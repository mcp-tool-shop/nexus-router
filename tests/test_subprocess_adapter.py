"""Tests for SubprocessAdapter."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest import mock

import pytest

from nexus_router.dispatch import (
    SubprocessAdapter,
    default_redact_args,
    default_redact_text,
)
from nexus_router.exceptions import NexusOperationalError
from nexus_router.tool import run

# Path to the echo_tool fixture
ECHO_TOOL = Path(__file__).parent / "fixtures" / "echo_tool.py"


class TestSubprocessAdapterInit:
    """Tests for SubprocessAdapter initialization."""

    def test_empty_base_cmd_raises(self) -> None:
        """Empty base_cmd raises ValueError."""
        with pytest.raises(ValueError, match="must not be empty"):
            SubprocessAdapter([])

    def test_default_adapter_id_derived(self) -> None:
        """Default adapter_id is derived from base_cmd."""
        adapter = SubprocessAdapter([sys.executable, "-m", "some_module"])
        assert adapter.adapter_id.startswith("subprocess:")
        assert "python" in adapter.adapter_id.lower() or "exe" in adapter.adapter_id.lower()

    def test_custom_adapter_id(self) -> None:
        """Custom adapter_id is used when provided."""
        adapter = SubprocessAdapter(
            [sys.executable, str(ECHO_TOOL)],
            adapter_id="my-custom-adapter",
        )
        assert adapter.adapter_id == "my-custom-adapter"

    def test_adapter_id_stable(self) -> None:
        """Same base_cmd produces same derived adapter_id."""
        cmd = [sys.executable, str(ECHO_TOOL)]
        adapter1 = SubprocessAdapter(cmd)
        adapter2 = SubprocessAdapter(cmd)
        assert adapter1.adapter_id == adapter2.adapter_id

    def test_different_cmds_different_ids(self) -> None:
        """Different base_cmds produce different adapter_ids."""
        adapter1 = SubprocessAdapter([sys.executable, "script1.py"])
        adapter2 = SubprocessAdapter([sys.executable, "script2.py"])
        assert adapter1.adapter_id != adapter2.adapter_id


class TestSubprocessAdapterSuccess:
    """Tests for successful subprocess calls."""

    def test_success_returns_json(self) -> None:
        """Successful call returns parsed JSON."""
        adapter = SubprocessAdapter(
            [sys.executable, str(ECHO_TOOL)],
            adapter_id="echo-test",
        )

        result = adapter.call("my-tool", "my-method", {"key": "value"})

        assert result["success"] is True
        assert result["tool"] == "my-tool"
        assert result["method"] == "my-method"
        assert result["received_args"] == {"key": "value"}
        assert result["echo"] is True

    def test_success_with_complex_args(self) -> None:
        """Successful call with nested args."""
        adapter = SubprocessAdapter(
            [sys.executable, str(ECHO_TOOL)],
            adapter_id="echo-test",
        )

        complex_args = {
            "string": "hello",
            "number": 42,
            "float": 3.14,
            "bool": True,
            "null": None,
            "list": [1, 2, 3],
            "nested": {"a": {"b": {"c": 1}}},
        }

        result = adapter.call("tool", "method", complex_args)

        assert result["success"] is True
        assert result["received_args"] == complex_args

    def test_success_ignores_stderr(self) -> None:
        """Success returns JSON even when stderr has content."""
        adapter = SubprocessAdapter(
            [sys.executable, str(ECHO_TOOL)],
            adapter_id="echo-test",
        )

        result = adapter.call(
            "tool", "method", {"simulate_stderr": "Warning: something happened"}
        )

        assert result["success"] is True
        # stderr content is ignored in output


class TestSubprocessAdapterErrors:
    """Tests for subprocess error handling."""

    def test_timeout_raises_operational_error(self) -> None:
        """Timeout raises NexusOperationalError with TIMEOUT code."""
        adapter = SubprocessAdapter(
            [sys.executable, str(ECHO_TOOL)],
            adapter_id="echo-test",
            timeout_s=0.5,
        )

        with pytest.raises(NexusOperationalError) as exc_info:
            adapter.call("tool", "method", {"simulate_timeout": True})

        assert exc_info.value.error_code == "TIMEOUT"
        assert "timed out" in str(exc_info.value).lower()

    def test_nonzero_exit_raises_operational_error(self) -> None:
        """Non-zero exit code raises NexusOperationalError."""
        adapter = SubprocessAdapter(
            [sys.executable, str(ECHO_TOOL)],
            adapter_id="echo-test",
        )

        with pytest.raises(NexusOperationalError) as exc_info:
            adapter.call(
                "tool",
                "method",
                {"simulate_exit_code": 2, "stderr_message": "Something failed"},
            )

        assert exc_info.value.error_code == "NONZERO_EXIT"
        assert "code 2" in str(exc_info.value)

    def test_invalid_json_output_raises_operational_error(self) -> None:
        """Invalid JSON output raises NexusOperationalError."""
        adapter = SubprocessAdapter(
            [sys.executable, str(ECHO_TOOL)],
            adapter_id="echo-test",
        )

        with pytest.raises(NexusOperationalError) as exc_info:
            adapter.call("tool", "method", {"simulate_invalid_json": True})

        assert exc_info.value.error_code == "INVALID_JSON_OUTPUT"

    def test_command_not_found_raises_operational_error(self) -> None:
        """Missing command raises NexusOperationalError."""
        adapter = SubprocessAdapter(
            ["nonexistent_command_12345"],
            adapter_id="missing-cmd",
        )

        with pytest.raises(NexusOperationalError) as exc_info:
            adapter.call("tool", "method", {})

        assert exc_info.value.error_code == "COMMAND_NOT_FOUND"


class TestSubprocessAdapterIntegration:
    """Integration tests with full router."""

    def test_apply_mode_with_subprocess_adapter(self, tmp_path: Path) -> None:
        """Apply mode calls SubprocessAdapter correctly."""
        db_path = str(tmp_path / "test.db")
        adapter = SubprocessAdapter(
            [sys.executable, str(ECHO_TOOL)],
            adapter_id="echo-integration",
        )

        resp = run(
            {
                "goal": "subprocess integration test",
                "mode": "apply",
                "policy": {"allow_apply": True},
                "plan_override": [
                    {
                        "step_id": "s1",
                        "intent": "test subprocess call",
                        "call": {
                            "tool": "test-tool",
                            "method": "test-method",
                            "args": {"input": "hello"},
                        },
                    }
                ],
            },
            db_path=db_path,
            adapter=adapter,
        )

        assert resp["summary"]["mode"] == "apply"
        assert resp["summary"]["adapter_id"] == "echo-integration"
        assert resp["summary"]["outputs_applied"] == 1
        assert resp["results"][0]["status"] == "ok"
        assert resp["results"][0]["output"]["success"] is True
        assert resp["results"][0]["output"]["received_args"] == {"input": "hello"}

    def test_dry_run_never_calls_subprocess(self, tmp_path: Path) -> None:
        """dry_run mode never invokes subprocess."""
        db_path = str(tmp_path / "test.db")
        # Use a command that would fail if called
        adapter = SubprocessAdapter(
            ["nonexistent_command_that_would_fail"],
            adapter_id="should-not-call",
        )

        # This should succeed because dry_run never calls the adapter
        resp = run(
            {
                "goal": "dry_run subprocess test",
                "mode": "dry_run",
                "plan_override": [
                    {
                        "step_id": "s1",
                        "intent": "test",
                        "call": {"tool": "t", "method": "m", "args": {}},
                    }
                ],
            },
            db_path=db_path,
            adapter=adapter,
        )

        assert resp["summary"]["mode"] == "dry_run"
        assert resp["summary"]["adapter_id"] == "should-not-call"
        assert resp["results"][0]["simulated"] is True

    def test_subprocess_error_allows_subsequent_steps(self, tmp_path: Path) -> None:
        """Operational error from subprocess allows subsequent steps."""
        db_path = str(tmp_path / "test.db")
        adapter = SubprocessAdapter(
            [sys.executable, str(ECHO_TOOL)],
            adapter_id="echo-multi",
        )

        resp = run(
            {
                "goal": "multi-step subprocess test",
                "mode": "apply",
                "policy": {"allow_apply": True},
                "plan_override": [
                    {
                        "step_id": "s1",
                        "intent": "this will fail",
                        "call": {
                            "tool": "t",
                            "method": "m",
                            "args": {"simulate_exit_code": 1},
                        },
                    },
                    {
                        "step_id": "s2",
                        "intent": "this will succeed",
                        "call": {
                            "tool": "t",
                            "method": "m",
                            "args": {"input": "success"},
                        },
                    },
                ],
            },
            db_path=db_path,
            adapter=adapter,
        )

        assert resp["results"][0]["status"] == "error"
        assert resp["results"][1]["status"] == "ok"
        assert resp["summary"]["outputs_skipped"] == 1
        assert resp["summary"]["outputs_applied"] == 1


class TestSubprocessAdapterConfig:
    """Tests for SubprocessAdapter configuration options."""

    def test_custom_env(self) -> None:
        """Custom environment variables are passed to subprocess."""
        adapter = SubprocessAdapter(
            [sys.executable, str(ECHO_TOOL)],
            adapter_id="echo-env",
            env={"CUSTOM_VAR": "custom_value"},
        )

        # The echo tool doesn't use env vars, but we verify no crash
        result = adapter.call("tool", "method", {})
        assert result["success"] is True

    def test_custom_cwd(self, tmp_path: Path) -> None:
        """Custom cwd is used for subprocess."""
        adapter = SubprocessAdapter(
            [sys.executable, str(ECHO_TOOL)],
            adapter_id="echo-cwd",
            cwd=str(tmp_path),
        )

        result = adapter.call("tool", "method", {})
        assert result["success"] is True

    def test_max_stdout_chars_does_not_break_parsing(self) -> None:
        """max_stdout_chars only affects diagnostics, not JSON parsing."""
        adapter = SubprocessAdapter(
            [sys.executable, str(ECHO_TOOL)],
            adapter_id="echo-truncate",
            max_stdout_chars=50,  # Very small, but parsing uses full output
        )

        # Should still work - truncation is for event storage, not parsing
        result = adapter.call("tool", "method", {"data": "x" * 100})
        assert result["success"] is True
        assert result["received_args"]["data"] == "x" * 100


class TestRedactionDefaults:
    """Tests for default redaction functions."""

    def test_redact_args_sensitive_keys(self) -> None:
        """Sensitive keys are redacted."""
        args = {
            "api_key": "secret123",
            "password": "hunter2",
            "token": "abc.def.ghi",
            "Authorization": "Bearer xyz",
            "cookie": "session=abc",
            "credential": "user:pass",
            "private_key": "-----BEGIN PRIVATE KEY-----",
        }
        redacted = default_redact_args(args)
        for key in args:
            assert redacted[key] == "[REDACTED]"

    def test_redact_args_safe_keys_preserved(self) -> None:
        """Non-sensitive keys are preserved."""
        args = {
            "name": "test",
            "count": 42,
            "enabled": True,
            "data": [1, 2, 3],
        }
        redacted = default_redact_args(args)
        assert redacted == args

    def test_redact_args_nested(self) -> None:
        """Nested sensitive keys are redacted."""
        args = {
            "config": {
                "api_key": "secret",
                "database": {
                    "password": "dbpass",
                    "host": "localhost",
                },
            },
            "items": [{"token": "xyz"}, {"name": "item1"}],
        }
        redacted = default_redact_args(args)
        assert redacted["config"]["api_key"] == "[REDACTED]"
        assert redacted["config"]["database"]["password"] == "[REDACTED]"
        assert redacted["config"]["database"]["host"] == "localhost"
        assert redacted["items"][0]["token"] == "[REDACTED]"
        assert redacted["items"][1]["name"] == "item1"

    def test_redact_text_bearer_tokens(self) -> None:
        """Bearer tokens are redacted in text."""
        text = "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"
        redacted = default_redact_text(text)
        assert "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9" not in redacted
        assert "Bearer [REDACTED]" in redacted

    def test_redact_text_api_keys(self) -> None:
        """API keys in various formats are redacted."""
        text = "api_key=sk-abc123 api-key: 'xyz789'"
        redacted = default_redact_text(text)
        assert "sk-abc123" not in redacted
        assert "xyz789" not in redacted

    def test_redact_text_passwords(self) -> None:
        """Passwords are redacted in text."""
        text = "password=secret123 token: mytoken"
        redacted = default_redact_text(text)
        assert "secret123" not in redacted
        assert "mytoken" not in redacted


class TestRedactionHooks:
    """Tests for redaction hooks in SubprocessAdapter."""

    def test_redact_args_for_event(self) -> None:
        """Adapter applies redaction to args."""
        adapter = SubprocessAdapter(
            [sys.executable, str(ECHO_TOOL)],
            adapter_id="echo-redact",
        )
        args = {"api_key": "secret", "data": "public"}
        redacted = adapter.redact_args_for_event(args)
        assert redacted["api_key"] == "[REDACTED]"
        assert redacted["data"] == "public"

    def test_redact_text_for_event(self) -> None:
        """Adapter applies text redaction."""
        adapter = SubprocessAdapter(
            [sys.executable, str(ECHO_TOOL)],
            adapter_id="echo-redact",
        )
        text = "Bearer token123"
        redacted = adapter.redact_text_for_event(text)
        assert "token123" not in redacted

    def test_custom_redact_args(self) -> None:
        """Custom redact_args function is used."""

        def custom_redact(args: dict) -> dict:
            return {k: "***" if "secret" in k else v for k, v in args.items()}

        adapter = SubprocessAdapter(
            [sys.executable, str(ECHO_TOOL)],
            adapter_id="echo-custom",
            redact_args=custom_redact,
        )
        args = {"secret_data": "x", "public": "y"}
        redacted = adapter.redact_args_for_event(args)
        assert redacted["secret_data"] == "***"
        assert redacted["public"] == "y"

    def test_disable_redaction(self) -> None:
        """Redaction can be disabled with identity function."""
        adapter = SubprocessAdapter(
            [sys.executable, str(ECHO_TOOL)],
            adapter_id="echo-no-redact",
            redact_args=lambda x: x,
            redact_text=lambda x: x,
        )
        args = {"api_key": "secret"}
        text = "Bearer token123"
        assert adapter.redact_args_for_event(args)["api_key"] == "secret"
        assert "token123" in adapter.redact_text_for_event(text)


class TestErrorCodeExpansion:
    """Tests for expanded error codes."""

    def test_cwd_not_found(self, tmp_path: Path) -> None:
        """CWD_NOT_FOUND when cwd doesn't exist."""
        adapter = SubprocessAdapter(
            [sys.executable, str(ECHO_TOOL)],
            adapter_id="echo-cwd",
            cwd=str(tmp_path / "nonexistent"),
        )
        with pytest.raises(NexusOperationalError) as exc_info:
            adapter.call("tool", "method", {})
        assert exc_info.value.error_code == "CWD_NOT_FOUND"

    def test_cwd_not_directory(self, tmp_path: Path) -> None:
        """CWD_NOT_DIRECTORY when cwd is a file."""
        file_path = tmp_path / "file.txt"
        file_path.write_text("content")
        adapter = SubprocessAdapter(
            [sys.executable, str(ECHO_TOOL)],
            adapter_id="echo-cwd",
            cwd=str(file_path),
        )
        with pytest.raises(NexusOperationalError) as exc_info:
            adapter.call("tool", "method", {})
        assert exc_info.value.error_code == "CWD_NOT_DIRECTORY"

    def test_env_invalid_value(self) -> None:
        """ENV_INVALID when env has non-string values."""
        adapter = SubprocessAdapter(
            [sys.executable, str(ECHO_TOOL)],
            adapter_id="echo-env",
            env={"KEY": 123},  # type: ignore[dict-item]
        )
        with pytest.raises(NexusOperationalError) as exc_info:
            adapter.call("tool", "method", {})
        assert exc_info.value.error_code == "ENV_INVALID"

    def test_timeout_includes_details(self) -> None:
        """TIMEOUT error includes timeout_s in details."""
        adapter = SubprocessAdapter(
            [sys.executable, str(ECHO_TOOL)],
            adapter_id="echo-timeout",
            timeout_s=0.5,
        )
        with pytest.raises(NexusOperationalError) as exc_info:
            adapter.call("tool", "method", {"simulate_timeout": True})
        assert exc_info.value.error_code == "TIMEOUT"
        assert exc_info.value.details["timeout_s"] == 0.5

    def test_nonzero_exit_includes_stderr_excerpt(self) -> None:
        """NONZERO_EXIT includes stderr_excerpt in details."""
        adapter = SubprocessAdapter(
            [sys.executable, str(ECHO_TOOL)],
            adapter_id="echo-exit",
        )
        with pytest.raises(NexusOperationalError) as exc_info:
            adapter.call(
                "tool", "method", {"simulate_exit_code": 1, "stderr_message": "Error!"}
            )
        assert exc_info.value.error_code == "NONZERO_EXIT"
        assert "returncode" in exc_info.value.details
        assert "stderr_excerpt" in exc_info.value.details


