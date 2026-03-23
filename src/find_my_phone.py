"""CLI entry point for the find_my_phone application."""

import logging
from typing import Annotated

import typer

from config import Settings
from logging_config import setup_logging
from tracing import configure_tracing

app = typer.Typer()
logger = logging.getLogger(__name__)


@app.callback()
def main(
    verbose: Annotated[
        bool,
        typer.Option("--verbose", "-v", help="Enable debug logging"),
    ] = False,
    quiet: Annotated[
        bool,
        typer.Option("--quiet", "-q", help="Only show warnings and errors"),
    ] = False,
) -> None:
    """Find My Phone: locate and track your Android phone."""
    settings = Settings()
    setup_logging(app_name=settings.app_name, verbose=verbose, quiet=quiet)
    configure_tracing(app_name=settings.app_name)


@app.command()
def locate() -> None:
    """Locate your Android phone."""
    with __import__("tracing").trace_span("cli.locate"):
        logger.info("Locating phone...")
        typer.echo("Phone location feature coming soon.")


@app.command()
def ring() -> None:
    """Ring your Android phone."""
    with __import__("tracing").trace_span("cli.ring"):
        logger.info("Ringing phone...")
        typer.echo("Phone ring feature coming soon.")


if __name__ == "__main__":
    app()
