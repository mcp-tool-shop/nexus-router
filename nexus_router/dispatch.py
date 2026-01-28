"""Dispatch adapters for nexus-router tool calls."""

from __future__ import annotations

import errno
import hashlib
import json
import os
import re
import stat
import subprocess
import tempfile
import time
from typing import Any, Callable, Dict, List, Optional, Protocol, Tuple

from .exceptions import NexusBugError, NexusOperationalError

# Default pattern for detecting sensitive keys in args
_SENSITIVE_KEY_PATTERN = re.compile(
    r"(?i)(token|secret|password|api[_-]?key|authorization|cookie|credential|private[_-]?key)"
)


def default_redact_args(args: Dict[str, Any]) -> Dict[str, Any]:
    """
    Default redaction function for args.

    Replaces values of keys matching sensitive patterns with "[REDACTED]".
    Recursively handles nested dicts.
    """

    def redact(obj: Any) -> Any:
        if isinstance(obj, dict):
            return {k: _redact_value(k, v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [redact(item) for item in obj]
        return obj

    def _redact_value(key: str, value: Any) -> Any:
        if _SENSITIVE_KEY_PATTERN.search(key):
            return "[REDACTED]"
        return redact(value)

    return redact(args)  # type: ignore[no-any-return]


def default_redact_text(text: str) -> str:
    """
    Default redaction function for text output.

    Redacts common secret patterns in text (Bearer tokens, API keys, etc.).
    """
    # Bearer tokens (do this first, before Authorization pattern)
    text = re.sub(r"Bearer\s+[A-Za-z0-9_\-\.]+", "Bearer [REDACTED]", text)
    # API key patterns (common formats)
    text = re.sub(r"(?i)(api[_-]?key[=:]\s*)['\"]?[A-Za-z0-9_\-]+['\"]?", r"\1[REDACTED]", text)
    # Generic key=value for sensitive keys (skip Authorization: Bearer already handled)
    text = re.sub(
        r"(?i)(token|secret|password|cookie)[=:]\s*['\"]?[^\s'\"]+['\"]?",
        r"\1=[REDACTED]",
        text,
    )
    # Authorization header without Bearer (direct value)
    text = re.sub(
        r"(?i)authorization[=:]\s*(?!Bearer\s)['\"]?[^\s'\"]+['\"]?",
        "authorization=[REDACTED]",
        text,
    )
    return text


class DispatchAdapter(Protocol):
    """
    Protocol for dispatch adapters.

    Adapters implement the transport layer for tool calls.
    The router decides what to call; the adapter decides how to call it.
    """

    @property
    def adapter_id(self) -> str:
        """Unique identifier for this adapter instance."""
        ...

    def call(self, tool: str, method: str, args: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute a tool call.

        Args:
            tool: Tool identifier (e.g., "file-system")
            method: Method name (e.g., "read_file")
            args: Arguments dict for the method

        Returns:
            JSON-serializable dict with the result.

        Raises:
            NexusOperationalError: For expected failures (timeout, tool error, etc.)
            NexusBugError: For unexpected failures (bugs in adapter)
            Other exceptions: Treated as bugs by the router
        """
        ...


class NullAdapter:
    """
    Adapter that returns deterministic placeholder outputs.

    Used for:
    - dry_run mode (default)
    - Testing without external dependencies
    - Development/debugging
    """

    def __init__(self, adapter_id: str = "null") -> None:
        self._adapter_id = adapter_id

    @property
    def adapter_id(self) -> str:
        return self._adapter_id

    def call(self, tool: str, method: str, args: Dict[str, Any]) -> Dict[str, Any]:
        """Return a deterministic placeholder result."""
        return {
            "simulated": True,
            "tool": tool,
            "method": method,
            "args_echo": args,
            "result": None,
        }


class FakeAdapter:
    """
    Adapter with configurable responses for testing.

    Allows tests to specify exact outputs or errors for specific
    (tool, method) combinations.
    """

    def __init__(self, adapter_id: str = "fake") -> None:
        self._adapter_id = adapter_id
        self._responses: Dict[Tuple[str, str], Callable[..., Dict[str, Any]]] = {}
        self._default_response: Optional[Callable[..., Dict[str, Any]]] = None
        self._call_log: list[Dict[str, Any]] = []

    @property
    def adapter_id(self) -> str:
        return self._adapter_id

    @property
    def call_log(self) -> list[Dict[str, Any]]:
        """Log of all calls made to this adapter."""
        return self._call_log

    def set_response(
        self,
        tool: str,
        method: str,
        response: Dict[str, Any] | Callable[[Dict[str, Any]], Dict[str, Any]],
    ) -> None:
        """
        Set the response for a specific (tool, method) combination.

        Args:
            tool: Tool identifier
            method: Method name
            response: Either a dict to return, or a callable that takes args
                      and returns a dict (or raises an exception)
        """
        if callable(response):
            self._responses[(tool, method)] = response
        else:
            self._responses[(tool, method)] = lambda _args: response

    def set_default_response(
        self,
        response: Dict[str, Any] | Callable[[str, str, Dict[str, Any]], Dict[str, Any]],
    ) -> None:
        """
        Set the default response for unregistered (tool, method) combinations.

        Args:
            response: Either a dict to return, or a callable that takes
                      (tool, method, args) and returns a dict
        """
        if callable(response):
            self._default_response = response
        else:
            self._default_response = lambda _t, _m, _a: response

    def set_operational_error(
        self,
        tool: str,
        method: str,
        message: str,
        error_code: str = "TOOL_ERROR",
    ) -> None:
        """Configure a specific call to raise NexusOperationalError."""

        def raise_error(_args: Dict[str, Any]) -> Dict[str, Any]:
            raise NexusOperationalError(message, error_code=error_code)

        self._responses[(tool, method)] = raise_error

    def set_bug_error(
        self,
        tool: str,
        method: str,
        message: str,
        error_code: str = "ADAPTER_BUG",
    ) -> None:
        """Configure a specific call to raise NexusBugError."""

        def raise_error(_args: Dict[str, Any]) -> Dict[str, Any]:
            raise NexusBugError(message, error_code=error_code)

        self._responses[(tool, method)] = raise_error

    def call(self, tool: str, method: str, args: Dict[str, Any]) -> Dict[str, Any]:
        """Execute the configured response."""
        # Log the call
        self._call_log.append({"tool": tool, "method": method, "args": args})

        # Check for specific response
        key = (tool, method)
        if key in self._responses:
            return self._responses[key](args)

        # Check for default response
        if self._default_response is not None:
            return self._default_response(tool, method, args)

        # No response configured - return placeholder
        return {
            "fake": True,
            "tool": tool,
            "method": method,
            "args_echo": args,
            "result": None,
        }

    def reset(self) -> None:
        """Clear all configured responses and call log."""
        self._responses.clear()
        self._default_response = None
        self._call_log.clear()


class SubprocessAdapter:
    """
    Adapter that calls external commands via subprocess.

    Executes tool calls by invoking a base command with:
        <base_cmd> call <tool> <method> --json-args-file <path>

    The external command must:
    - Read JSON payload from the args file
    - Print JSON result to stdout on success
    - Exit with 0 on success, non-zero on failure

    All failures are mapped to NexusOperationalError (not bugs).

    Security features (v0.5.1+):
    - Redaction hooks to prevent secrets in events/errors
    - Separate stdout/stderr capture limits
    - Temp file permissions (0o600 on POSIX)
    - Cleanup retry with diagnostic tracking
    """

    # Callable type aliases for redaction hooks
    RedactArgsFunc = Callable[[Dict[str, Any]], Dict[str, Any]]
    RedactTextFunc = Callable[[str], str]

    def __init__(
        self,
        base_cmd: List[str],
        *,
        adapter_id: Optional[str] = None,
        timeout_s: float = 30.0,
        cwd: Optional[str] = None,
        env: Optional[Dict[str, str]] = None,
        max_stdout_chars: int = 200_000,
        max_stderr_chars: int = 50_000,
        redact_args: Optional[RedactArgsFunc] = None,
        redact_text: Optional[RedactTextFunc] = None,
        cleanup_retry_delay_s: float = 0.1,
    ) -> None:
        """
        Initialize SubprocessAdapter.

        Args:
            base_cmd: Base command as list (e.g., ["python", "-m", "mcpt.cli"])
            adapter_id: Optional custom adapter ID. If None, derived from base_cmd.
            timeout_s: Timeout for subprocess execution in seconds.
            cwd: Working directory for subprocess.
            env: Environment variables (merged with os.environ).
            max_stdout_chars: Max chars to capture from stdout (for diagnostics).
            max_stderr_chars: Max chars to capture from stderr (for diagnostics).
            redact_args: Function to redact sensitive args before storing in events.
                        If None, uses default_redact_args. Pass lambda x: x to disable.
            redact_text: Function to redact sensitive text in output/errors.
                        If None, uses default_redact_text. Pass lambda x: x to disable.
            cleanup_retry_delay_s: Delay before retry if temp file cleanup fails.
        """
        if not base_cmd:
            raise ValueError("base_cmd must not be empty")

        self._base_cmd = list(base_cmd)
        self._timeout_s = timeout_s
        self._cwd = cwd
        self._env = env
        self._max_stdout_chars = max_stdout_chars
        self._max_stderr_chars = max_stderr_chars
        self._cleanup_retry_delay_s = cleanup_retry_delay_s

        # Redaction hooks (default to built-in redactors)
        self._redact_args: SubprocessAdapter.RedactArgsFunc = (
            redact_args if redact_args is not None else default_redact_args
        )
        self._redact_text: SubprocessAdapter.RedactTextFunc = (
            redact_text if redact_text is not None else default_redact_text
        )

        # Track last cleanup status for diagnostics
        self._last_cleanup_failed: bool = False

        # Derive adapter_id if not provided
        if adapter_id is not None:
            self._adapter_id = adapter_id
        else:
            self._adapter_id = self._derive_adapter_id()

    def _derive_adapter_id(self) -> str:
        """Derive a stable adapter ID from base_cmd."""
        first_token = os.path.basename(self._base_cmd[0])
        # Add short hash of full command for uniqueness
        cmd_str = " ".join(self._base_cmd)
        cmd_hash = hashlib.sha256(cmd_str.encode()).hexdigest()[:6]
        return f"subprocess:{first_token}:{cmd_hash}"

    @property
    def adapter_id(self) -> str:
        return self._adapter_id

    @property
    def last_cleanup_failed(self) -> bool:
        """True if the last temp file cleanup failed (diagnostic)."""
        return self._last_cleanup_failed

    def redact_args_for_event(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Apply redaction to args for event storage."""
        return self._redact_args(args)

    def redact_text_for_event(self, text: str) -> str:
        """Apply redaction to text for event storage."""
        return self._redact_text(text)

    def call(self, tool: str, method: str, args: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute a tool call via subprocess.

        Returns:
            Parsed JSON result from stdout.

        Raises:
            NexusOperationalError: For timeout, non-zero exit, or invalid JSON output.
        """
        self._last_cleanup_failed = False

        # Build payload (full args for the subprocess, NOT redacted)
        payload = {
            "tool": tool,
            "method": method,
            "args": args,
        }
        payload_json = json.dumps(payload, sort_keys=True, separators=(",", ":"))

        # Write payload to temp file
        args_file_path: Optional[str] = None
        try:
            # Create temp file with identifiable prefix
            fd, args_file_path = tempfile.mkstemp(
                suffix=".json", prefix="nexus-router-args-"
            )
            try:
                os.write(fd, payload_json.encode("utf-8"))
            finally:
                os.close(fd)

            # Set restrictive permissions on POSIX (best-effort)
            self._secure_temp_file(args_file_path)

            # Build command
            cmd = self._base_cmd + ["call", tool, method, "--json-args-file", args_file_path]

            # Validate cwd if specified
            if self._cwd is not None:
                self._validate_cwd(self._cwd)

            # Prepare environment
            run_env: Optional[Dict[str, str]] = None
            if self._env is not None:
                self._validate_env(self._env)
                run_env = {**os.environ, **self._env}

            # Execute
            try:
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=self._timeout_s,
                    cwd=self._cwd,
                    env=run_env,
                    shell=False,
                )
            except subprocess.TimeoutExpired as e:
                raise NexusOperationalError(
                    f"Command timed out after {self._timeout_s}s",
                    error_code="TIMEOUT",
                    details={"timeout_s": self._timeout_s},
                ) from e
            except FileNotFoundError as e:
                raise NexusOperationalError(
                    f"Command not found: {self._base_cmd[0]}",
                    error_code="COMMAND_NOT_FOUND",
                ) from e
            except PermissionError as e:
                raise NexusOperationalError(
                    f"Permission denied executing command: {self._base_cmd[0]}",
                    error_code="PERMISSION_DENIED",
                ) from e
            except OSError as e:
                # Map specific errno values
                if e.errno == errno.EACCES:
                    raise NexusOperationalError(
                        f"Permission denied: {e}",
                        error_code="PERMISSION_DENIED",
                    ) from e
                raise NexusOperationalError(
                    f"OS error executing command: {e}",
                    error_code="OS_ERROR",
                ) from e

            # Check exit code
            if result.returncode != 0:
                stderr_excerpt = self._truncate_stderr(result.stderr)
                raise NexusOperationalError(
                    f"Command exited with code {result.returncode}",
                    error_code="NONZERO_EXIT",
                    details={
                        "returncode": result.returncode,
                        "stderr_excerpt": self._redact_text(stderr_excerpt),
                    },
                )

            # Parse JSON output (use full stdout, not truncated)
            try:
                output = json.loads(result.stdout)
            except json.JSONDecodeError as e:
                # Include first/last chars for debugging
                stdout_excerpt = self._excerpt_for_json_error(result.stdout)
                raise NexusOperationalError(
                    f"Invalid JSON output: {e}",
                    error_code="INVALID_JSON_OUTPUT",
                    details={"stdout_excerpt": self._redact_text(stdout_excerpt)},
                ) from e

            if not isinstance(output, dict):
                raise NexusOperationalError(
                    f"Output is not a JSON object: {type(output).__name__}",
                    error_code="INVALID_JSON_OUTPUT",
                )

            return output

        finally:
            # Clean up temp file with retry
            if args_file_path is not None:
                self._cleanup_temp_file(args_file_path)

    def _secure_temp_file(self, path: str) -> None:
        """Set restrictive permissions on temp file (POSIX only, best-effort)."""
        if os.name == "posix":
            try:
                os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)  # 0o600
            except OSError:
                pass  # Best effort

    def _validate_cwd(self, cwd: str) -> None:
        """Validate working directory exists and is a directory."""
        if not os.path.exists(cwd):
            raise NexusOperationalError(
                f"Working directory not found: {cwd}",
                error_code="CWD_NOT_FOUND",
            )
        if not os.path.isdir(cwd):
            raise NexusOperationalError(
                f"Working directory is not a directory: {cwd}",
                error_code="CWD_NOT_DIRECTORY",
            )

    def _validate_env(self, env: Dict[str, str]) -> None:
        """Validate environment variables are all strings."""
        for key, value in env.items():
            if not isinstance(key, str) or not isinstance(value, str):
                raise NexusOperationalError(
                    "Invalid env variable: key and value must be strings",
                    error_code="ENV_INVALID",
                    details={"key": str(key), "value_type": type(value).__name__},
                )

    def _cleanup_temp_file(self, path: str) -> None:
        """Clean up temp file with one retry on failure."""
        try:
            os.remove(path)
            return
        except OSError:
            pass  # First attempt failed, retry

        # Retry after short delay (helps on Windows with file locks)
        time.sleep(self._cleanup_retry_delay_s)
        try:
            os.remove(path)
        except OSError:
            self._last_cleanup_failed = True
            # Don't fail the run, just track for diagnostics

    def _truncate_stdout(self, text: str) -> str:
        """Truncate stdout to max_stdout_chars."""
        if len(text) <= self._max_stdout_chars:
            return text
        return text[: self._max_stdout_chars] + f"... [truncated at {self._max_stdout_chars}]"

    def _truncate_stderr(self, text: str) -> str:
        """Truncate stderr to max_stderr_chars."""
        if len(text) <= self._max_stderr_chars:
            return text
        return text[: self._max_stderr_chars] + f"... [truncated at {self._max_stderr_chars}]"

    def _excerpt_for_json_error(self, text: str, head: int = 200, tail: int = 100) -> str:
        """
        Create excerpt showing first and last chars for JSON parse error debugging.

        For large invalid JSON output, shows head...tail for context.
        """
        if len(text) <= head + tail + 20:
            return text
        return f"{text[:head]}... [{len(text) - head - tail} chars] ...{text[-tail:]}"
