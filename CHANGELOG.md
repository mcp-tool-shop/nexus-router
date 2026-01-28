# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.3.0] - 2026-01-27

### Added

- **nexus-router.export**: Deterministic, portable snapshot of a run
  - SHA256 digest over canonical {run, events} for integrity verification
  - Repeated exports of same run produce identical digests
  - Optional provenance record linking export to source
  - Bundle format v0.3 designed for cross-DB portability
- **nexus-router.import**: Safe bundle loading into a database
  - Digest verification before import (default on)
  - Conflict resolution modes: `reject_on_conflict`, `new_run_id`, `overwrite`
  - Automatic run_id remapping in events when using `new_run_id` mode
  - Post-import replay validation (default on)
  - Preserves original event sequences and timestamps
- **JSON Schemas** for v0.3 tools:
  - `nexus-router.export.request.v0.3.json`
  - `nexus-router.export.response.v0.3.json`
  - `nexus-router.import.request.v0.3.json`
  - `nexus-router.import.response.v0.3.json`
- **Tests**: Contract tests, golden fixtures, and round-trip tests for export/import

### Changed

- `tool.py` exports `export()` and `import_bundle()` functions
- `__init__.py` exports `export` and `import_` modules

### Notes

- Bundles are self-contained and replayable without original DB
- Import normalizes IDs when mode=new_run_id (run_id, event_id, payload references)
- Real tool dispatch still planned for future version

## [0.2.0] - 2025-01-28

### Added

- **nexus-router.inspect**: Read-only tool to summarize runs in the event store
  - Filter by `run_id`, `status`, `since`
  - Pagination with `limit` and `offset`
  - Returns counts (total, completed, failed, running) and run details
- **nexus-router.replay**: Reconstruct run view from events with invariant checking
  - Validates event sequence invariants (ordering, completeness)
  - Returns detailed step timeline and violation reports
  - `strict` mode controls whether violations cause `ok=false`
- **Invariant checks** in replay:
  - Sequence starts at 0 and increments by 1
  - `RUN_STARTED` exists and is first
  - `PLAN_CREATED` appears after `RUN_STARTED`
  - `STEP_STARTED` precedes `STEP_COMPLETED` per step
  - `TOOL_CALL_*` appears between `STEP_STARTED` and `STEP_COMPLETED`
  - Terminal event (`RUN_COMPLETED` or `RUN_FAILED`) exists
- **JSON Schemas** for v0.2 tools:
  - `nexus-router.inspect.request.v0.2.json`
  - `nexus-router.inspect.response.v0.2.json`
  - `nexus-router.replay.request.v0.2.json`
  - `nexus-router.replay.response.v0.2.json`
- **Tests**: Contract tests and golden fixtures for inspect and replay

### Changed

- `tool.py` refactored: schema caching, cleaner tool function signatures
- `__init__.py` exports `inspect` and `replay` modules

### Notes

- v0.2 operates directly on SQLite event store (no import/export yet)
- Real tool dispatch still planned for v0.3+
- Import/export capability planned for v0.3

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
