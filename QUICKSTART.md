# QUICKSTART (nexus-router v0.1.1)

## Install

```bash
pip install -e .
```

## Run (Python)

```python
from nexus_router.tool import run

result = run({
  "goal": "scan repo",
  "mode": "dry_run",
  "plan_override": []
})
print(result["summary"])
```

## Persistence

Default `db_path=":memory:"` is ephemeral. Pass a file path to persist runs:

```python
result = run({"goal": "scan repo"}, db_path="nexus-router.db")
```

## Run tests

```bash
python -m pytest -q
```