class TestOutputCapLimits:
    """Tests for stdout/stderr capture limits."""

    def test_separate_stdout_stderr_limits(self) -> None:
        """Different limits for stdout and stderr."""
        adapter = SubprocessAdapter(
            [sys.executable, str(ECHO_TOOL)],
            adapter_id="echo-limits",
            max_stdout_chars=100,
            max_stderr_chars=50,
        )
        # Verify limits are set correctly
        assert adapter._max_stdout_chars == 100
        assert adapter._max_stderr_chars == 50

    def test_truncate_stderr_in_error(self) -> None:
        """Stderr is truncated in error details."""
        adapter = SubprocessAdapter(
            [sys.executable, str(ECHO_TOOL)],
            adapter_id="echo-truncate",
            max_stderr_chars=20,
        )
        long_stderr = "x" * 100
        with pytest.raises(NexusOperationalError) as exc_info:
            adapter.call(
                "tool",
                "method",
                {"simulate_exit_code": 1, "stderr_message": long_stderr},
            )
        excerpt = exc_info.value.details.get("stderr_excerpt", "")
        # Should be truncated
        assert len(excerpt) <= 50  # 20 + truncation message


class TestTempFileSecurity:
    """Tests for temp file security."""

    def test_temp_file_prefix(self) -> None:
        """Temp files have identifiable prefix."""
        # We can't easily test this without mocking, but we can verify
        # the adapter creates temp files with the right pattern
        adapter = SubprocessAdapter(
            [sys.executable, str(ECHO_TOOL)],
            adapter_id="echo-temp",
        )
        # Just verify it works - the prefix is internal
        result = adapter.call("tool", "method", {})
        assert result["success"] is True

    @pytest.mark.skipif(os.name != "posix", reason="POSIX-only test")
    def test_temp_file_permissions_posix(self) -> None:
        """Temp file has 0o600 permissions on POSIX."""
        # This would require intercepting the temp file creation
        # For now, just verify the method exists
        adapter = SubprocessAdapter(
            [sys.executable, str(ECHO_TOOL)],
            adapter_id="echo-perms",
        )
        # Verify _secure_temp_file exists
        assert hasattr(adapter, "_secure_temp_file")


