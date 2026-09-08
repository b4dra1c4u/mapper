<p align="center">
  <img src="assets/banner.png" alt="mapper banner" width="406" />
</p>

`mapper` is a command-line tool designed for bug bounty hunters and security researchers to discover, download, and extract JavaScript files and their associated `.map` Source Map files while preserving original remote paths locally.

## Features

- **URL Batch Input:** Read target URLs from a file or direct CLI argument.
- **JS Identification:** Filters and identifies JS-like files (`.js`, `.ts`, `.jsx`, `.tsx`, `.mjs`, `.cjs`).
- **Path Preservation:** Downloads files locally preserving URL path structure relative to working directory / output directory.
- **Source Map Extraction:** Parses downloaded JS files for `//# sourceMappingURL=...`, `/*# sourceMappingURL=...`, and `SourceMap` / `X-SourceMap` HTTP headers, with fallback to standard `.js.map` naming patterns.
- **False Positive Validation:** Checks downloaded map files to ensure they are valid JSON source maps and not HTML error pages (e.g. 404/500 responses returning HTML with HTTP 200).
- **Structured Output & Logging:** Supports `--json` mode for automated pipeline chaining (`jq`) and standard colored `rich` outputs.
- **Rate Limiting & Custom Headers:** Configurable concurrency, request delay, timeout, and custom User-Agent or custom HTTP headers.

## Installation

### Globally via pipx

Install `mapper` into an isolated global environment:

```bash
# Install directly from the local repository directory
pipx install .

# Or install in editable mode for active development
pipx install --editable .

# Or install from a pre-built wheel
pipx install dist/mapper-0.1.3-py3-none-any.whl --force

# Or directly from a Git repository
pipx install git+https://github.com/b4dra1c4u/mapper.git
```

### Via `uv`

```bash
uv pip install .
```

---

## Running from Source (Development)

Run `mapper` directly from source without manual installation using `uv`:

```bash
# Display help and available options
uv run mapper --help

# Run mapper against a single URL or file
uv run mapper https://example.com/app.js
uv run mapper urls.txt -o ./downloads
```

---

## Usage

```bash
# Basic scan with an input file containing URLs (one per line)
mapper urls.txt

# Scan a single URL with custom output directory and custom headers
mapper https://example.com/static/bundle.js -o ./output_dir -H "Authorization: Bearer token" -H "X-Custom-Header: value"

# Route traffic through an HTTP proxy (e.g. Burp Suite)
mapper urls.txt --proxy 127.0.0.1:8080

# Output structured JSON results to stdout (for jq / automation pipelines)
mapper urls.txt --json > results.json

# Silent mode (suppress banner and progress UI, log errors to stderr)
mapper urls.txt --silent --json
```

---

## Testing

Run tests using `pytest` inside the `uv` environment:

```bash
# Run standard unit test suite
uv run pytest

# Run integration tests
uv run pytest -m integration

# Run all tests (unit + integration)
uv run pytest -o addopts=""
```