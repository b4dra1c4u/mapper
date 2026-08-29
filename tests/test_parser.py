"""Unit tests for parser module."""

from mapper.parser import (
    discover_map_urls,
    extract_sourcemap_ref,
    get_fallback_map_url,
    get_fallback_map_urls,
    resolve_map_url,
)


def test_extract_sourcemap_ref_slash_slash():
    js_code = """
    console.log("hello world");
    //# sourceMappingURL=app.js.map
    """
    assert extract_sourcemap_ref(js_code) == "app.js.map"


def test_extract_sourcemap_ref_block_comment():
    js_code = """
    console.log("hello world");
    /*# sourceMappingURL=app.js.map */
    """
    assert extract_sourcemap_ref(js_code) == "app.js.map"


def test_resolve_map_url():
    base = "https://example.com/assets/js/main.js"
    assert resolve_map_url(base, "main.js.map") == "https://example.com/assets/js/main.js.map"
    assert resolve_map_url(base, "../maps/main.js.map") == "https://example.com/assets/maps/main.js.map"
    assert resolve_map_url(base, "https://cdn.example.com/main.js.map") == "https://cdn.example.com/main.js.map"
    assert resolve_map_url(base, "data:application/json;base64,eyJ2ZXJzaW9uIjozfQ==") is None


def test_get_fallback_map_url():
    assert get_fallback_map_url("https://example.com/app.js") == "https://example.com/app.js.map"
    assert get_fallback_map_url("https://example.com/app.js.map") == "https://example.com/app.js.map"


def test_get_fallback_map_urls():
    urls = get_fallback_map_urls("https://example.com/js/app.min.js")
    assert "https://example.com/js/app.min.js.map" in urls
    assert "https://example.com/js/app.js.map" in urls
    assert "https://example.com/js/maps/app.min.js.map" in urls


def test_discover_map_urls():
    js_url = "https://example.com/js/bundle.js"
    js_code = 'console.log("test");\n//# sourceMappingURL=bundle.js.map'
    headers = {"SourceMap": "header_bundle.js.map"}

    urls = discover_map_urls(js_url, js_code, headers=headers, include_fallback=True)

    assert "https://example.com/js/header_bundle.js.map" in urls
    assert "https://example.com/js/bundle.js.map" in urls
    # Deduplication check
    assert len(urls) == 2


def test_discover_map_urls_extended_fallback():
    js_url = "https://example.com/js/bundle.js"
    js_code = 'console.log("test");'

    urls = discover_map_urls(js_url, js_code, include_fallback=True, include_extended_fallback=True)

    assert "https://example.com/js/bundle.js.map" in urls
    assert "https://example.com/js/maps/bundle.js.map" in urls
    assert len(urls) > 2
