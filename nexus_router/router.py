from __future__ import annotations

from typing import Any, Dict, List

from .event_store import EventStore
from .policy import gate_apply
from .provenance import build_provenance_bundle
from . import events as E


def create_plan(request: Dict[str, Any]) -> List[Dict[str, Any]]:
    # v0.1: fixture-driven planner
    return request.get("plan_override", [])


def _unique_in_order(items: List[str]) -> List[str]:
    seen = set()
    out: List[str] = []
    for x in items:
        if x not in seen:
            seen.add(x)
            out.append(x)
    return out


class Router:
    def __init__(self, store: EventStore) -> None:
        self.store = store

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
                self.store.append(
                    run_id,
                    E.RUN_FAILED,
                    {"reason": "max_steps_exceeded", "max_steps": max_steps_i, "plan_steps": len(plan)},
                )
                self.store.set_run_status(run_id, "FAILED")
                plan = plan[:max_steps_i]

        tools_used: List[str] = []
        results: List[Dict[str, Any]] = []

        for step in plan:
            step_id = step["step_id"]
            call = step["call"]
            tools_used.append(call["method"])

            self.store.append(run_id, E.STEP_STARTED, {"step_id": step_id})
            self.store.append(run_id, E.TOOL_CALL_REQUESTED, {"step_id": step_id, "call": call})

            try:
                if mode == "dry_run":
                    output = {"simulated": True, "note": "v0.1 dry_run placeholder"}
                    simulated = True
                else:
                    gate_apply(policy)
                    output = {"applied": True, "note": "v0.1 apply placeholder"}
                    simulated = False

                self.store.append(
                    run_id,
                    E.TOOL_CALL_SUCCEEDED,
                    {"step_id": step_id, "simulated": simulated, "output": output},
                )
                status = "ok"

            except PermissionError as ex:
                outcome = "error"
                status = "error"
                output = {}
                self.store.append(
                    run_id,
                    E.TOOL_CALL_FAILED,
                    {"step_id": step_id, "error": str(ex), "kind": "PermissionError"},
                )

            except Exception as ex:
                # Posture A: record + re-raise
                outcome = "error"
                status = "error"
                output = {}
                self.store.append(
                    run_id,
                    E.TOOL_CALL_FAILED,
                    {"step_id": step_id, "error": repr(ex), "kind": "UnexpectedError"},
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

        return {
            "summary": {
                "mode": mode,
                "steps": len(plan),
                "tools_used": tools_used_u,
                "outputs_total": len(results),
                "outputs_applied": 0 if mode == "dry_run" else sum(1 for r in results if r["status"] == "ok"),
                "outputs_skipped": sum(1 for r in results if r["status"] != "ok"),
            },
            "run": {"run_id": run_id, "events_committed": events_committed},
            "plan": plan,
            "results": results,
            "provenance": prov_bundle.get("provenance", {"artifacts": [], "records": []}),
        }
