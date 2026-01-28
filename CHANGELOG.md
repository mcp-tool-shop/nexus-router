# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.1] - 2025-01-27

### Added

- **Policy enforcement**: `max_steps` now enforced — plans exceeding limit trigger `RUN_FAILED`
- **Schema validation**: Request validation wired into `tool.run()` via JSON Schema
- **Exception posture A**: Unexpected exceptions recorded to event log, then re-raised
- **EventStore lifecycle**: Added `close()` method and context manager support
- **CI pipeline**: GitHub Actions workflow for Python 3.9-3.12
- **Dev tooling**: ruff linting, mypy strict type checking
- **Contract tests**: Request/response schema validation tests
- **SECURITY.md**: Vulnerability reporting guidelines
- **CHANGELOG.md**: This file

### Changed

- Schemas moved from top-level `schemas/` to `nexus_router/schemas/` (package data)
- `pyproject.toml` updated with dev extras, ruff/mypy configuration

### Fixed

- All ruff lint errors resolved
- All mypy strict mode errors resolved
- Line length issues in SQL queries and test files

## [0.1.0] - 2025-01-27

### Added

- Initial release
- Event-sourced router with immutable event log
- SQLite-backed EventStore with WAL mode and monotonic sequencing
- Policy gating: `allow_apply` enforcement
- Provenance bundles with SHA256 digests
- Fixture-driven planning (`plan_override`)
- JSON Schema definitions for request/response
- Basic test coverage

### Notes

- v0.1.0 does not dispatch real tools (fixture-driven only)
- Real tool dispatch planned for v0.2
