"""Unit tests for HTTP proxy integration and configuration."""

from typing import List
from unittest.mock import AsyncMock, patch

import pytest
import typer
from typer.testing import CliRunner

from mapper.cli import app, normalize_proxy_args
from mapper.engine import MapperEngine
from mapper.models import MapperConfig, DownloadResult

runner = CliRunner()


def test_mapper_config_proxy_formatting() -> None:
    """Tests that MapperConfig formats proxy URL and disables verify_ssl when proxy is set."""
    # Bare host:port gets http:// prepended and disables verify_ssl
    config1 = MapperConfig(proxy="127.0.0.1:8080")
    assert config1.proxy == "http://127.0.0.1:8080"
    assert config1.verify_ssl is False

    # URL with scheme is preserved and disables verify_ssl
    config2 = MapperConfig(proxy="http://10.0.0.1:9090", verify_ssl=True)
    assert config2.proxy == "http://10.0.0.1:9090"
    assert config2.verify_ssl is False

    # No proxy leaves verify_ssl unchanged
    config3 = MapperConfig()
    assert config3.proxy is None
    assert config3.verify_ssl is True


def test_normalize_proxy_args_defaults() -> None:
    """Tests that normalize_proxy_args injects default proxy '127.0.0.1:8080' when set without a value."""
    # Bare --proxy at end
    res1 = normalize_proxy_args(["mapper", "target.js", "--proxy"])
    assert res1 == ["mapper", "target.js", "--proxy", "127.0.0.1:8080"]

    # Bare --proxy before another option
    res2 = normalize_proxy_args(["mapper", "target.js", "--proxy", "--debug"])
    assert res2 == ["mapper", "target.js", "--proxy", "127.0.0.1:8080", "--debug"]

    # Bare --proxy before target argument (sys.argv[0] is executable path)
    res3 = normalize_proxy_args(["/usr/bin/mapper", "--proxy", "target.js"])
    assert res3 == ["/usr/bin/mapper", "--proxy", "127.0.0.1:8080", "target.js"]

    # Explicit proxy value provided
    res4 = normalize_proxy_args(["/usr/bin/mapper", "target.js", "--proxy", "10.0.0.1:9090"])
    assert res4 == ["/usr/bin/mapper", "target.js", "--proxy", "10.0.0.1:9090"]

    # Explicit proxy before target
    res5 = normalize_proxy_args(["/usr/bin/mapper", "--proxy", "10.0.0.1:9090", "target.js"])
    assert res5 == ["/usr/bin/mapper", "--proxy", "10.0.0.1:9090", "target.js"]


@pytest.mark.asyncio
async def test_engine_creates_client_with_proxy() -> None:
    """Tests that MapperEngine initializes httpx.AsyncClient with proxy, trust_env=False, and verify=False."""
    config = MapperConfig(proxy="127.0.0.1:8080")
    engine = MapperEngine(config)

    with patch("mapper.engine.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client_cls.return_value = mock_client

        with patch.object(engine.downloader, "download_file", new_callable=AsyncMock) as mock_download:
            mock_download.return_value = (
                DownloadResult(url="https://example.com/app.js", success=True, local_path="/tmp/app.js"),
                b"console.log('test');",
            )
            await engine.run(["https://example.com/app.js"])

        mock_client_cls.assert_called_once_with(
            verify=False,
            proxy="http://127.0.0.1:8080",
            trust_env=False,
        )


def test_cli_proxy_option_invocations() -> None:
    """Tests CLI execution with --proxy option."""
    with patch("mapper.cli.MapperEngine.run", new_callable=AsyncMock) as mock_run:
        mock_run.return_value.total_urls_processed = 1
        mock_run.return_value.js_files_found = 0
        mock_run.return_value.js_files_downloaded = 0
        mock_run.return_value.js_files_failed = 0
        mock_run.return_value.map_files_discovered = 0
        mock_run.return_value.map_files_downloaded = 0
        mock_run.return_value.map_files_invalid = 0
        mock_run.return_value.map_files_failed = 0

        # Invocation with default --proxy
        args = normalize_proxy_args(["https://example.com/app.js", "--proxy", "--silent"])
        result = runner.invoke(app, args)
        assert result.exit_code == 0