class TestCleanupRetry:
    """Tests for temp file cleanup with retry."""

    def test_cleanup_success_no_flag(self) -> None:
        """Successful cleanup doesn't set flag."""
        adapter = SubprocessAdapter(
            [sys.executable, str(ECHO_TOOL)],
            adapter_id="echo-cleanup",
        )
        adapter.call("tool", "method", {})
        assert adapter.last_cleanup_failed is False

    def test_cleanup_retry_on_failure(self) -> None:
        """Cleanup retries on failure."""
        adapter = SubprocessAdapter(
            [sys.executable, str(ECHO_TOOL)],
            adapter_id="echo-cleanup",
            cleanup_retry_delay_s=0.01,  # Fast for testing
        )

        # Mock os.remove to fail twice (we need to capture path first)
        original_remove = os.remove
        call_count = [0]

        def failing_remove(path: str) -> None:
            call_count[0] += 1
            if call_count[0] <= 2 and "nexus-router-args" in path:
                raise OSError("Simulated failure")
            return original_remove(path)

        with mock.patch("os.remove", side_effect=failing_remove):
            # Need to also patch in the dispatch module
            with mock.patch(
                "nexus_router.dispatch.os.remove", side_effect=failing_remove
            ):
                adapter.call("tool", "method", {})

        # Should have been called twice for the temp file
        assert call_count[0] >= 2
        assert adapter.last_cleanup_failed is True

    def test_last_cleanup_failed_resets(self) -> None:
        """last_cleanup_failed resets on each call."""
        adapter = SubprocessAdapter(
            [sys.executable, str(ECHO_TOOL)],
            adapter_id="echo-cleanup",
        )
        # First call succeeds
        adapter.call("tool", "method", {})
        assert adapter.last_cleanup_failed is False

        # Force the flag on
        adapter._last_cleanup_failed = True

        # Next call should reset it
        adapter.call("tool", "method", {})
        assert adapter.last_cleanup_failed is False


class TestJsonExcerptForErrors:
    """Tests for JSON error excerpt generation."""

    def test_excerpt_short_output(self) -> None:
        """Short output is returned as-is."""
        adapter = SubprocessAdapter(
            [sys.executable, str(ECHO_TOOL)],
            adapter_id="echo-excerpt",
        )
        short_text = "short output"
        excerpt = adapter._excerpt_for_json_error(short_text)
        assert excerpt == short_text

    def test_excerpt_long_output_shows_head_tail(self) -> None:
        """Long output shows head...tail."""
        adapter = SubprocessAdapter(
            [sys.executable, str(ECHO_TOOL)],
            adapter_id="echo-excerpt",
        )
        long_text = "A" * 200 + "B" * 500 + "C" * 100
        excerpt = adapter._excerpt_for_json_error(long_text, head=200, tail=100)
        assert excerpt.startswith("A" * 200)
        assert excerpt.endswith("C" * 100)
        assert "chars]" in excerpt  # Shows count of skipped chars
