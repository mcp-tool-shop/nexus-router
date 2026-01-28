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
from typing import Any, Callable, Dict, FrozenSet, List, Optional, Protocol, Tuple

from .exceptions import NexusBugError, NexusOperationalError


# Standard capability constants
CAPABILITY_DRY_RUN = "dry_run"  # Adapter supports dry_run mode (simulated output)
CAPABILITY_APPLY = "apply"  # Adapter supports apply mode (real execution)
CAPABILITY_TIMEOUT = "timeout"  # Adapter enforces timeouts
CAPABILITY_EXTERNAL = "external"  # Adapter calls external systems

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

    Platform rules (v0.6+):
    - Adapters must not mutate global state
    - Adapters must be deterministic given args
    - Adapters must not swallow bugs
    - Adapters must declare capabilities
    - Adapters must tolerate replayed calls being skipped
    """

    @property
    def adapter_id(self) -> str:
        """Unique identifier for this adapter instance."""
        ...

    @property
    def capabilities(self) -> FrozenSet[str]:
        """
        Declared capabilities of this adapter.

        Standard capabilities:
        - "dry_run": Supports simulated execution
        - "apply": Supports real execution
        - "timeout": Enforces timeouts
        - "external": Calls external systems
        """
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


class AdapterRegistry:
    """
    Registry of dispatch adapters.

    Enables multiple adapters in one process without global state.
    Provides adapter lookup by ID and capability-based selection.

    Usage:
        registry = AdapterRegistry()
        registry.register(NullAdapter())
        registry.register(SubprocessAdapter([...]))

        run(request, db_path, adapters=registry)
    """

    def __init__(self, default_adapter_id: str = "null") -> None:
        """
        Initialize registry.

        Args:
            default_adapter_id: Adapter to use when none specified in request.
        """
        self._adapters: Dict[str, DispatchAdapter] = {}
        self._default_adapter_id = default_adapter_id

    @property
    def default_adapter_id(self) -> str:
        """The default adapter ID used when none specified."""
        return self._default_adapter_id

    def register(self, adapter: DispatchAdapter) -> None:
        """
        Register an adapter.

        Args:
            adapter: Adapter to register.

        Raises:
            ValueError: If adapter_id is already registered.
        """
        if adapter.adapter_id in self._adapters:
            raise ValueError(f"Adapter already registered: {adapter.adapter_id}")
        self._adapters[adapter.adapter_id] = adapter

    def get(self, adapter_id: str) -> DispatchAdapter:
        """
        Get adapter by ID.

        Args:
            adapter_id: Adapter ID to look up.

        Returns:
            The adapter.

        Raises:
            KeyError: If adapter not found.
        """
        try:
            return self._adapters[adapter_id]
        except KeyError:
            raise KeyError(f"Unknown adapter: {adapter_id}") from None

    def get_default(self) -> DispatchAdapter:
        """Get the default adapter."""
        return self.get(self._default_adapter_id)

    def list_ids(self) -> List[str]:
        """List all registered adapter IDs (sorted)."""
        return sorted(self._adapters.keys())

    def list_adapters(self) -> List[Dict[str, Any]]:
        """
        List all registered adapters with metadata.

        Returns:
            List of dicts with adapter_id and capabilities.
        """
        return [
            {
                "adapter_id": adapter.adapter_id,
                "capabilities": sorted(adapter.capabilities),
            }
            for adapter in sorted(
                self._adapters.values(), key=lambda a: a.adapter_id
            )
        ]

    def find_by_capability(self, capability: str) -> List[str]:
        """
        Find adapters with a specific capability.

        Args:
            capability: Capability to search for.

        Returns:
            List of adapter IDs that have the capability.
        """
        return [
            adapter_id
            for adapter_id, adapter in sorted(self._adapters.items())
            if capability in adapter.capabilities
        ]

    def has_capability(self, adapter_id: str, capability: str) -> bool:
        """
        Check if an adapter has a specific capability.

        Args:
            adapter_id: Adapter to check.
            capability: Capability to check for.

        Returns:
            True if adapter has capability.

        Raises:
            KeyError: If adapter not found.
        """
        return capability in self.get(adapter_id).capabilities

    def require_capability(self, adapter_id: str, capability: str) -> None:
        """
        Assert that an adapter has a required capability.

        Args:
            adapter_id: Adapter to check.
            capability: Required capability.

        Raises:
            KeyError: If adapter not found.
            NexusOperationalError: If capability not present.
        """
        if not self.has_capability(adapter_id, capability):
            raise NexusOperationalError(
                f"Adapter '{adapter_id}' lacks required capability: {capability}",
                error_code="CAPABILITY_MISSING",
                details={
                    "adapter_id": adapter_id,
                    "required_capability": capability,
                    "adapter_capabilities": sorted(self.get(adapter_id).capabilities),
                },
            )

    def __len__(self) -> int:
        return len(self._adapters)

    def __contains__(self, adapter_id: str) -> bool:
        return adapter_id in self._adapters


class NullAdapter:
    """
    Adapter that returns deterministic placeholder outputs.

    Used for:
    - dry_run mode (default)
    - Testing without external dependencies
    - Development/debugging

    Capabilities: dry_run
    """

    def __init__(self, adapter_id: str = "null") -> None:
        self._adapter_id = adapter_id
        self._capabilities: FrozenSet[str] = frozenset({CAPABILITY_DRY_RUN})

    @property
    def adapter_id(self) -> str:
        return self._adapter_id

    @property
    def capabilities(self) -> FrozenSet[str]:
        return self._capabilities

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

    Capabilities: dry_run, apply (for testing both modes)
    """

    def __init__(
        self,
        adapter_id: str = "fake",
        capabilities: Optional[FrozenSet[str]] = None,
    ) -> None:
        self._adapter_id = adapter_id
        self._capabilities: FrozenSet[str] = capabilities or frozenset(
            {CAPABILITY_DRY_RUN, CAPABILITY_APPLY}
        )
        self._responses: Dict[Tuple[str, str], Callable[..., Dict[str, Any]]] = {}
        self._default_response: Optional[Callable[..., Dict[str, Any]]] = None
        self._call_log: list[Dict[str, Any]] = []

    @property
    def adapter_id(self) -> str:
        return self._adapter_id

    @property
    def capabilities(self) -> FrozenSet[str]:
        return self._capabilities

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

    Hardening features (v0.5.2+):
    - strict_stderr mode: treat any stderr on success as failure
    - args_digest in all error details for correlation
    - Enhanced timeout/JSON error details

    Capabilities: apply, timeout, external
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
        strict_stderr: bool = False,
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
            strict_stderr: If True, treat non-empty stderr on success as failure.
                          Default False (ignore stderr on success).
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
        self._strict_stderr = strict_stderr
        self._capabilities: FrozenSet[str] = frozenset(
            {CAPABILITY_APPLY, CAPABILITY_TIMEOUT, CAPABILITY_EXTERNAL}
        )

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
    def capabilities(self) -> FrozenSet[str]:
        return self._capabilities

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

        # Compute args_digest for correlation (non-sensitive)
        args_digest = self._compute_args_digest(args)

        # Common error details (added to all errors)
        base_details = self._base_error_details(args_digest)

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
                # Enhanced timeout details
                details = {
                    **base_details,
                    "timeout_s": self._timeout_s,
                    "cmd_first_token": os.path.basename(self._base_cmd[0]),
                }
                if self._cwd:
                    details["cwd"] = self._cwd
                # Capture any partial output (may be None or bytes)
                if e.stdout is not None:
                    stdout_str = e.stdout if isinstance(e.stdout, str) else e.stdout.decode(
                        "utf-8", errors="replace"
                    )
                    details["stdout_excerpt"] = self._redact_text(
                        self._truncate_stdout(stdout_str)
                    )
                if e.stderr is not None:
                    stderr_str = e.stderr if isinstance(e.stderr, str) else e.stderr.decode(
                        "utf-8", errors="replace"
                    )
                    details["stderr_excerpt"] = self._redact_text(
                        self._truncate_stderr(stderr_str)
                    )
                raise NexusOperationalError(
                    f"Command timed out after {self._timeout_s}s",
                    error_code="TIMEOUT",
                    details=details,
                ) from e
            except FileNotFoundError as e:
                raise NexusOperationalError(
                    f"Command not found: {self._base_cmd[0]}",
                    error_code="COMMAND_NOT_FOUND",
                    details=base_details,
                ) from e
            except PermissionError as e:
                raise NexusOperationalError(
                    f"Permission denied executing command: {self._base_cmd[0]}",
                    error_code="PERMISSION_DENIED",
                    details=base_details,
                ) from e
            except OSError as e:
                # Map specific errno values
                if e.errno == errno.EACCES:
                    raise NexusOperationalError(
                        f"Permission denied: {e}",
                        error_code="PERMISSION_DENIED",
                        details=base_details,
                    ) from e
                raise NexusOperationalError(
                    f"OS error executing command: {e}",
                    error_code="OS_ERROR",
                    details=base_details,
                ) from e

            # Check exit code
            if result.returncode != 0:
                stderr_excerpt = self._truncate_stderr(result.stderr)
                raise NexusOperationalError(
                    f"Command exited with code {result.returncode}",
                    error_code="NONZERO_EXIT",
                    details={
                        **base_details,
                        "returncode": result.returncode,
                        "stderr_excerpt": self._redact_text(stderr_excerpt),
                    },
                )

            # Parse JSON output (use full stdout, not truncated)
            try:
                output = json.loads(result.stdout)
            except json.JSONDecodeError as e:
                # Enhanced JSON error details with head/tail/len
                stdout_len = len(result.stdout)
                details = {
                    **base_details,
                    "stdout_len": stdout_len,
                    "json_error": str(e),
                }
                # Add head/tail excerpts
                head, tail = self._excerpt_head_tail(result.stdout)
                details["stdout_head"] = self._redact_text(head)
                if tail:
                    details["stdout_tail"] = self._redact_text(tail)
                raise NexusOperationalError(
                    f"Invalid JSON output: {e}",
                    error_code="INVALID_JSON_OUTPUT",
                    details=details,
                ) from e

            if not isinstance(output, dict):
                raise NexusOperationalError(
                    f"Output is not a JSON object: {type(output).__name__}",
                    error_code="INVALID_JSON_OUTPUT",
                    details=base_details,
                )

            # Check strict_stderr AFTER successful JSON parse
            if self._strict_stderr and result.stderr.strip():
                stderr_excerpt = self._truncate_stderr(result.stderr)
                raise NexusOperationalError(
                    "Command produced stderr output (strict_stderr mode)",
                    error_code="STDERR_ON_SUCCESS",
                    details={
                        **base_details,
                        "stderr_excerpt": self._redact_text(stderr_excerpt),
                    },
                )

            return output

        finally:
            # Clean up temp file with retry
            if args_file_path is not None:
                self._cleanup_temp_file(args_file_path)

    def _compute_args_digest(self, args: Dict[str, Any]) -> str:
        """Compute SHA256 digest of canonical args JSON (first 12 hex chars)."""
        canonical = json.dumps(args, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode()).hexdigest()[:12]

    def _base_error_details(self, args_digest: str) -> Dict[str, Any]:
        """Build common error details included in all operational errors."""
        return {"args_digest": args_digest}

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
        Deprecated in v0.5.2 - use _excerpt_head_tail instead.
        """
        if len(text) <= head + tail + 20:
            return text
        return f"{text[:head]}... [{len(text) - head - tail} chars] ...{text[-tail:]}"

    def _excerpt_head_tail(
        self, text: str, head: int = 500, tail: int = 200
    ) -> Tuple[str, Optional[str]]:
        """
        Extract head and tail excerpts from text.

        Returns:
            (head_excerpt, tail_excerpt) where tail_excerpt is None if text is short.
        """
        if len(text) <= head + tail:
            return (text, None)
        return (text[:head], text[-tail:])
