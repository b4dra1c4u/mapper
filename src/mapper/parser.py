"""Parser for discovering source map references from JavaScript files and HTTP headers.

Provides:
- Robust sourceMappingURL extraction from single-line and block comments (last match wins).
- HTTP SourceMap / X-SourceMap header extraction.
- Standard and extended fallback candidate generation.
- Careful string search for quoted .map paths while avoiding .map() method calls.
"""

from __future__ import annotations

import re
from typing import Dict, List, Optional, Set
from urllib.parse import urljoin, urlparse, urlunparse


# ---------------------------------------------------------------------------
# Regex patterns
# ---------------------------------------------------------------------------

# Official / common sourceMappingURL comments (//# , //@ , /*# ... */)
SOURCEMAP_COMMENT_RE = re.compile(
    r"""
    (?:
        //[#@]\s*sourceMappingURL\s*=\s*(\S+)                 # single-line comment
      | /\*[\#@]?\s*sourceMappingURL\s*=\s*([^*\s]+)\s*\*/     # block comment
    )
    """,
    re.IGNORECASE | re.VERBOSE,
)

# Quoted strings that look like source-map paths/URLs.
# Designed to avoid common false positives from Array.prototype.map etc.
MAP_IN_STRING_RE = re.compile(
    r"""
    (?P<quote>['"`])                    # opening quote
    (?P<path>
        (?:                             # optional scheme / absolute path
            https?://[^\s'"`]+?
          | /[^\s'"`]*?
          | \.{0,2}/[^\s'"`]*?
          | [a-zA-Z0-9_\-./]+?
        )
        \.map                           # must end with .map
        (?:\?[^\s'"`]*)?                # optional query string
    )
    (?P=quote)                          # matching closing quote
    """,
    re.VERBOSE | re.IGNORECASE,
)

# Quick negative filter: reject if the match is immediately followed by '('
FOLLOWED_BY_PAREN_RE = re.compile(r"\.map\s*\(")


# ---------------------------------------------------------------------------
# Core helpers
# ---------------------------------------------------------------------------

def extract_sourcemap_ref(content: str) -> Optional[str]:
    """Extracts the sourceMappingURL value from JavaScript source code.

    Returns the last match found in the file (conventionally at the end).

    Args:
        content: JavaScript source code text.

    Returns:
        The extracted source map URL reference string, or None if not found.
    """
    if not content:
        return None

    matches = list(SOURCEMAP_COMMENT_RE.finditer(content))
    if not matches:
        return None

    for match in reversed(matches):
        ref = match.group(1) or match.group(2)
        if ref:
            ref = ref.strip().strip("'\"")
            if ref:
                return ref
    return None


def resolve_map_url(base_js_url: str, ref: str) -> Optional[str]:
    """Resolves a source map reference relative to the original JS file URL.

    Args:
        base_js_url: Full URL of the JavaScript file.
        ref: Relative or absolute source map URL reference.

    Returns:
        Resolved absolute URL string, or None if invalid or data URI.
    """
    if not ref:
        return None

    ref = ref.strip()
    if not ref or ref.startswith("data:"):
        return None

    return urljoin(base_js_url, ref)


def get_fallback_map_url(base_js_url: str) -> str:
    """Generates the classic fallback source map URL by appending `.map`.

    Args:
        base_js_url: Base JS URL.

    Returns:
        Fallback URL ending with .map.
    """
    parsed = urlparse(base_js_url)
    if not parsed.path.endswith(".map"):
        return f"{base_js_url}.map"
    return base_js_url


