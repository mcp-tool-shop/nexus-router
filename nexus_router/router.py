from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

from . import events as E
from .dispatch import (
    CAPABILITY_APPLY,
    AdapterRegistry,
    DispatchAdapter,
    NullAdapter,
)
from .event_store import EventStore
from .exceptions import NexusBugError, NexusOperationalError
from .policy import gate_apply
from .provenance import build_provenance_bundle


def create_plan(request: Dict[str, Any]) -> List[Dict[str, Any]]:
    # v0.1: fixture-driven planner
    plan: List[Dict[str, Any]] = request.get("plan_override", [])
    return plan


def _unique_in_order(items: List[str]) -> List[str]:
    seen = set()
    out: List[str] = []
    for x in items:
        if x not in seen:
            seen.add(x)
            out.append(x)
    return out


class Router:
    def __init__(
        self,
        store: EventStore,
        adapter: Optional[DispatchAdapter] = None,
        adapters: Optional[AdapterRegistry] = None,
    ) -> None:
        """
        Initialize router with event store and adapter configuration.

        Args:
            store: Event store for recording run events.
            adapter: Single adapter (legacy pattern, deprecated in v0.6).
            adapters: Adapter registry (v0.6+). Takes precedence over adapter.

        Resolution order:
        1. If adapters is provided, use registry.get_default()
        2. Else if adapter is provided, use it directly
        3. Else use NullAdapter()
        """
        self.store = store
        self._registry = adapters

        # Resolve adapter: registry takes precedence
        if adapters is not None:
            self.adapter: DispatchAdapter = adapters.get_default()
        elif adapter is not None:
            self.adapter = adapter
        else:
            self.adapter = NullAdapter()

    def run(self, request: Dict[str, Any]) -> Dict[str, Any]:
        mode = request.get("mode", "dry_run")
        goal = request["goal"]
        policy = request.get("policy", {})

        run_id = self.store.create_run(mode=mode, goal=goal)
        self.store.append(run_id, E.RUN_STARTED, {"mode": mode, "goal": goal})

        plan = create_plan(request)
        self.store.append(run_id, E.PLAN_CREATED, {"plan": plan})

        max_steps = policy.get("max_steps")
        outcome = "ok"
        if max_steps is not None:
            max_steps_i = int(max_steps)
            if len(plan) > max_steps_i:
                outcome = "error"
                fail_payload = {
                    "reason": "max_steps_exceeded",
                    "max_steps": max_steps_i,
                    "plan_steps": len(plan),
                }
                self.store.append(run_id, E.RUN_FAILED, fail_payload)
                self.store.set_run_status(run_id, "FAILED")
                plan = plan[:max_steps_i]

        tools_used: List[str] = []
        results: List[Dict[str, Any]] = []

        for step in plan:
            step_id = step["step_id"]
            call = step["call"]
            tool = call.get("tool", "unknown")
            method = call["method"]
            args = call.get("args", {})
            tools_used.append(method)

            self.store.append(run_id, E.STEP_STARTED, {"step_id": step_id})
            self.store.append(
                run_id,
                E.TOOL_CALL_REQUESTED,
                {
                    "step_id": step_id,
                    "call": call,
                    "adapter_id": self.adapter.adapter_id,
                },
            )

            try:
                output, simulated, duration_ms = self._dispatch_call(
                    mode=mode,
                    policy=policy,
                    tool=tool,
                    method=method,
                    args=args,
                )

                self.store.append(
                    run_id,
                    E.TOOL_CALL_SUCCEEDED,
                    {
                        "step_id": step_id,
                        "simulated": simulated,
                        "output": output,
                        "adapter_id": self.adapter.adapter_id,
                        "duration_ms": duration_ms,
                    },
                )
                status = "ok"

            except NexusOperationalError as ex:
                # Operational error: record failure, continue to next step or end run
                outcome = "error"
                status = "error"
                output = {}
                self.store.append(
                    run_id,
                    E.TOOL_CALL_FAILED,
                    {
                        "step_id": step_id,
                        "error_kind": "operational",
                        "error_code": ex.error_code,
                        "message": str(ex),
                        "adapter_id": self.adapter.adapter_id,
                    },
                )
                # Don't re-raise - run continues but will end as FAILED

            except NexusBugError as ex:
                # Bug error: record and re-raise
                outcome = "error"
                status = "error"
                output = {}
                self.store.append(
                    run_id,
                    E.TOOL_CALL_FAILED,
                    {
                        "step_id": step_id,
                        "error_kind": "bug",
                        "error_code": ex.error_code,
                        "message": str(ex),
                        "adapter_id": self.adapter.adapter_id,
                    },
                )
                self.store.append(
                    run_id,
                    E.RUN_FAILED,
                    {"reason": "bug_error", "step_id": step_id},
                )
                self.store.set_run_status(run_id, "FAILED")
                raise

            except PermissionError as ex:
                # Legacy: policy gate failure
                outcome = "error"
                status = "error"
                output = {}
                self.store.append(
                    run_id,
                    E.TOOL_CALL_FAILED,
                    {
                        "step_id": step_id,
                        "error_kind": "operational",
                        "error_code": "PERMISSION_DENIED",
                        "message": str(ex),
                        "adapter_id": self.adapter.adapter_id,
                    },
                )

            except Exception as ex:
                # Unknown exception: treat as bug, record + re-raise
                outcome = "error"
                status = "error"
                output = {}
                self.store.append(
                    run_id,
                    E.TOOL_CALL_FAILED,
                    {
                        "step_id": step_id,
                        "error_kind": "bug",
                        "error_code": "UNKNOWN_ERROR",
                        "message": repr(ex),
                        "adapter_id": self.adapter.adapter_id,
                    },
                )
                self.store.append(
                    run_id,
                    E.RUN_FAILED,
                    {"reason": "unexpected_exception", "step_id": step_id},
                )
                self.store.set_run_status(run_id, "FAILED")
                raise

            self.store.append(run_id, E.STEP_COMPLETED, {"step_id": step_id, "status": status})
            results.append(
                {
                    "step_id": step_id,
                    "status": status,
                    "simulated": (mode == "dry_run"),
                    "output": output,
                    "evidence": [],
                }
            )

        prov_bundle = build_provenance_bundle(run_id=run_id, request=request, results=results)
        self.store.append(run_id, E.PROVENANCE_EMITTED, prov_bundle)

        if outcome == "ok":
            self.store.append(run_id, E.RUN_COMPLETED, {"outcome": "ok"})
            self.store.set_run_status(run_id, "COMPLETED")
        else:
            # Run already failed (max_steps or step error) - emit final failure event
            self.store.append(run_id, E.RUN_FAILED, {"outcome": "error"})
            self.store.set_run_status(run_id, "FAILED")

        tools_used_u = _unique_in_order(tools_used)
        events_committed = len(self.store.read_events(run_id))

        applied_count = (
            0 if mode == "dry_run" else sum(1 for r in results if r["status"] == "ok")
        )
        skipped_count = sum(1 for r in results if r["status"] != "ok")

        return {
            "summary": {
                "mode": mode,
                "steps": len(plan),
                "tools_used": tools_used_u,
                "outputs_total": len(results),
                "outputs_applied": applied_count,
                "outputs_skipped": skipped_count,
                "adapter_id": self.adapter.adapter_id,
            },
            "run": {"run_id": run_id, "events_committed": events_committed},
            "plan": plan,
            "results": results,
            "provenance": prov_bundle.get("provenance", {"artifacts": [], "records": []}),
        }

    def _dispatch_call(
        self,
        *,
        mode: str,
        policy: Dict[str, Any],
        tool: str,
        method: str,
        args: Dict[str, Any],
    ) -> tuple[Dict[str, Any], bool, int]:
        """
        Dispatch a tool call based on mode.

        Returns:
            (output, simulated, duration_ms)

        Raises:
            NexusOperationalError: If adapter lacks required capability for mode.
        """
        if mode == "dry_run":
            # dry_run: never call adapter, return simulated output
            output: Dict[str, Any] = {
                "simulated": True,
                "adapter_id": self.adapter.adapter_id,
                "tool": tool,
                "method": method,
            }
            return output, True, 0

        # apply mode: enforce capability, then gate, then call adapter
        if CAPABILITY_APPLY not in self.adapter.capabilities:
            raise NexusOperationalError(
                f"Adapter '{self.adapter.adapter_id}' lacks required capability "
                f"'{CAPABILITY_APPLY}' for apply mode",
                error_code="CAPABILITY_MISSING",
                details={
                    "adapter_id": self.adapter.adapter_id,
                    "required_capability": CAPABILITY_APPLY,
                    "adapter_capabilities": sorted(self.adapter.capabilities),
                },
            )

        gate_apply(policy)

        start_time = time.monotonic()
        output = self.adapter.call(tool, method, args)
        duration_ms = int((time.monotonic() - start_time) * 1000)

        # Ensure adapter_id is in output
        output["adapter_id"] = self.adapter.adapter_id

        return output, False, duration_ms
