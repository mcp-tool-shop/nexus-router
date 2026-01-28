# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.5.1] - 2026-01-27

### Added

- **Redaction hooks**: Prevent secrets from leaking into events/errors
  - `default_redact_args()`: Redacts keys matching `token|secret|password|api_key|...`
  - `default_redact_text()`: Redacts Bearer tokens, API keys, passwords in text
  - `redact_args` and `redact_text` parameters on `SubprocessAdapter`
  - `redact_args_for_event()` and `redact_text_for_event()` methods
- **Separate output limits**: `max_stdout_chars` and `max_stderr_chars` (was `max_capture_chars`)
- **Expanded error codes**:
  - `PERMISSION_DENIED`: Command execution permission denied
  - `CWD_NOT_FOUND`: Working directory doesn't exist
  - `CWD_NOT_DIRECTORY`: Working directory is a file
  - `ENV_INVALID`: Environment variable key or value not a string
- **Exception details**: `NexusOperationalError.details` dict with contextual info
  - `TIMEOUT` includes `timeout_s`
  - `NONZERO_EXIT` includes `returncode` and `stderr_excerpt` (redacted)
  - `INVALID_JSON_OUTPUT` includes `stdout_excerpt` (head/tail for large output)
- **Temp file security**: chmod 0o600 on POSIX (best-effort)
- **Cleanup retry**: One retry with configurable delay if temp file removal fails
  - `last_cleanup_failed` property for diagnostics
  - `cleanup_retry_delay_s` parameter (default 0.1s)
- **Identifiable temp files**: Prefix `nexus-router-args-` for operator debugging

### Changed

- `max_capture_chars` renamed to `max_stdout_chars` (breaking change)
- Temp file prefix changed from `nexus_args_` to `nexus-router-args-`

### Notes

- Redaction is applied to event payloads and error details, not to subprocess input
- Pass `redact_args=lambda x: x` to disable arg redaction
- 107 tests passing

## [0.5.0] - 2026-01-27

### Added

- **SubprocessAdapter**: Execute tool calls via external commands
  - Invokes `<base_cmd> call <tool> <method> --json-args-file <path>`
  - Payload passed via temp file (avoids Windows command-line length limits)
  - Parses JSON output from stdout on success
  - Timeout enforcement with configurable `timeout_s`
  - Error codes: `TIMEOUT`, `NONZERO_EXIT`, `INVALID_JSON_OUTPUT`, `COMMAND_NOT_FOUND`
  - Stable `adapter_id` derived from `base_cmd` hash (or user-provided)
  - All failures mapped to `NexusOperationalError` (graceful degradation)
- **Test fixture**: `tests/fixtures/echo_tool.py` for deterministic subprocess testing
  - Simulates success, timeout, exit codes, and invalid JSON output

### Changed

- Version bumped to 0.5.0

### Notes

- SubprocessAdapter never raises `NexusBugError` - all subprocess failures are operational
- Temp files cleaned up in `finally` block (Windows-safe)
- `max_capture_chars` only affects event diagnostics, not JSON parsing
- External command contract: print JSON to stdout, exit 0 on success

## [0.4.0] - 2026-01-27

### Added

- **Dispatch Adapters**: Pluggable tool execution interface for real tool integration
  - `DispatchAdapter` protocol defining `adapter_id` property and `call()` method
  - `NullAdapter`: Default adapter returning deterministic simulated output
  - `FakeAdapter`: Configurable test adapter with response injection, call logging, and error simulation
- **Error Taxonomy**: Structured exception handling for dispatch failures
  - `NexusOperationalError`: Expected failures (network, timeout) - recorded but not re-raised
  - `NexusBugError`: Unexpected failures (invariant violations) - recorded then re-raised
  - Unknown exceptions treated as bugs and re-raised after recording
- **apply mode execution**: Real tool calls via adapter when `mode=apply`
  - Policy gating (`allow_apply`) enforced before dispatch
  - Call duration tracked in milliseconds
  - Adapter ID recorded in events and response
- **dry_run mode isolation**: Never invokes adapter, returns simulated output
- **Response schema v0.4**: Added `adapter_id` field to summary

### Changed

- `tool.run()` accepts optional `adapter` parameter
- `Router.__init__()` accepts optional `adapter` parameter (defaults to `NullAdapter`)
- Response `summary` now includes `adapter_id`
- Event payloads include `adapter_id` for traceability

### Notes

- Adapters are explicitly passed to `run()` (no global registry)
- `SubprocessAdapter` for external processes deferred to v0.5
- Operational errors allow run to continue (subsequent steps execute)
- Bug errors halt the run immediately after recording

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
