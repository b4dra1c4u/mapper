"""Unit tests for validator module."""

from mapper.validator import is_js_url, validate_source_map


def test_is_js_url():
    assert is_js_url("https://example.com/static/app.js")
    assert is_js_url("https://example.com/assets/main.ts?v=123")
    assert is_js_url("https://example.com/bundle.jsx")
    assert is_js_url("https://example.com/chunk.mjs")
    assert is_js_url("https://example.com/bundle.js.map")
    assert not is_js_url("https://example.com/index.html")
    assert not is_js_url("https://example.com/style.css")
    assert not is_js_url("https://example.com/api/v1/users")


def test_validate_source_map_valid():
    valid_map = '{"version": 3, "file": "out.js", "sources": ["in.js"], "mappings": "AAAA"}'
    is_valid, reason = validate_source_map(valid_map)
    assert is_valid
    assert reason == "Valid source map"


def test_validate_source_map_with_xssi_prefix():
    valid_xssi_map = ')]}\'\n{"version": 3, "sources": ["in.js"], "mappings": "AAAA"}'
    is_valid, reason = validate_source_map(valid_xssi_map)
    assert is_valid


def test_validate_source_map_html_error_page():
    html_page = """<!DOCTYPE html>
    <html>
    <head><title>404 Not Found</title></head>
    <body><h1>Page Not Found</h1></body>
    </html>"""
    is_valid, reason = validate_source_map(html_page)
    assert not is_valid
    assert "HTML page" in reason


def test_validate_source_map_invalid_json():
    invalid_json = '{"version": 3, "sources": ['
    is_valid, reason = validate_source_map(invalid_json)
    assert not is_valid
    assert "Invalid JSON format" in reason


def test_validate_source_map_missing_map_keys():
    non_map_json = '{"error": "Not Found", "code": 404}'
    is_valid, reason = validate_source_map(non_map_json)
    assert not is_valid
    assert "missing standard source map keys" in reason
