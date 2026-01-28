"""Tests for dispatch adapters and error handling."""

from __future__ import annotations

from pathlib import Path

import pytest

from nexus_router.dispatch import FakeAdapter, NullAdapter
from nexus_router.exceptions import NexusBugError, NexusOperationalError
from nexus_router.tool import run


class TestNullAdapter:
    """Tests for NullAdapter."""

    def test_null_adapter_returns_simulated_output(self) -> None:
        """NullAdapter returns deterministic simulated output."""
        adapter = NullAdapter()
        result = adapter.call("test-tool", "test_method", {"arg": "value"})

        assert result["simulated"] is True
        assert result["tool"] == "test-tool"
        assert result["method"] == "test_method"
        assert result["args_echo"] == {"arg": "value"}

    def test_null_adapter_id(self) -> None:
        """NullAdapter has default ID 'null'."""
        adapter = NullAdapter()
        assert adapter.adapter_id == "null"

    def test_null_adapter_custom_id(self) -> None:
        """NullAdapter can have custom ID."""
        adapter = NullAdapter(adapter_id="custom-null")
        assert adapter.adapter_id == "custom-null"


class TestFakeAdapter:
    """Tests for FakeAdapter."""

    def test_fake_adapter_default_response(self) -> None:
        """FakeAdapter returns placeholder when no response configured."""
        adapter = FakeAdapter()
        result = adapter.call("tool", "method", {"x": 1})

        assert result["fake"] is True
        assert result["tool"] == "tool"
        assert result["method"] == "method"

    def test_fake_adapter_set_response_dict(self) -> None:
        """FakeAdapter returns configured dict response."""
        adapter = FakeAdapter()
        adapter.set_response("my-tool", "my_method", {"success": True, "value": 42})

        result = adapter.call("my-tool", "my_method", {})
        assert result == {"success": True, "value": 42}

    def test_fake_adapter_set_response_callable(self) -> None:
        """FakeAdapter calls configured callable."""
        adapter = FakeAdapter()
        adapter.set_response("tool", "echo", lambda args: {"echoed": args["msg"]})

        result = adapter.call("tool", "echo", {"msg": "hello"})
        assert result == {"echoed": "hello"}

    def test_fake_adapter_operational_error(self) -> None:
        """FakeAdapter can raise NexusOperationalError."""
        adapter = FakeAdapter()
        adapter.set_operational_error("tool", "fail", "timeout", error_code="TIMEOUT")

        with pytest.raises(NexusOperationalError) as exc_info:
            adapter.call("tool", "fail", {})

        assert str(exc_info.value) == "timeout"
        assert exc_info.value.error_code == "TIMEOUT"

    def test_fake_adapter_bug_error(self) -> None:
        """FakeAdapter can raise NexusBugError."""
        adapter = FakeAdapter()
        adapter.set_bug_error("tool", "buggy", "internal error", error_code="ADAPTER_BUG")

        with pytest.raises(NexusBugError) as exc_info:
            adapter.call("tool", "buggy", {})

        assert str(exc_info.value) == "internal error"
        assert exc_info.value.error_code == "ADAPTER_BUG"

    def test_fake_adapter_call_log(self) -> None:
        """FakeAdapter logs all calls."""
        adapter = FakeAdapter()
        adapter.call("t1", "m1", {"a": 1})
        adapter.call("t2", "m2", {"b": 2})

        assert len(adapter.call_log) == 2
        assert adapter.call_log[0] == {"tool": "t1", "method": "m1", "args": {"a": 1}}
        assert adapter.call_log[1] == {"tool": "t2", "method": "m2", "args": {"b": 2}}

    def test_fake_adapter_reset(self) -> None:
        """FakeAdapter.reset() clears responses and log."""
        adapter = FakeAdapter()
        adapter.set_response("tool", "method", {"x": 1})
        adapter.call("tool", "method", {})
        adapter.reset()

        assert len(adapter.call_log) == 0
        # Should return default placeholder now
        result = adapter.call("tool", "method", {})
        assert result["fake"] is True


