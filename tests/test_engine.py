"""Integration tests for MapperEngine workflow."""

import pytest
import httpx
import base64
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


@pytest.mark.asyncio
async def test_engine_reconstructs_inline_source_map(tmp_path, monkeypatch):
    output_dir = tmp_path / "out"
    config = MapperConfig(output_dir=str(output_dir))
    source_map = b'{"version":3,"sources":["app.ts"],"mappings":"AAAA"}'
    inline_map = base64.b64encode(source_map).decode()

    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == "https://example.com/js/app.js"
        return httpx.Response(
            200,
            text=f'console.log("app");\n//# sourceMappingURL=data:application/json;charset=utf-8;base64,{inline_map}',
            headers={"Content-Type": "application/javascript"},
        )

    transport = httpx.MockTransport(handler)
    async_client = httpx.AsyncClient
    monkeypatch.setattr(
        "mapper.engine.httpx.AsyncClient",
        lambda **kwargs: async_client(transport=transport, **kwargs),
    )

    stats = await MapperEngine(config).run(["https://example.com/js/app.js"])

    map_path = output_dir / "example.com" / "js" / "app.js.map"
    assert map_path.read_bytes() == source_map
    assert stats.map_files_discovered == 1
    assert stats.map_files_downloaded == 1
