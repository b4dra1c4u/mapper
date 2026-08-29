from io import StringIO
from rich.console import Console
from typer.testing import CliRunner

from mapper import __version__
from mapper.cli import app, print_banner

runner = CliRunner()


def test_cli_version():
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert "mapper version" in result.output


def test_cli_missing_target():
    result = runner.invoke(app, [])
    assert result.exit_code != 0


def test_cli_invalid_target():
    result = runner.invoke(app, ["non_existent_file_path.txt"])
    assert result.exit_code == 1
    assert "No valid URLs found" in result.output or "is being ignored" in result.output


def test_cli_debug_option():
    result = runner.invoke(app, ["https://example.com/app.js", "--debug"])
    assert result.exit_code == 0 or "DEBUG" in result.output


def test_print_banner_output():
    buf = StringIO()
    test_console = Console(file=buf, color_system=None, force_terminal=False)
    print_banner(test_console)
    output = buf.getvalue()
    assert f"v{__version__}" in output
    assert "b4d_ra1c4u" in output


def test_cli_banner_shown_by_default():
    result = runner.invoke(app, ["non_existent_file_path.txt"])
    assert f"v{__version__}" in result.output
    assert "b4d_ra1c4u" in result.output


def test_cli_banner_suppressed_when_silent():
    result = runner.invoke(app, ["non_existent_file_path.txt", "--silent"])
    assert "b4d_ra1c4u" not in result.output

