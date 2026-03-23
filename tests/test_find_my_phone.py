"""Tests for the find_my_phone CLI module."""

from typer.testing import CliRunner

from find_my_phone import app

runner = CliRunner()


def test_help() -> None:
    """Test that help command works."""
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "Find My Phone" in result.output


def test_locate() -> None:
    """Test the locate command."""
    result = runner.invoke(app, ["locate"])
    assert result.exit_code == 0
    assert "coming soon" in result.output.lower()


def test_ring() -> None:
    """Test the ring command."""
    result = runner.invoke(app, ["ring"])
    assert result.exit_code == 0
    assert "coming soon" in result.output.lower()


def test_verbose_flag() -> None:
    """Test that verbose flag is accepted."""
    result = runner.invoke(app, ["-v", "locate"])
    assert result.exit_code == 0


def test_quiet_flag() -> None:
    """Test that quiet flag is accepted."""
    result = runner.invoke(app, ["-q", "locate"])
    assert result.exit_code == 0