def get_fallback_map_urls(base_js_url: str) -> List[str]:
    """Generates several plausible source-map URLs based on common conventions.

    Args:
        base_js_url: Base JS URL.

    Returns:
        List of candidate fallback URL strings.
    """
    parsed = urlparse(base_js_url)
    path = parsed.path or ""
    candidates: List[str] = []

    # 1. Classic: foo.js -> foo.js.map
    if not path.endswith(".map"):
        candidates.append(base_js_url + ".map")

    # 2. Strip .min / .bundle / .prod before adding .map
    for suffix in (".min.js", ".bundle.js", ".prod.js", ".js"):
        if path.endswith(suffix):
            base = path[: -len(suffix)]
            candidates.append(urlunparse(parsed._replace(path=base + ".js.map", query="", fragment="")))
            candidates.append(urlunparse(parsed._replace(path=base + ".map", query="", fragment="")))
            break

    # 3. Common sub-directories used by various bundlers
    filename = path.rsplit("/", 1)[-1] if path else ""
    if filename:
        for subdir in ("maps/", "sourcemaps/", "source-maps/", ".maps/", "map/"):
            candidates.append(urljoin(base_js_url, subdir + filename + ".map"))
            if filename.endswith(".js"):
                candidates.append(
                    urljoin(base_js_url, subdir + filename[:-3] + ".map")
                )

    seen: Set[str] = set()
    result: List[str] = []
    for c in candidates:
        if c and c not in seen:
            seen.add(c)
            result.append(c)
    return result


def _extract_map_paths_from_strings(content: str) -> List[str]:
    """Find quoted strings that look like source-map paths, avoiding .map() calls.

    Args:
        content: JS content string.

    Returns:
        List of discovered relative/absolute .map path strings.
    """
    found: List[str] = []
    seen: Set[str] = set()

    for match in MAP_IN_STRING_RE.finditer(content):
        path = match.group("path").strip()
        if not path or path in seen:
            continue

        start, end = match.span()
        window = content[max(0, start - 20) : min(len(content), end + 10)]
        if FOLLOWED_BY_PAREN_RE.search(window):
            continue

        if "/" in path or path.count(".") >= 2 or path.endswith(".js.map"):
            seen.add(path)
            found.append(path)

    return found


def discover_map_urls(
    js_url: str,
    js_content: str,
    headers: Optional[Dict[str, str]] = None,
    include_fallback: bool = True,
    include_string_search: bool = True,
    include_extended_fallback: bool = False,
) -> List[str]:
    """Discovers potential source map URLs for a given JavaScript file.

    Order of discovery (and priority):
      1. HTTP SourceMap / X-SourceMap header (spec priority)
      2. sourceMappingURL comment in the JS (last match wins)
      3. Quoted .map paths found in the source (carefully filtered)
      4. Conventional fallback candidates (*.js.map)
      5. Extended fallback candidates (optional: directory/suffix variations)

    Args:
        js_url: Full URL of the JavaScript file.
        js_content: Text content of the JavaScript file.
        headers: Optional response headers from the JS download.
        include_fallback: Whether to add classic .map fallback.
        include_string_search: Whether to scan for quoted .map paths.
        include_extended_fallback: Whether to add directory & naming variation fallbacks.

    Returns:
        Deduplicated list of absolute URLs to try as source maps.
    """
    discovered: List[str] = []
    seen: Set[str] = set()

    def add(url: Optional[str]) -> None:
        if url and url not in seen:
            seen.add(url)
            discovered.append(url)

    # 1. HTTP headers (SourceMap has precedence over the comment per spec)
    if headers:
        normalized = {k.lower(): v for k, v in headers.items()}
        for header_name in ("sourcemap", "x-sourcemap"):
            value = normalized.get(header_name)
            if value:
                add(resolve_map_url(js_url, value.strip()))

    # 2. Official sourceMappingURL comment
    ref = extract_sourcemap_ref(js_content)
    if ref:
        add(resolve_map_url(js_url, ref))

    # 3. Careful string search for .map paths (avoids .map() false positives)
    if include_string_search and js_content:
        for path in _extract_map_paths_from_strings(js_content):
            add(resolve_map_url(js_url, path))

    # 4. Conventional fallback (.js.map)
    if include_fallback:
        add(get_fallback_map_url(js_url))

    # 5. Extended fallbacks (optional directory & naming variations)
    if include_extended_fallback:
        for fallback in get_fallback_map_urls(js_url):
            add(fallback)

    return discovered