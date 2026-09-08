"""Core orchestrator engine for executing mapper extraction workflows."""

import asyncio
from typing import Any, Callable, Dict, List, Optional, Tuple
import httpx

from mapper.downloader import AsyncDownloader
from mapper.models import DownloadResult, DownloadStats, MapperConfig
from mapper.parser import decode_inline_sourcemap, discover_map_urls, extract_sourcemap_ref
from mapper.validator import is_js_url


class MapperEngine:
    """Core workflow engine for finding, downloading, and validating JS source maps."""

    def __init__(
        self,
        config: MapperConfig,
        logger: Optional[Callable[[str], None]] = None,
    ):
        """Initializes MapperEngine with config and optional logger.

        Args:
            config: Configuration for downloader and output directories.
            logger: Optional logging callback for debug outputs.
        """
        self.config = config
        self.logger = logger
        self.downloader = AsyncDownloader(config, logger=logger)

    def _log(self, msg: str) -> None:
        if self.logger:
            self.logger(msg)

    async def run(
        self,
        urls: List[str],
        progress_callback: Optional[Callable[[str, int, int], None]] = None,
    ) -> DownloadStats:
        """Executes the full pipeline for given initial URLs concurrently.

        1. Identifies JS files
        2. Downloads JS files concurrently (throttled by config.concurrency)
        3. Parses references to map files
        4. Downloads and validates map files concurrently
        5. Compiles stats

        Args:
            urls: List of target URLs.
            progress_callback: Optional callback for progress reporting (phase, current, total).

        Returns:
            DownloadStats object summarizing execution results.
        """
        stats = DownloadStats(total_urls_processed=len(urls))

        # 1. Identify JS files
        js_urls = [u.strip() for u in urls if u.strip() and is_js_url(u)]
        stats.js_files_found = len(js_urls)

        self._log(f"[dim #FFA500][DEBUG][/dim #FFA500] Identified {len(js_urls)} JS-like URL(s) out of {len(urls)} input URL(s)")

        if not js_urls:
            return stats

        client_kwargs: Dict[str, Any] = {"verify": self.config.verify_ssl}
        if self.config.proxy:
            client_kwargs["proxy"] = self.config.proxy
            client_kwargs["trust_env"] = False
            self._log(f"[dim #FFA500][DEBUG][/dim #FFA500] Configured HTTP proxy: {self.config.proxy}")

        async with httpx.AsyncClient(**client_kwargs) as client:
            # 2. Download JS files concurrently
            completed_js_count = 0
            total_js = len(js_urls)

            async def _download_js(url: str) -> Tuple[DownloadResult, Optional[bytes]]:
                nonlocal completed_js_count
                res, content = await self.downloader.download_file(client, url, is_map_file=False)
                completed_js_count += 1
                if progress_callback:
                    progress_callback("Downloading JS files", completed_js_count, total_js)
                return res, content

            js_tasks = [_download_js(url) for url in js_urls]
            js_results: List[Tuple[DownloadResult, Optional[bytes]]] = await asyncio.gather(*js_tasks)

            for res, content in js_results:
                if res.success:
                    stats.js_files_downloaded += 1
                    if res.local_path:
                        stats.downloaded_files.append(res.local_path)
                else:
                    stats.js_files_failed += 1

            # 3. Analyze downloaded JS files for map references
            candidate_map_urls: List[str] = []
            for res, content in js_results:
                if res.success and content:
                    try:
                        text_content = content.decode("utf-8", errors="replace")
                        inline_map = decode_inline_sourcemap(extract_sourcemap_ref(text_content) or "")
                        if inline_map is not None and res.local_path:
                            stats.map_files_discovered += 1
                            inline_result = self.downloader.write_inline_source_map(res.local_path, inline_map)
                            if inline_result.success:
                                stats.map_files_downloaded += 1
                                if inline_result.local_path:
                                    stats.downloaded_files.append(inline_result.local_path)
                            else:
                                stats.map_files_invalid += 1
                            continue

                        discovered = discover_map_urls(
                            js_url=res.url,
                            js_content=text_content,
                            include_fallback=True,
                        )
                        for m_url in discovered:
                            if m_url not in candidate_map_urls:
                                candidate_map_urls.append(m_url)
                    except Exception as e:
                        self._log(f"[bold red][ERROR][/bold red] Error analyzing JS content for {res.url}: {e}")

            stats.map_files_discovered += len(candidate_map_urls)
            self._log(f"[dim #FFA500][DEBUG][/dim #FFA500] Discovered {stats.map_files_discovered} potential source map candidate(s)")

            # 4. Download and validate candidate map files concurrently
            if candidate_map_urls:
                completed_map_count = 0
                total_maps = len(candidate_map_urls)

                async def _download_map(map_url: str) -> DownloadResult:
                    nonlocal completed_map_count
                    res, _ = await self.downloader.download_file(client, map_url, is_map_file=True)
                    completed_map_count += 1
                    if progress_callback:
                        progress_callback("Downloading Source Maps", completed_map_count, total_maps)
                    return res

                map_tasks = [_download_map(map_url) for map_url in candidate_map_urls]
                map_results: List[DownloadResult] = await asyncio.gather(*map_tasks)

                for res in map_results:
                    if res.success:
                        stats.map_files_downloaded += 1
                        if res.local_path:
                            stats.downloaded_files.append(res.local_path)
                    else:
                        if res.error and "Invalid source map" in res.error:
                            stats.map_files_invalid += 1
                        else:
                            stats.map_files_failed += 1

        return stats
