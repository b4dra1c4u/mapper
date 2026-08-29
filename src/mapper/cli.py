"""CLI interface for mapper using Typer and Rich."""

import asyncio
import json
import sys
from pathlib import Path
from typing import Dict, List, Optional

import typer
from rich.console import Console
from rich.text import Text
from rich.style import Style
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
from rich.table import Table

from mapper import __version__
from mapper.engine import MapperEngine
from mapper.models import MapperConfig, DownloadStats

app = typer.Typer(
    name="mapper",
    help="CLI tool for finding, downloading, and validating JavaScript source map files.",
    add_completion=False,
)

console = Console()
err_console = Console(stderr=True)

def print_banner(console: Optional[Console] = None) -> None:
    """Prints the Mapper ASCII art banner with a yellow to orange gradient.

    Args:
        console: Optional Rich Console instance to print to. Defaults to standard stdout Console.
    """
    if console is None:
        console = Console()

    # Logo lines (5 rows)
    logo_lines = [
        "███╗   ███╗ █████╗ ██████╗ ██████╗ ███████╗██████╗ ",
        "████╗ ████║██╔══██╗██╔══██╗██╔══██╗██╔════╝██╔══██╗",
        "██╔████╔██║███████║██████╔╝██████╔╝█████╗  ██████╔╝",
        "██║╚██╔╝██║██╔══██║██╔═══╝ ██╔═══╝ ██╔══╝  ██╔══██╗",
        "██║ ╚═╝ ██║██║  ██║██║     ██║     ███████╗██║  ██║",
    ]

    # Gradient: Yellow → Amber → Orange → Dark Orange → Deep Orange
    gradient_colors = [
        "#FFD700",  # Gold / Bright Yellow
        "#FFBF00",  # Amber
        "#FFA500",  # Orange
        "#FF8C00",  # Dark Orange
        "#FF6B00",  # Deep Orange
    ]

    # Print logo with vertical gradient
    console.print()
    for line, color in zip(logo_lines, gradient_colors):
        text = Text(line, style=Style(color=color, bold=True))
        console.print(text, justify="default")

    # Footer (centered, muted)
    footer = Text(
        f">> by ⚡ b4d_ra1c4u ⚡ <<                    v{__version__} ",
        #f"JS Source Map Extractor                      v{__version__} ",
        style=Style(color="#A0A0A0"),
    )
    console.print(footer, justify="default")
    console.print()


def parse_headers(header_list: Optional[List[str]]) -> Dict[str, str]:
    """Parses a list of header strings in 'Key: Value' format into a dictionary.

    Args:
        header_list: List of raw header strings.

    Returns:
        Dictionary of header key-value pairs.
    """
    headers = {}
    if not header_list:
        return headers
    for item in header_list:
        if ":" in item:
            key, value = item.split(":", 1)
            headers[key.strip()] = value.strip()
    return headers


def version_callback(value: bool) -> None:
    """Prints the application version and exits."""
    if value:
        console.print(f"[bold #FFA500]mapper[/bold #FFA500] version {__version__}")
        raise typer.Exit()


