# Find My Phone Documentation

## Overview

Find My Phone is a CLI tool to locate and track your Android phone from the command line.

## Getting Started

See the [README](../README.md) for installation and quick start instructions.

## Architecture

The project follows a standard Python CLI structure:

- **Entry Point** (`src/find_my_phone.py`): Typer CLI with `locate` and `ring` commands
- **Configuration** (`src/config.py`): Environment-based settings using pydantic-settings
- **Logging** (`src/logging_config.py`): Rich console + file logging
- **Tracing** (`src/tracing.py`): OpenTelemetry spans exported as JSONL

## Development

### Prerequisites

- Python 3.13+
- uv package manager

### Setup

```bash
make sync
```

### Quality Checks

```bash
make check    # Full quality gate: lint, format, typecheck, security, tests
```

### Testing

```bash
make test         # Run tests
make test-cov     # Run tests with coverage
```
