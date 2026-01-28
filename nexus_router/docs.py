"""Auto-generated documentation for nexus-router adapters."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .plugins import inspect_adapter, InspectionResult


@dataclass
class AdapterEntry:
    """Entry for a known adapter to document."""

    factory_ref: str
    package_name: str
    repo_url: Optional[str] = None
    config: Optional[Dict[str, Any]] = None  # Minimal config for inspection


# Known adapters registry (source of truth for docs generation)
KNOWN_ADAPTERS: List[AdapterEntry] = [
    AdapterEntry(
        factory_ref="nexus_router_adapter_http:create_adapter",
        package_name="nexus-router-adapter-http",
        repo_url="https://github.com/mcp-tool-shop/nexus-router-adapter-http",
        config={"base_url": "https://example.com"},
    ),
    AdapterEntry(
        factory_ref="nexus_router_adapter_stdout:create_adapter",
        package_name="nexus-router-adapter-stdout",
        repo_url="https://github.com/mcp-tool-shop/nexus-router-adapter-stdout",
        config={},
    ),
]


def _render_config_table(config_params: List[Dict[str, Any]]) -> str:
    """Render config parameters as a markdown table."""
    if not config_params:
        return "_No configuration parameters documented._\n"

    lines = [
        "| Parameter | Type | Required | Default | Description |",
        "|-----------|------|----------|---------|-------------|",
    ]

    for param in config_params:
        name = f"`{param['name']}`"
        ptype = param.get("type", "any")
        required = "Yes" if param.get("required") else "No"
        default = f"`{param['default']!r}`" if "default" in param else "-"
        desc = param.get("description", "-")
        lines.append(f"| {name} | {ptype} | {required} | {default} | {desc} |")

    return "\n".join(lines) + "\n"


def _render_adapter_section(
    entry: AdapterEntry,
    result: InspectionResult,
) -> str:
    """Render a single adapter's documentation section."""
    lines: List[str] = []

    # Header
    kind = result.adapter_kind or "unknown"
    lines.append(f"### {kind} adapter")
    lines.append("")

    # Badges
    badges = []
    if entry.repo_url:
        ci_badge = f"[![adapter-ci]({entry.repo_url}/actions/workflows/adapter-ci.yml/badge.svg)]({entry.repo_url}/actions/workflows/adapter-ci.yml)"
        badges.append(ci_badge)
    if badges:
        lines.append(" ".join(badges))
        lines.append("")

    # Basic info
    lines.append(f"**Package:** `{entry.package_name}`")
    lines.append(f"**Factory:** `{entry.factory_ref}`")
    if result.supported_router_versions:
        lines.append(f"**Supported router versions:** `{result.supported_router_versions}`")
    lines.append("")

    # Capabilities
    caps = result.capabilities or []
    if caps:
        lines.append(f"**Capabilities:** {', '.join(f'`{c}`' for c in sorted(caps))}")
        lines.append("")

    # Installation
    lines.append("#### Installation")
    lines.append("")
    lines.append("```bash")
    lines.append(f"pip install {entry.package_name}")
    lines.append("```")
    lines.append("")

    # Usage
    lines.append("#### Usage")
    lines.append("")
    lines.append("```python")
    lines.append("from nexus_router.plugins import load_adapter")
    lines.append("")
    lines.append("adapter = load_adapter(")
    lines.append(f'    "{entry.factory_ref}",')
    if entry.config:
        for key, value in entry.config.items():
            lines.append(f"    {key}={value!r},")
    lines.append(")")
    lines.append("```")
    lines.append("")

    # Configuration
    lines.append("#### Configuration")
    lines.append("")
    lines.append(_render_config_table(result.config_params or []))
    lines.append("")

    # Error codes
    if result.error_codes:
        lines.append("#### Error Codes")
        lines.append("")
        for code in result.error_codes:
            lines.append(f"- `{code}`")
        lines.append("")

    # Repository link
    if entry.repo_url:
        lines.append(f"**Repository:** [{entry.repo_url}]({entry.repo_url})")
        lines.append("")

    return "\n".join(lines)


