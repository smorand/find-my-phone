"""CLI entry point for the find_my_phone application."""

import logging
import sys
from typing import Annotated, Any

import typer
from rich.console import Console
from rich.table import Table

from config import Settings
from logging_config import setup_logging
from tracing import configure_tracing

app = typer.Typer()
logger = logging.getLogger(__name__)
console = Console()

CANONIC_ID_DISPLAY_LENGTH = 20


def _init(verbose: bool = False, quiet: bool = False) -> Settings:
    """Initialize logging, tracing, and return settings."""
    settings = Settings()
    setup_logging(app_name=settings.app_name, verbose=verbose, quiet=quiet)
    configure_tracing(app_name=settings.app_name)
    return settings


def _ensure_logged_in(settings: Settings) -> None:
    """Exit with error if not logged in."""
    from auth import is_logged_in  # noqa: PLC0415

    if not is_logged_in(settings):
        console.print("[red]Not logged in.[/red] Run 'find-my-phone login' first.")
        sys.exit(1)


def _resolve_device_id(settings: Settings, device_ref: str) -> str:
    """Resolve a device reference (index or canonic ID) to a canonic ID."""
    from device_manager import list_devices as do_list  # noqa: PLC0415

    try:
        idx = int(device_ref)
        devices = do_list(settings)
        if idx < 1 or idx > len(devices):
            console.print(f"[red]Invalid device index {idx}.[/red] Use 'find-my-phone list' to see devices.")
            sys.exit(1)
        return devices[idx - 1].canonic_id
    except ValueError:
        return device_ref


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
    _init(verbose=verbose, quiet=quiet)


@app.command()
def login() -> None:
    """Authenticate with Google to access Find My Device."""
    from auth import login as do_login  # noqa: PLC0415

    settings = Settings()
    try:
        do_login(settings)
        console.print("[green]Login successful![/green] Tokens cached.")
    except Exception as exc:
        console.print(f"[red]Login failed:[/red] {exc}")
        sys.exit(1)


@app.command(name="list")
def list_devices() -> None:
    """List all devices associated with your Google account."""
    from device_manager import list_devices as do_list  # noqa: PLC0415

    settings = Settings()
    _ensure_logged_in(settings)

    try:
        devices = do_list(settings)
    except RuntimeError as exc:
        console.print(f"[red]Error:[/red] {exc}")
        sys.exit(1)

    if not devices:
        console.print("[yellow]No devices found.[/yellow]")
        return

    table = Table(title="Your Devices")
    table.add_column("#", style="dim", width=3)
    table.add_column("Name", style="bold")
    table.add_column("Type")
    table.add_column("Manufacturer")
    table.add_column("Model")
    table.add_column("Location")
    table.add_column("Canonic ID", style="dim")

    for idx, device in enumerate(devices, 1):
        location_str = _format_location(device)
        canonic_display = device.canonic_id
        if len(canonic_display) > CANONIC_ID_DISPLAY_LENGTH:
            canonic_display = canonic_display[:CANONIC_ID_DISPLAY_LENGTH] + "..."

        table.add_row(
            str(idx),
            device.name,
            device.device_type,
            device.manufacturer,
            device.model,
            location_str or "[dim]unavailable[/dim]",
            canonic_display,
        )

    console.print(table)


@app.command()
def ring(
    device: Annotated[str, typer.Argument(help="Device index (from 'list') or canonic ID")],
    stop: Annotated[bool, typer.Option("--stop", "-s", help="Stop ringing")] = False,
) -> None:
    """Ring your Android phone to find it."""
    from device_manager import ring_device  # noqa: PLC0415

    settings = Settings()
    _ensure_logged_in(settings)

    canonic_id = _resolve_device_id(settings, device)

    action = "Stopping ring" if stop else "Ringing"
    console.print(f"[cyan]{action} device...[/cyan]")

    success = ring_device(settings, canonic_id, stop=stop)
    if success:
        if stop:
            console.print("[green]Ring stopped.[/green]")
        else:
            console.print("[green]Ring command sent![/green] Your phone should be ringing.")
    else:
        console.print("[red]Failed to send ring command.[/red]")
        sys.exit(1)


@app.command()
def locate(
    device: Annotated[str, typer.Argument(help="Device index (from 'list') or canonic ID")],
) -> None:
    """Show the last known location of your device."""
    from device_manager import list_devices as do_list  # noqa: PLC0415

    settings = Settings()
    _ensure_logged_in(settings)

    canonic_id = _resolve_device_id(settings, device)

    console.print("[cyan]Fetching device list for location data...[/cyan]")
    try:
        devices = do_list(settings)
    except RuntimeError as exc:
        console.print(f"[red]Error:[/red] {exc}")
        sys.exit(1)

    target = None
    for d in devices:
        if d.canonic_id == canonic_id:
            target = d
            break

    if not target:
        console.print(f"[red]Device with ID '{canonic_id}' not found.[/red]")
        sys.exit(1)

    console.print(f"\n[bold]{target.name}[/bold] ({target.device_type})")

    if not target.locations:
        console.print("[yellow]No location data available.[/yellow]")
        console.print("[dim]Location may be encrypted or the device has not reported recently.[/dim]")
        return

    for loc in target.locations:
        if loc.location_name:
            console.print(f"  Location: {loc.location_name}")
        if loc.latitude != 0 or loc.longitude != 0:
            console.print(f"  Coordinates: {loc.latitude:.6f}, {loc.longitude:.6f}")
            console.print(f"  Google Maps: {loc.google_maps_url}")
        if loc.accuracy > 0:
            console.print(f"  Accuracy: {loc.accuracy:.0f}m")
        if loc.timestamp:
            console.print(f"  Last seen: {loc.timestamp:%Y-%m-%d %H:%M:%S UTC}")
        console.print(f"  Status: {loc.status}")


def _format_location(device: Any) -> str:
    """Format device location for table display."""
    if not device.locations:
        return ""
    loc = device.locations[0]
    parts = []
    if loc.location_name:
        parts.append(loc.location_name)
    elif loc.latitude != 0 or loc.longitude != 0:
        parts.append(f"{loc.latitude:.6f}, {loc.longitude:.6f}")
    if loc.timestamp:
        parts.append(f"({loc.timestamp:%Y-%m-%d %H:%M})")
    return " ".join(parts)


if __name__ == "__main__":
    app()
