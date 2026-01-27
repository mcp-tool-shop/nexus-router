from __future__ import annotations

import hashlib
import json
import uuid
from typing import Any, Dict, List


def sha256_canonical(obj: Any) -> str:
    data = json.dumps(obj, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def build_provenance_bundle(
    *, run_id: str, request: Dict[str, Any], results: List[Dict[str, Any]]
) -> Dict[str, Any]:
    digest = sha256_canonical({"request": request, "results": results})
    return {
        "provenance": {
            "artifacts": [],
            "records": [
                {
                    "prov_id": str(uuid.uuid4()),
                    "method_id": "nexus-router.provenance.record_v0_1",
                    "inputs": [],
                    "outputs": [],
                    "digests": [{"artifact_id": f"run:{run_id}", "alg": "sha256", "value": digest}],
                }
            ],
        }
    }
