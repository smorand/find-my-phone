# Find My Phone

A CLI tool to locate and track your Android phone from the command line using Google's Find My Device internal API.

## How It Works

This tool uses the internal `android.googleapis.com/nova/` API (the same backend that powers Google's Find My Device app). Authentication is handled through a Chrome login flow that captures an OAuth token, which is then exchanged for an Android Device Manager scoped token via `gpsoauth`.

Communication with the API uses Protocol Buffers (protobuf) for encoding/decoding requests and responses.

## Project Structure

```
find-my-phone/
├── src/
│   ├── find_my_phone.py    # CLI entry point (Typer)
│   ├── auth.py             # Google auth (Chrome login, token exchange)
│   ├── device_manager.py   # Nova API (list, ring, locate)
│   ├── config.py           # Settings (pydantic-settings)
│   ├── logging_config.py   # Logging setup (rich + file)
│   ├── tracing.py          # OpenTelemetry tracing (JSONL)
│   └── proto/              # Protobuf definitions and generated code
│       ├── Common.proto
│       ├── DeviceUpdate.proto
│       ├── Common_pb2.py       # Generated
│       └── DeviceUpdate_pb2.py # Generated
├── tests/                  # Unit tests
│   └── functional/         # Integration tests
├── pyproject.toml          # Project configuration
├── Makefile                # Build automation
├── Dockerfile              # Container build
└── README.md               # This file
```

## Requirements

- Python 3.13 or later
- uv (package manager)
- Google Chrome (for initial login)

## Quick Start

```bash
# Install dependencies
make sync

# Login to your Google account (opens Chrome)
make run ARGS='login'

# List your devices
make run ARGS='list'

# Locate a device (by index or canonic ID)
make run ARGS='locate 1'

# Ring your phone
make run ARGS='ring 1'

# Stop ringing
make run ARGS='ring 1 --stop'
```

## CLI Commands

| Command | Description |
|---------|-------------|
| `login` | Authenticate via Chrome (required once) |
| `list` | List all devices on your Google account |
| `locate <device>` | Show last known location with Google Maps link |
| `ring <device>` | Ring a device |
| `ring <device> --stop` | Stop ringing |

The `<device>` argument can be either a numeric index (from `list` output) or a canonic device ID.

### Flags

| Flag | Description |
|------|-------------|
| `-v` / `--verbose` | Enable debug logging |
| `-q` / `--quiet` | Suppress non-essential output |

## Development Commands

| Command | Description |
|---------|-------------|
| `make sync` | Install dependencies |
| `make run` | Run the CLI application |
| `make run ARGS='...'` | Run with arguments |
| `make test` | Run tests |
| `make test-cov` | Run tests with coverage |
| `make check` | Run all quality checks (lint, format, typecheck, security, tests) |
| `make format` | Format code with Ruff |
| `make proto` | Compile protobuf definitions |
| `make docker-build` | Build Docker image |
| `make clean` | Remove build artifacts |
| `make help` | Show all available commands |

## Configuration

Environment variables are prefixed with `FIND_MY_PHONE_`:

| Variable | Description | Default |
|----------|-------------|---------|
| `FIND_MY_PHONE_APP_NAME` | Application name | `find_my_phone` |
| `FIND_MY_PHONE_DEBUG` | Enable debug mode | `false` |
| `FIND_MY_PHONE_SECRETS_DIR` | Secrets storage directory | `~/.config/find-my-phone` |

You can also create a `.env` file in the project root.

## Authentication

1. Run `find-my-phone login` to open a Chrome window
2. Sign in to your Google account
3. The tool captures an OAuth token and exchanges it for API access tokens
4. Tokens are cached in `~/.config/find-my-phone/secrets.json`

## Log Files

- `find_my_phone.log` : Application logs (also shown in console with colors)
- `find_my_phone-otel.log` : OpenTelemetry traces in JSONL format
