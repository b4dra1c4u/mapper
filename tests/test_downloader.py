"""Unit tests for downloader path resolution, logging, and overwriting behavior."""

from pathlib import Path
import pytest
import httpx

from mapper.downloader import AsyncDownloader, url_to_local_path
from mapper.models import MapperConfig


def test_url_to_local_path():
    output_dir = "/tmp/mapper_output"

    p1 = url_to_local_path("https://example.com/assets/js/main.js", output_dir)
    assert p1 == Path("/tmp/mapper_output/example.com/assets/js/main.js")

    p2 = url_to_local_path("https://cdn.test.org:8080/static/bundle.js?v=1.2.3#hash", output_dir)
    assert p2 == Path("/tmp/mapper_output/cdn.test.org_8080/static/bundle.js")

    p3 = url_to_local_path("https://example.com/", output_dir)
    assert p3 == Path("/tmp/mapper_output/example.com/index.js")


@pytest.mark.asyncio
async def test_downloader_debug_logging(tmp_path):
    logs = []

    def log_cb(msg: str):
        logs.append(msg)

    config = MapperConfig(output_dir=str(tmp_path / "log_test"), debug=True)
    downloader = AsyncDownloader(config, logger=log_cb)

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if "good.js" in url:
            return httpx.Response(200, text="console.log(1);")
        return httpx.Response(404, text="Not found")

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        res1, _ = await downloader.download_file(client, "https://example.com/good.js")
        assert res1.success
        assert any("DIR_CREATED" in log for log in logs)
        assert any("DOWNLOADED" in log for log in logs)

        res2, _ = await downloader.download_file(client, "https://example.com/bad.js")
        assert not res2.success
        assert any("ERROR" in log for log in logs)


@pytest.mark.asyncio
async def test_downloader_overwrites_existing_files(tmp_path):
    output_dir = tmp_path / "overwrite_test"
    config = MapperConfig(output_dir=str(output_dir), debug=True)
    logs = []

    downloader = AsyncDownloader(config, logger=lambda msg: logs.append(msg))

    target_file = output_dir / "example.com" / "js" / "app.js"
    target_file.parent.mkdir(parents=True, exist_ok=True)
    target_file.write_text("old content")

    assert target_file.read_text() == "old content"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="new content")

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        res, _ = await downloader.download_file(client, "https://example.com/js/app.js")
        assert res.success
        assert target_file.read_text() == "new content"
        assert any("OVERWRITING" in log for log in logs)
