"""Data models for mapper CLI using Pydantic."""

from typing import Dict, List, Optional
from pydantic import BaseModel, Field


class DownloadResult(BaseModel):
    """Result of an individual file download attempt."""

    url: str
    success: bool
    status_code: Optional[int] = None
    local_path: Optional[str] = None
    error: Optional[str] = None
    is_map_file: bool = False
    content_type: Optional[str] = None


class DownloadStats(BaseModel):
    """Summary statistics for the extraction session."""

    total_urls_processed: int = 0
    js_files_found: int = 0
    js_files_downloaded: int = 0
    js_files_failed: int = 0
    map_files_discovered: int = 0
    map_files_downloaded: int = 0
    map_files_failed: int = 0
    map_files_invalid: int = 0
    downloaded_files: List[str] = Field(default_factory=list)


class MapperConfig(BaseModel):
    """Configuration options for HTTP request processing and download engine."""

    output_dir: str = "."
    concurrency: int = 10
    timeout: float = 10.0
    delay: float = 0.0
    user_agent: str = "mapper/0.1.3 (BugBounty/OSINT Tool)"
    headers: Dict[str, str] = Field(default_factory=dict)
    verify_ssl: bool = True
    debug: bool = False
    proxy: Optional[str] = None

    def model_post_init(self, __context: Optional[dict] = None) -> None:
        """Post-initialization callback to handle proxy formatting and disable TLS verification.

        Args:
            __context: Optional context passed by Pydantic.
        """
        if self.proxy:
            # Disable TLS verification when proxy is used
            self.verify_ssl = False
            if not self.proxy.startswith(("http://", "https://", "socks5://", "socks5h://")):
                self.proxy = f"http://{self.proxy}"