@app.command()
def run(
    target: str = typer.Argument(
        ...,
        help="Path to file containing URLs (one per line) or a single URL to analyze.",
    ),
    output_dir: Path = typer.Option(
        Path("output"),
        "-o",
        "--output-dir",
        help="Base directory to save downloaded files while preserving remote path structure.",
    ),
    concurrency: int = typer.Option(
        10,
        "-c",
        "--concurrency",
        help="Maximum concurrent HTTP downloads.",
    ),
    timeout: float = typer.Option(
        10.0,
        "-t",
        "--timeout",
        help="HTTP request timeout in seconds.",
    ),
    delay: float = typer.Option(
        0.0,
        "-d",
        "--delay",
        help="Delay in seconds between HTTP requests.",
    ),
    header: Optional[List[str]] = typer.Option(
        None,
        "-H",
        "--header",
        help="Custom HTTP headers in 'Name: Value' format. Can be specified multiple times.",
    ),
    user_agent: str = typer.Option(
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36",
        "-A",
        "--user-agent",
        help="Custom User-Agent header.",
    ),
    no_verify_ssl: bool = typer.Option(
        True,
        "--insecure",
        help="Disable SSL certificate verification.",
    ),
    proxy: Optional[str] = typer.Option(
        None,
        "--proxy",
        help="Pass all requests through an HTTP proxy (default: 127.0.0.1:8080 if set without a value).",
    ),
    debug: bool = typer.Option(
        False,
        "--debug",
        help="Enable verbose debug logging (directory creation, download paths, errors).",
    ),
    json_output: bool = typer.Option(
        False,
        "--json",
        help="Output raw JSON results to stdout (logs redirected to stderr).",
    ),
    silent: bool = typer.Option(
        False,
        "--silent",
        help="Suppress all log outputs except JSON results.",
    ),
    version: Optional[bool] = typer.Option(
        None,
        "-v",
        "--version",
        callback=version_callback,
        is_eager=True,
        help="Show version and exit.",
    ),
) -> None:
    """Discovers and downloads JavaScript files and source maps from target URLs."""

    log_console = err_console if json_output or silent else console

    if not silent:
        print_banner(log_console)

    # Collect input URLs
    urls: List[str] = []
    target_path = Path(target)

    if target_path.exists() and target_path.is_file():
        try:
            urls = [line.strip() for line in target_path.read_text().splitlines() if line.strip()]
        except Exception as e:
            log_console.print(f"[bold red]Error reading input file {target}: {e}[/bold red]")
            raise typer.Exit(code=1)
    else:
        if target.startswith("http://") or target.startswith("https://"):
            urls = [target]
        else:
            log_console.print(
                f"[bold red]Target '{target}' is being ignored, since it's not a valid HTTP/HTTPS URL.[/bold red]"
            )

    if not urls:
        log_console.print("[bold red]No valid URLs found to process.[/bold red]")
        raise typer.Exit(code=1)

    custom_headers = parse_headers(header)
    config = MapperConfig(
        output_dir=str(output_dir),
        concurrency=concurrency,
        timeout=timeout,
        delay=delay,
        headers=custom_headers,
        user_agent=user_agent,
        verify_ssl=not no_verify_ssl,
        debug=debug,
        proxy=proxy,
    )

    logger = None
    if debug:
        def log_debug(msg: str) -> None:
            err_console.print(msg)
        logger = log_debug

    if not json_output and not silent:
        log_console.print(
            Panel.fit(
                f"[bold #FFA500]mapper v{__version__}[/bold #FFA500] - JS Source Map Extractor\n"
                f"[dim]Targets: {len(urls)} | Output: {output_dir} | Debug: {debug}[/dim]",
                title="[bold #FF8C00]Mapper Initialized[/bold #FF8C00]",
            )
        )

    engine = MapperEngine(config, logger=logger)

    stats: Optional[DownloadStats] = None

    if json_output or silent or debug:
        stats = asyncio.run(engine.run(urls=urls))
    else:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            console=log_console,
        ) as progress:
            phase_tasks = {}

            def update_progress(phase: str, current: int, total: int) -> None:
                if phase not in phase_tasks:
                    phase_tasks[phase] = progress.add_task(f"[bold #FFA500]{phase}[/bold #FFA500]", total=total)
                progress.update(
                    phase_tasks[phase],
                    completed=current,
                    total=total,
                )

            stats = asyncio.run(engine.run(urls=urls, progress_callback=update_progress))

    if json_output:
        sys.stdout.write(stats.model_dump_json(indent=2) + "\n")
        return

    if not silent:
        table = Table(title="Extraction Summary Statistics", show_header=True, header_style="bold #FF8C00")
        table.add_column("Metric", style="#FFD700")
        table.add_column("Count", style="#A0A0A0", justify="right")
        

        table.add_row("Total URLs Processed", str(stats.total_urls_processed))
        table.add_row("JS Files Identified", str(stats.js_files_found))
        table.add_row("JS Files Downloaded", str(stats.js_files_downloaded))
        table.add_row("JS Files Failed", f"[red]{stats.js_files_failed}[/red]" if stats.js_files_failed else "0")
        table.add_row("Source Maps Discovered", str(stats.map_files_discovered))
        table.add_row("Source Maps Downloaded", f"[bold #FFD700]{stats.map_files_downloaded}[/bold #FFD700]")
        table.add_row("Source Maps Invalid (False Positives)", str(stats.map_files_invalid))
        table.add_row("Source Maps Download Failed", f"[red]{stats.map_files_failed}[/red]" if stats.map_files_failed else "0")

        log_console.print("")
        log_console.print(table)
        log_console.print(f"[bold #FFD700]✔ Done![/bold #FFD700] Downloaded assets saved in: [#FFD700]{output_dir}[/#FFD700]\n")


VAL_OPTIONS = {
    "-o", "--output-dir",
    "-c", "--concurrency",
    "-t", "--timeout",
    "-d", "--delay",
    "-H", "--header",
    "-A", "--user-agent",
    "--proxy",
}


def normalize_proxy_args(argv: List[str]) -> List[str]:
    """Normalizes CLI arguments so that '--proxy' passed without a value defaults to '127.0.0.1:8080'.

    Args:
        argv: List of raw CLI argument strings.

    Returns:
        Modified argument list with bare '--proxy' options assigned '127.0.0.1:8080'.
    """
    if "--proxy" not in argv:
        return argv

    # Separate executable script name (sys.argv[0]) from actual arguments
    prog = argv[:1]
    args = argv[1:]

    new_args: List[str] = []
    i = 0
    while i < len(args):
        arg = args[i]
        if arg == "--proxy":
            if i + 1 >= len(args) or args[i + 1].startswith("-"):
                new_args.extend(["--proxy", "127.0.0.1:8080"])
            else:
                has_target_before = False
                skip_next = False
                for j in range(0, i):
                    if skip_next:
                        skip_next = False
                        continue
                    if args[j] in VAL_OPTIONS:
                        skip_next = True
                        continue
                    if not args[j].startswith("-"):
                        has_target_before = True
                        break

                has_target_after = False
                skip_next = False
                for j in range(i + 2, len(args)):
                    if skip_next:
                        skip_next = False
                        continue
                    if args[j] in VAL_OPTIONS:
                        skip_next = True
                        continue
                    if not args[j].startswith("-"):
                        has_target_after = True
                        break

                if has_target_before or has_target_after:
                    new_args.append(arg)
                else:
                    new_args.extend(["--proxy", "127.0.0.1:8080"])
        else:
            new_args.append(arg)
        i += 1
    return prog + new_args


def main() -> None:
    """Main entry point for console script."""
    sys.argv = normalize_proxy_args(sys.argv)
    app()


if __name__ == "__main__":
    main()
