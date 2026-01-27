from typing import Any, Dict


def gate_apply(policy: Dict[str, Any]) -> None:
    if not policy.get("allow_apply", False):
        raise PermissionError("Policy does not allow apply (allow_apply=false).")
