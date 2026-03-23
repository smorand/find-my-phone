# Find My Phone

A CLI tool to locate and track your Android phone from the command line.

## Project Structure

```
find-my-phone/
├── src/
│   ├── find_my_phone.py    # CLI entry point (Typer)
│   ├── config.py           # Settings (pydantic-settings)
│   ├── logging_config.py   # Logging setup (rich + file)
│   └── tracing.py          # OpenTelemetry tracing (JSONL)
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

## Quick Start

```bash
# Install dependencies
make sync

# Run the CLI
make run

# Run with arguments
make run ARGS='--help'

# Locate your phone
make run ARGS='locate'

# Ring your phone
make run ARGS='ring'
```

## Available Commands

| Command | Description |
|---------|-------------|
| `make sync` | Install dependencies |
| `make run` | Run the CLI application |
| `make run ARGS='...'` | Run with arguments |
| `make test` | Run tests |
| `make test-cov` | Run tests with coverage |
| `make check` | Run all quality checks |
| `make format` | Format code with Ruff |
| `make docker-build` | Build Docker image |
| `make run-up` | Start with Docker Compose |
| `make clean` | Remove build artifacts |
| `make help` | Show all available commands |

## Configuration

Environment variables are prefixed with `FIND_MY_PHONE_`:

| Variable | Description | Default |
|----------|-------------|---------|
| `FIND_MY_PHONE_APP_NAME` | Application name | `find_my_phone` |
| `FIND_MY_PHONE_DEBUG` | Enable debug mode | `false` |

You can also create a `.env` file in the project root.

## Log Files

- `find_my_phone.log` : Application logs (also shown in console with colors)
- `find_my_phone-otel.log` : OpenTelemetry traces in JSONL format
