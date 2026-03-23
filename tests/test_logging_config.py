"""Tests for the logging_config module."""

import logging
from pathlib import Path

from logging_config import setup_logging


def test_setup_logging_creates_log_file(tmp_path: Path) -> None:
    """Test that setup_logging creates a log file."""
    setup_logging(app_name="test_app", log_dir=tmp_path)
    log_file = tmp_path / "test_app.log"
    logger = logging.getLogger("test_setup")
    logger.info("test message")
    assert log_file.exists()


def test_setup_logging_verbose(tmp_path: Path) -> None:
    """Test that verbose mode sets DEBUG level."""
    setup_logging(app_name="test_verbose", verbose=True, log_dir=tmp_path)
    root = logging.getLogger()
    assert root.level == logging.DEBUG


def test_setup_logging_quiet(tmp_path: Path) -> None:
    """Test that quiet mode sets WARNING level."""
    setup_logging(app_name="test_quiet", quiet=True, log_dir=tmp_path)
    root = logging.getLogger()
    assert root.level == logging.WARNING


def test_setup_logging_quiet_overrides_verbose(tmp_path: Path) -> None:
    """Test that quiet takes precedence over verbose."""
    setup_logging(app_name="test_both", verbose=True, quiet=True, log_dir=tmp_path)
    root = logging.getLogger()
    assert root.level == logging.WARNING
