"""Validation logic for JavaScript source map files and JavaScript assets."""

import json
import re
from typing import Tuple, Union

JS_EXTENSIONS = (
    ".js",
    ".ts",
    ".jsx",
    ".tsx",
    ".mjs",
    ".cjs",
    ".map",
)

HTML_PATTERNS = [
    r"^\s*<!DOCTYPE\s+html",
    r"^\s*<html[\s>]",
    r"^\s*<head[\s>]",
    r"^\s*<body[\s>]",
    r"^\s*<div[\s>]",
]


def is_js_url(url: str) -> bool:
    """Checks if a URL points to a JavaScript or TypeScript-like file.

    Args:
        url: The URL string to test.

    Returns:
        True if the URL matches standard JS/TS extensions or path patterns.
    """
    clean_url = url.split("?")[0].split("#")[0].lower()
    return clean_url.endswith(JS_EXTENSIONS) or any(
        ext in clean_url for ext in (".js?", ".ts?", ".jsx?", ".tsx?", ".mjs?", ".cjs?")
    )


def validate_source_map(content: Union[str, bytes]) -> Tuple[bool, str]:
    """Validates whether raw content is a genuine JavaScript source map file.

    Checks for JSON validity, required Source Map keys, and filters out HTML
    error pages (false positive 200 responses). Handles XSSI prefix `)]}'`.

    Args:
        content: String or bytes representation of the map file content.

    Returns:
        A tuple of (is_valid: bool, reason: str).
    """
    if isinstance(content, bytes):
        try:
            text = content.decode("utf-8", errors="replace")
        except Exception as e:
            return False, f"Failed to decode content as UTF-8: {e}"
    else:
        text = content

    text_stripped = text.lstrip()

    # Reject obvious HTML documents
    for pattern in HTML_PATTERNS:
        if re.search(pattern, text_stripped, re.IGNORECASE):
            return False, "Content appears to be an HTML page instead of JSON source map"

    # Handle optional XSSI protection prefix (e.g. Google source maps )]}')
    if text_stripped.startswith(")]}'"):
        text_stripped = text_stripped[4:].lstrip()

    try:
        data = json.loads(text_stripped)
    except json.JSONDecodeError as e:
        return False, f"Invalid JSON format: {e}"

    if not isinstance(data, dict):
        return False, "Source map JSON root must be an object"

    # Standard Source Map v3 keys (or indexed source maps with sections)
    required_keys = {"version", "sources", "mappings", "sections"}
    present_keys = required_keys.intersection(data.keys())

    if not present_keys:
        return False, f"JSON object missing standard source map keys ({required_keys})"

    return True, "Valid source map"