class TestDispatchInDryRun:
    """Tests for dispatch behavior in dry_run mode."""

    def test_dry_run_never_calls_adapter(self, tmp_path: Path) -> None:
        """In dry_run mode, adapter.call() is never invoked."""
        db_path = str(tmp_path / "test.db")
        adapter = FakeAdapter()

        resp = run(
            {
                "goal": "dry run test",
                "mode": "dry_run",
                "plan_override": [
                    {
                        "step_id": "s1",
                        "intent": "test",
                        "call": {"tool": "my-tool", "method": "my_method", "args": {"x": 1}},
                    }
                ],
            },
            db_path=db_path,
            adapter=adapter,
        )

        # Adapter was never called
        assert len(adapter.call_log) == 0

        # But run completed successfully
        assert resp["summary"]["mode"] == "dry_run"
        assert resp["summary"]["steps"] == 1
        assert resp["summary"]["adapter_id"] == "fake"

        # Output shows simulated
        assert resp["results"][0]["simulated"] is True
        assert resp["results"][0]["output"]["simulated"] is True

    def test_dry_run_uses_adapter_id_in_events(self, tmp_path: Path) -> None:
        """dry_run records adapter_id even though it doesn't call adapter."""
        db_path = str(tmp_path / "test.db")
        adapter = FakeAdapter(adapter_id="my-fake-adapter")

        resp = run(
            {
                "goal": "adapter id test",
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

        assert resp["summary"]["adapter_id"] == "my-fake-adapter"
        assert resp["results"][0]["output"]["adapter_id"] == "my-fake-adapter"


class TestDispatchInApply:
    """Tests for dispatch behavior in apply mode."""

    def test_apply_calls_adapter(self, tmp_path: Path) -> None:
        """In apply mode, adapter.call() is invoked for each step."""
        db_path = str(tmp_path / "test.db")
        adapter = FakeAdapter()
        adapter.set_response("my-tool", "my_method", {"result": "success"})

        resp = run(
            {
                "goal": "apply test",
                "mode": "apply",
                "policy": {"allow_apply": True},
                "plan_override": [
                    {
                        "step_id": "s1",
                        "intent": "test",
                        "call": {"tool": "my-tool", "method": "my_method", "args": {"x": 1}},
                    }
                ],
            },
            db_path=db_path,
            adapter=adapter,
        )

        # Adapter was called once
        assert len(adapter.call_log) == 1
        assert adapter.call_log[0] == {
            "tool": "my-tool",
            "method": "my_method",
            "args": {"x": 1},
        }

        # Run completed successfully
        assert resp["summary"]["mode"] == "apply"
        assert resp["summary"]["outputs_applied"] == 1

        # Output contains adapter result
        assert resp["results"][0]["simulated"] is False
        assert resp["results"][0]["output"]["result"] == "success"

    def test_apply_multiple_steps(self, tmp_path: Path) -> None:
        """Apply mode calls adapter for each step in order."""
        db_path = str(tmp_path / "test.db")
        adapter = FakeAdapter()
        adapter.set_response("t", "step1", {"n": 1})
        adapter.set_response("t", "step2", {"n": 2})

        resp = run(
            {
                "goal": "multi-step apply",
                "mode": "apply",
                "policy": {"allow_apply": True},
                "plan_override": [
                    {
                        "step_id": "s1",
                        "intent": "first",
                        "call": {"tool": "t", "method": "step1", "args": {}},
                    },
                    {
                        "step_id": "s2",
                        "intent": "second",
                        "call": {"tool": "t", "method": "step2", "args": {}},
                    },
                ],
            },
            db_path=db_path,
            adapter=adapter,
        )

        assert len(adapter.call_log) == 2
        assert resp["summary"]["outputs_applied"] == 2
        assert resp["results"][0]["output"]["n"] == 1
        assert resp["results"][1]["output"]["n"] == 2


class TestOperationalErrors:
    """Tests for operational error handling."""

    def test_operational_error_fails_run_gracefully(self, tmp_path: Path) -> None:
        """Operational errors cause RUN_FAILED but don't raise."""
        db_path = str(tmp_path / "test.db")
        adapter = FakeAdapter()
        adapter.set_operational_error("tool", "fail_op", "connection timeout", "TIMEOUT")

        # Should NOT raise
        resp = run(
            {
                "goal": "operational error test",
                "mode": "apply",
                "policy": {"allow_apply": True},
                "plan_override": [
                    {
                        "step_id": "s1",
                        "intent": "will fail",
                        "call": {"tool": "tool", "method": "fail_op", "args": {}},
                    },
                ],
            },
            db_path=db_path,
            adapter=adapter,
        )

        # Run completed (didn't raise) but failed
        assert resp["summary"]["outputs_skipped"] == 1
        assert resp["results"][0]["status"] == "error"

    def test_operational_error_allows_subsequent_steps(self, tmp_path: Path) -> None:
        """Operational errors don't prevent subsequent steps from running."""
        db_path = str(tmp_path / "test.db")
        adapter = FakeAdapter()
        adapter.set_operational_error("tool", "fail_op", "error")
        adapter.set_response("tool", "succeed", {"ok": True})

        resp = run(
            {
                "goal": "continue after op error",
                "mode": "apply",
                "policy": {"allow_apply": True},
                "plan_override": [
                    {
                        "step_id": "s1",
                        "intent": "fails",
                        "call": {"tool": "tool", "method": "fail_op", "args": {}},
                    },
                    {
                        "step_id": "s2",
                        "intent": "succeeds",
                        "call": {"tool": "tool", "method": "succeed", "args": {}},
                    },
                ],
            },
            db_path=db_path,
            adapter=adapter,
        )

        # Both steps ran
        assert len(adapter.call_log) == 2
        assert resp["results"][0]["status"] == "error"
        assert resp["results"][1]["status"] == "ok"


class TestBugErrors:
    """Tests for bug error handling."""

    def test_bug_error_raises_after_recording(self, tmp_path: Path) -> None:
        """Bug errors are recorded then re-raised."""
        db_path = str(tmp_path / "test.db")
        adapter = FakeAdapter()
        adapter.set_bug_error("tool", "buggy", "invariant violation", "INTERNAL_BUG")

        with pytest.raises(NexusBugError) as exc_info:
            run(
                {
                    "goal": "bug error test",
                    "mode": "apply",
                    "policy": {"allow_apply": True},
                    "plan_override": [
                        {
                            "step_id": "s1",
                            "intent": "has bug",
                            "call": {"tool": "tool", "method": "buggy", "args": {}},
                        },
                    ],
                },
                db_path=db_path,
                adapter=adapter,
            )

        assert str(exc_info.value) == "invariant violation"
        assert exc_info.value.error_code == "INTERNAL_BUG"

    def test_unknown_exception_treated_as_bug(self, tmp_path: Path) -> None:
        """Unknown exceptions are treated as bugs and re-raised."""
        db_path = str(tmp_path / "test.db")
        adapter = FakeAdapter()

        # Configure adapter to raise a regular exception
        def raise_value_error(_args: dict) -> dict:
            raise ValueError("unexpected value")

        adapter.set_response("tool", "unknown_exc", raise_value_error)

        with pytest.raises(ValueError) as exc_info:
            run(
                {
                    "goal": "unknown exception test",
                    "mode": "apply",
                    "policy": {"allow_apply": True},
                    "plan_override": [
                        {
                            "step_id": "s1",
                            "intent": "unknown",
                            "call": {"tool": "tool", "method": "unknown_exc", "args": {}},
                        },
                    ],
                },
                db_path=db_path,
                adapter=adapter,
            )

        assert str(exc_info.value) == "unexpected value"


class TestDefaultAdapter:
    """Tests for default adapter behavior."""

    def test_no_adapter_uses_null_adapter(self, tmp_path: Path) -> None:
        """When no adapter is passed, NullAdapter is used."""
        db_path = str(tmp_path / "test.db")

        resp = run(
            {
                "goal": "default adapter test",
                "mode": "dry_run",
                "plan_override": [
                    {
                        "step_id": "s1",
                        "intent": "test",
                        "call": {"tool": "t", "method": "m", "args": {}},
                    },
                ],
            },
            db_path=db_path,
            # No adapter passed
        )

        assert resp["summary"]["adapter_id"] == "null"
        assert resp["results"][0]["output"]["simulated"] is True

    def test_apply_with_null_adapter_fails_capability(self, tmp_path: Path) -> None:
        """Apply mode with NullAdapter fails due to missing 'apply' capability (v0.6+)."""
        db_path = str(tmp_path / "test.db")

        resp = run(
            {
                "goal": "apply with null",
                "mode": "apply",
                "policy": {"allow_apply": True},
                "plan_override": [
                    {
                        "step_id": "s1",
                        "intent": "test",
                        "call": {"tool": "t", "method": "m", "args": {"x": 1}},
                    },
                ],
            },
            db_path=db_path,
            # No adapter = NullAdapter (lacks 'apply' capability)
        )

        # Run fails because NullAdapter doesn't have 'apply' capability
        assert resp["summary"]["adapter_id"] == "null"
        assert resp["results"][0]["status"] == "error"
        # Run should fail
        from nexus_router.event_store import EventStore

        store = EventStore(db_path)
        run_id = resp["run"]["run_id"]
        events = store.read_events(run_id)
        store.close()

        # Should have TOOL_CALL_FAILED with CAPABILITY_MISSING
        failed_events = [e for e in events if e.type == "TOOL_CALL_FAILED"]
        assert len(failed_events) == 1
        assert failed_events[0].payload["error_code"] == "CAPABILITY_MISSING"
