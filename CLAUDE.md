# Find My Phone

## Overview

CLI tool to locate and track Android phones. Built with Python 3.13, Typer, pydantic-settings, OpenTelemetry, Ruff, mypy, pytest.

## Key Commands

```bash
make sync               # Install dependencies
make run                # Run the CLI application
make run ARGS='--help'  # Run with arguments
make check              # Full quality gate (lint, format, typecheck, security, tests+coverage)
make docker-build       # Build Docker image
```

## Project Structure

- `src/find_my_phone.py` : CLI entry point (Typer app) with `locate` and `ring` commands
- `src/config.py` : Settings via pydantic-settings (FIND_MY_PHONE_ prefix)
- `src/logging_config.py` : Logging setup with rich + file output (<app>.log)
- `src/tracing.py` : OpenTelemetry tracing with JSONL export (<app>-otel.log)
- `tests/` : Unit tests
- `tests/functional/` : Integration tests

## Conventions

- Entry point in `src/find_my_phone.py` contains only CLI wiring
- Business logic in separate modules within `src/`
- Use `@dataclass(frozen=True)` for value objects
- All async operations use asyncio patterns
- Logging with `%` formatting, not f-strings
- OTel traces to `<app>-otel.log`, app logs to `<app>.log`

## Processes

- Every modification must be committed and pushed to the remote repository
- Every modification must include documentation updates (CLAUDE.md + .agent_docs and README.md + docs)

## Quality Gate

Run `make check` before every commit. It runs: lint, format-check, typecheck, security, test-cov (>= 80% coverage).

## Auto-Evaluation Checklist

Before considering any task complete:
- [ ] `make check` passes
- [ ] No sync blocking calls in async code
- [ ] All external calls traced with OpenTelemetry
- [ ] No forbidden practices (bare except, print, mutable defaults, .format(), assert)
- [ ] Config via Settings class, not os.environ
- [ ] Dependencies injected, not created inline
- [ ] Test coverage >= 80%

## Coding Standards

This project follows the `python` skill. Reload it for full coding standards reference.

## Documentation Index

- `.agent_docs/python.md` : Python coding standards and conventions
- `.agent_docs/makefile.md` : Detailed Makefile documentation
