#!/usr/bin/env python3
"""
Check that ADAPTERS.generated.md is up-to-date.

This script regenerates the docs and compares them to the committed version.
Exits with code 1 if they differ (meaning docs need to be regenerated).

Usage:
    python scripts/check_generated_docs.py

In CI:
    python scripts/check_generated_docs.py || (echo "Docs are stale. Run: python -c 'from nexus_router.docs import generate_adapter_docs; ...'"; exit 1)
"""

from __future__ import annotations

import re
import sys
from pathlib import Path


def normalize_for_comparison(content: str) -> str:
    """Remove timestamp from generated content for comparison."""
    # Remove the timestamp line: <!-- Generated: 2026-01-28 04:09:03 UTC -->
    return re.sub(r"<!-- Generated: .* UTC -->", "<!-- Generated: [TIMESTAMP] -->", content)


def main() -> int:
    repo_root = Path(__file__).parent.parent
    docs_file = repo_root / "ADAPTERS.generated.md"

    # Check if file exists
    if not docs_file.exists():
        print("ERROR: ADAPTERS.generated.md does not exist", file=sys.stderr)
        print("Run: python -c \"from nexus_router.docs import generate_adapter_docs; ...")
        return 1

    # Read existing content
    existing = docs_file.read_text(encoding="utf-8")

    # Generate fresh content
    from nexus_router.docs import generate_adapter_docs

    result = generate_adapter_docs()

    if result.adapters_failed > 0:
        print("ERROR: Some adapters failed inspection:", file=sys.stderr)
        for error in result.errors:
            print(f"  - {error}", file=sys.stderr)
        return 1

    # Compare (ignoring timestamp)
    existing_normalized = normalize_for_comparison(existing)
    generated_normalized = normalize_for_comparison(result.markdown)

    if existing_normalized != generated_normalized:
        print("ERROR: ADAPTERS.generated.md is out of date", file=sys.stderr)
        print()
        print("To regenerate, run:")
        print('  python -c "from nexus_router.docs import generate_adapter_docs; open(\'ADAPTERS.generated.md\', \'w\').write(generate_adapter_docs().markdown)"')
        print()

        # Show diff summary
        existing_lines = existing_normalized.splitlines()
        generated_lines = generated_normalized.splitlines()

        if len(existing_lines) != len(generated_lines):
            print(f"Line count differs: {len(existing_lines)} vs {len(generated_lines)}")

        return 1

    print("ADAPTERS.generated.md is up-to-date")
    return 0


if __name__ == "__main__":
    sys.exit(main())
