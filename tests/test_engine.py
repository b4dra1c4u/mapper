"""Integration tests for MapperEngine workflow."""

import pytest
import httpx
from mapper.engine import MapperEngine
from mapper.models import MapperConfig


@pytest.mark.asyncio
async def test_engine_run_with_mock(tmp_path):
    output_dir = tmp_path / "out"
    config = MapperConfig(output_dir=str(output_dir))
    engine = MapperEngine(config)

    # Mock HTTP transport using httpx.MockTransport
    def handler(request: httpx.Request) -> httpx.Response:
        url_str = str(request.url)
        if url_str == "https://example.com/js/app.js":
            return httpx.Response(
                200,
                text='console.log("app");\n//# sourceMappingURL=app.js.map',
                headers={"Content-Type": "application/javascript"},
            )
        elif url_str == "https://example.com/js/app.js.map":
            return httpx.Response(
                200,
                text='{"version": 3, "sources": ["app.ts"], "mappings": "AAAA"}',
                headers={"Content-Type": "application/json"},
            )
        return httpx.Response(404, text="Not Found")

    # Patch client creation or inject transport in engine downloader tests
    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        # Test downloader directly with mock client
        res1, content1 = await engine.downloader.download_file(client, "https://example.com/js/app.js", is_map_file=False)
        assert res1.success
        assert res1.local_path == str(output_dir / "example.com" / "js" / "app.js")

        res2, content2 = await engine.downloader.download_file(client, "https://example.com/js/app.js.map", is_map_file=True)
        assert res2.success
        assert res2.local_path == str(output_dir / "example.com" / "js" / "app.js.map")


@pytest.mark.asyncio
async def test_engine_false_positive_map_rejected(tmp_path):
    output_dir = tmp_path / "out"
    config = MapperConfig(output_dir=str(output_dir))
    engine = MapperEngine(config)

    def handler(request: httpx.Request) -> httpx.Response:
        # 404 returning 200 OK with HTML body
        return httpx.Response(
            200,
            text='<!DOCTYPE html><html><body>Error 404</body></html>',
            headers={"Content-Type": "text/html"},
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        res, content = await engine.downloader.download_file(
            client, "https://example.com/js/missing.js.map", is_map_file=True
        )
        assert not res.success
        assert res.error and "Invalid source map" in res.error