def _render_failed_adapter(entry: AdapterEntry, error: str) -> str:
    """Render a section for an adapter that failed inspection."""
    lines = [
        f"### {entry.package_name}",
        "",
        f"**Package:** `{entry.package_name}`",
        f"**Factory:** `{entry.factory_ref}`",
        "",
        "⚠️ **Inspection failed:**",
        "",
        f"```",
        error,
        "```",
        "",
    ]
    return "\n".join(lines)


@dataclass
class DocsGenerationResult:
    """Result of generate_adapter_docs()."""

    markdown: str
    adapters_ok: int
    adapters_failed: int
    errors: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "markdown": self.markdown,
            "adapters_ok": self.adapters_ok,
            "adapters_failed": self.adapters_failed,
            "errors": self.errors,
        }


def generate_adapter_docs(
    adapters: Optional[List[AdapterEntry]] = None,
    *,
    title: str = "Official Adapters",
    include_header: bool = True,
    include_footer: bool = True,
) -> DocsGenerationResult:
    """
    Generate markdown documentation from adapter manifests.

    This is a read-only tool that inspects adapters and generates
    consistent documentation from their manifests.

    Args:
        adapters: List of AdapterEntry to document. Defaults to KNOWN_ADAPTERS.
        title: Title for the adapters section.
        include_header: Include file header with generation timestamp.
        include_footer: Include footer with generation info.

    Returns:
        DocsGenerationResult with markdown and statistics.

    Example:
        result = generate_adapter_docs()
        print(result.markdown)
    """
    if adapters is None:
        adapters = KNOWN_ADAPTERS

    sections: List[str] = []
    errors: List[str] = []
    adapters_ok = 0
    adapters_failed = 0

    # Header
    if include_header:
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        sections.append("<!-- AUTO-GENERATED FILE - DO NOT EDIT MANUALLY -->")
        sections.append(f"<!-- Generated: {timestamp} -->")
        sections.append("")
        sections.append(f"# {title}")
        sections.append("")
        sections.append("This file is auto-generated from adapter manifests.")
        sections.append("To update, run `python -m nexus_router.docs`.")
        sections.append("")

    # Adapter sections
    for entry in adapters:
        try:
            result = inspect_adapter(
                entry.factory_ref,
                config=entry.config,
                strict=True,
            )

            if result.ok:
                sections.append(_render_adapter_section(entry, result))
                adapters_ok += 1
            else:
                # Validation failed but we still have some info
                error_msgs = [f"{e.check_id}: {e.message}" for e in result.errors]
                sections.append(_render_failed_adapter(entry, "\n".join(error_msgs)))
                errors.append(f"{entry.factory_ref}: validation failed")
                adapters_failed += 1

        except Exception as e:
            sections.append(_render_failed_adapter(entry, str(e)))
            errors.append(f"{entry.factory_ref}: {e}")
            adapters_failed += 1

    # Summary table
    if include_header and adapters:
        summary_lines = [
            "## Summary",
            "",
            "| Adapter | Kind | Capabilities | Status |",
            "|---------|------|--------------|--------|",
        ]

        for entry in adapters:
            try:
                result = inspect_adapter(entry.factory_ref, config=entry.config, strict=True)
                kind = result.adapter_kind or "?"
                caps = ", ".join(sorted(result.capabilities or []))
                status = "✓" if result.ok else "⚠️"
                summary_lines.append(f"| [{entry.package_name}](#{kind}-adapter) | {kind} | {caps} | {status} |")
            except Exception:
                summary_lines.append(f"| {entry.package_name} | ? | ? | ❌ |")

        summary_lines.append("")
        # Insert summary after header
        header_end = 3 if include_header else 0
        sections.insert(header_end, "\n".join(summary_lines))

    # Footer
    if include_footer:
        sections.append("---")
        sections.append("")
        from . import __version__
        sections.append(f"_Generated by nexus-router v{__version__} • {adapters_ok} adapters documented_")
        sections.append("")

    markdown = "\n".join(sections)

    return DocsGenerationResult(
        markdown=markdown,
        adapters_ok=adapters_ok,
        adapters_failed=adapters_failed,
        errors=errors,
    )


def main() -> None:
    """CLI entry point for docs generation."""
    import sys

    result = generate_adapter_docs()

    if result.errors:
        print("Errors:", file=sys.stderr)
        for error in result.errors:
            print(f"  - {error}", file=sys.stderr)
        print(file=sys.stderr)

    print(result.markdown)

    if result.adapters_failed > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
