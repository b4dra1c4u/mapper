"""Asynchronous HTTP downloader engine with path preservation and rate limiting."""

import asyncio
import os
import re
import shutil
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple
from urllib.parse import unquote, urlparse

import httpx

from mapper.models import DownloadResult, MapperConfig
from mapper.validator import validate_source_map


def url_to_local_path(url: str, output_dir: str) -> Path:
    """Converts a remote URL to a local filesystem path preserving directory structure.

    Args:
        url: The full remote URL.
        output_dir: Base directory where downloaded files should be saved.

    Returns:
        Path object representing the target local file path.
    """
    parsed = urlparse(url)
    domain = parsed.netloc.replace(":", "_")
    path = unquote(parsed.path).lstrip("/")

    if not path or path.endswith("/"):
        path += "index.js"

    # Remove query string parameters from filename to keep filesystem clean
    # while preserving file extensions
    path_parts = path.split("/")
    filename = path_parts[-1]

    if "?" in filename:
        clean_filename = filename.split("?")[0]
        if not clean_filename:
            clean_filename = "index.js"
        path_parts[-1] = clean_filename

    relative_path = os.path.join(*path_parts)
    # Sanitize invalid characters for filenames
    relative_path = re.sub(r'[<>:"\\|?*]', "_", relative_path)

    return Path(output_dir) / domain / relative_path


class AsyncDownloader:
    """Async HTTP Downloader using httpx for managing concurrent downloads."""

    def __init__(
        self,
        config: MapperConfig,
        logger: Optional[Callable[[str], None]] = None,
    ):
        """Initializes the downloader with configuration options.

        Args:
            config: MapperConfig containing timeout, headers, concurrency, etc.
            logger: Optional logging callback for debug messages.
        """
        self.config = config
        self.logger = logger
        self.semaphore = asyncio.Semaphore(config.concurrency)
        self.headers = {
            "User-Agent": config.user_agent,
            **config.headers,
        }

    def _log(self, msg: str) -> None:
        if self.logger:
            self.logger(msg)

    async def download_file(
        self,
        client: httpx.AsyncClient,
        url: str,
        is_map_file: bool = False,
    ) -> Tuple[DownloadResult, Optional[bytes]]:
        """Downloads a single URL, validates map files, and writes to local disk.

        Overwrites existing files and directories without prompting.

        Args:
            client: Active httpx.AsyncClient session.
            url: Target URL to download.
            is_map_file: Whether the target is expected to be a source map file.

        Returns:
            Tuple of (DownloadResult, raw_content_bytes_if_successful).
        """
        async with self.semaphore:
            if self.config.delay > 0:
                await asyncio.sleep(self.config.delay)

            target_path = url_to_local_path(url, self.config.output_dir)

            try:
                response = await client.get(
                    url,
                    headers=self.headers,
                    follow_redirects=True,
                    timeout=self.config.timeout,
                )

                if response.status_code != 200:
                    err_msg = f"HTTP Status {response.status_code}"
                    self._log(f"[bold red][ERROR][/bold red] {url} -> {err_msg}")
                    return (
                        DownloadResult(
                            url=url,
                            success=False,
                            status_code=response.status_code,
                            error=err_msg,
                            is_map_file=is_map_file,
                            content_type=response.headers.get("Content-Type"),
                        ),
                        None,
                    )

                content = response.content

                # For map files, perform strict validation against false positives (e.g. 200 OK HTML 404 pages)
                if is_map_file:
                    is_valid, reason = validate_source_map(content)
                    if not is_valid:
                        err_msg = f"Invalid source map: {reason}"
                        self._log(f"[bold red][ERROR/FALSE_POSITIVE][/bold red] {url} -> {err_msg}")
                        return (
                            DownloadResult(
                                url=url,
                                success=False,
                                status_code=response.status_code,
                                error=err_msg,
                                is_map_file=True,
                                content_type=response.headers.get("Content-Type"),
                            ),
                            None,
                        )

                # Ensure parent directory structure exists, handling any file/directory conflicts
                parent_dir = target_path.parent
                if parent_dir.exists() and parent_dir.is_file():
                    parent_dir.unlink()

                if not parent_dir.exists():
                    self._log(f"[dim #FFA500][DIR_CREATED][/dim #FFA500] {parent_dir}")
                    parent_dir.mkdir(parents=True, exist_ok=True)

                # Handle existing file/directory at target_path (overwrite without prompt)
                if target_path.exists():
                    if target_path.is_dir():
                        shutil.rmtree(target_path)
                    self._log(f"[dim yellow][OVERWRITING][/dim yellow] {target_path}")

                target_path.write_bytes(content)
                self._log(f"[bold green][DOWNLOADED][/bold green] {url} -> {target_path}")

                return (
                    DownloadResult(
                        url=url,
                        success=True,
                        status_code=response.status_code,
                        local_path=str(target_path),
                        is_map_file=is_map_file,
                        content_type=response.headers.get("Content-Type"),
                    ),
                    content,
                )

            except httpx.RequestError as exc:
                err_msg = f"Network error: {str(exc)}"
                self._log(f"[bold red][ERROR][/bold red] {url} -> {err_msg}")
                return (
                    DownloadResult(
                        url=url,
                        success=False,
                        error=err_msg,
                        is_map_file=is_map_file,
                    ),
                    None,
                )
            except Exception as exc:
                err_msg = f"Unexpected error: {str(exc)}"
                self._log(f"[bold red][ERROR][/bold red] {url} -> {err_msg}")
                return (
                    DownloadResult(
                        url=url,
                        success=False,
                        error=err_msg,
                        is_map_file=is_map_file,
                    ),
                    None,
                )

    def write_inline_source_map(self, js_path: str, content: bytes) -> DownloadResult:
        """Validates and saves an inline source map next to its JavaScript file.

        Args:
            js_path: Local path of the already downloaded JavaScript file.
            content: Decoded inline source map bytes.

        Returns:
            Result describing the local source map write.
        """
        is_valid, reason = validate_source_map(content)
        map_path = Path(js_path).with_name(Path(js_path).name + ".map")
        if not is_valid:
            err_msg = f"Invalid source map: {reason}"
            self._log(f"[bold red][ERROR/FALSE_POSITIVE][/bold red] {js_path} -> {err_msg}")
            return DownloadResult(
                url=js_path,
                success=False,
                error=err_msg,
                is_map_file=True,
            )

        try:
            map_path.write_bytes(content)
            self._log(f"[bold green][RECONSTRUCTED][/bold green] {js_path} -> {map_path}")
            return DownloadResult(
                url=js_path,
                success=True,
                local_path=str(map_path),
                is_map_file=True,
            )
        except OSError as exc:
            err_msg = f"Failed to write inline source map: {exc}"
            self._log(f"[bold red][ERROR][/bold red] {js_path} -> {err_msg}")
            return DownloadResult(
                url=js_path,
                success=False,
                error=err_msg,
                is_map_file=True,
            )
