"""
Plugin loading for nexus-router adapter packages.

This module provides utilities for loading adapter packages without
introducing global state or import side effects. Adapters are loaded
explicitly by the host process and registered into an AdapterRegistry.

Usage:
    from nexus_router.plugins import load_adapter
    from nexus_router.dispatch import AdapterRegistry

    registry = AdapterRegistry(default_adapter_id="http")
    registry.register(
        load_adapter(
            "nexus_router_adapter_http:create_adapter",
            adapter_id="http",
            base_url="https://api.example.com",
            timeout_s=30,
        )
    )

The factory_ref format is "module.path:function_name".
"""

from __future__ import annotations

import importlib
from typing import Any, Dict, Optional

from .dispatch import DispatchAdapter
from .exceptions import NexusOperationalError


class AdapterLoadError(NexusOperationalError):
    """Error loading an adapter from a plugin package."""

    def __init__(self, message: str, *, factory_ref: str, cause: Optional[Exception] = None):
        details: Dict[str, Any] = {"factory_ref": factory_ref}
        if cause is not None:
            details["cause"] = str(cause)
            details["cause_type"] = type(cause).__name__
        super().__init__(message, error_code="ADAPTER_LOAD_FAILED", details=details)
        self.factory_ref = factory_ref
        self.cause = cause


def load_adapter(factory_ref: str, **config: Any) -> DispatchAdapter:
    """
    Load an adapter from a plugin package.

    Args:
        factory_ref: Module and function reference in format "module.path:function_name".
                     Example: "nexus_router_adapter_http:create_adapter"
        **config: Configuration passed to the adapter factory function.

    Returns:
        A DispatchAdapter instance.

    Raises:
        AdapterLoadError: If the adapter cannot be loaded (module not found,
                          function not found, factory raised, etc.)

    Example:
        adapter = load_adapter(
            "nexus_router_adapter_http:create_adapter",
            adapter_id="my-http-adapter",
            base_url="https://api.example.com",
            timeout_s=30,
        )

    The factory function must have the signature:
        def create_adapter(*, adapter_id: str | None = None, **config) -> DispatchAdapter

    Platform rules:
    - No side effects on import
    - No global state modification
    - Factory must return a valid DispatchAdapter
    - Caller is responsible for registering into AdapterRegistry
    """
    # Parse factory_ref
    if ":" not in factory_ref:
        raise AdapterLoadError(
            f"Invalid factory_ref format: '{factory_ref}'. Expected 'module:function'.",
            factory_ref=factory_ref,
        )

    module_path, function_name = factory_ref.rsplit(":", 1)

    if not module_path or not function_name:
        raise AdapterLoadError(
            f"Invalid factory_ref format: '{factory_ref}'. "
            f"Both module and function must be non-empty.",
            factory_ref=factory_ref,
        )

    # Import module
    try:
        module = importlib.import_module(module_path)
    except ImportError as e:
        raise AdapterLoadError(
            f"Failed to import module '{module_path}': {e}",
            factory_ref=factory_ref,
            cause=e,
        )

    # Get factory function
    try:
        factory = getattr(module, function_name)
    except AttributeError as e:
        raise AdapterLoadError(
            f"Module '{module_path}' has no attribute '{function_name}'",
            factory_ref=factory_ref,
            cause=e,
        )

    if not callable(factory):
        raise AdapterLoadError(
            f"'{function_name}' in module '{module_path}' is not callable",
            factory_ref=factory_ref,
        )

    # Call factory
    try:
        adapter = factory(**config)
    except Exception as e:
        raise AdapterLoadError(
            f"Factory '{function_name}' raised: {e}",
            factory_ref=factory_ref,
            cause=e,
        )

    # Validate result
    if not _is_dispatch_adapter(adapter):
        raise AdapterLoadError(
            f"Factory '{function_name}' did not return a valid DispatchAdapter. "
            f"Got: {type(adapter).__name__}",
            factory_ref=factory_ref,
        )

    return adapter


def _is_dispatch_adapter(obj: Any) -> bool:
    """Check if an object implements the DispatchAdapter protocol."""
    return (
        hasattr(obj, "adapter_id")
        and hasattr(obj, "adapter_kind")
        and hasattr(obj, "capabilities")
        and hasattr(obj, "call")
        and callable(getattr(obj, "call", None))
    )


def get_adapter_metadata(adapter: DispatchAdapter) -> Dict[str, Any]:
    """
    Extract metadata from an adapter for introspection.

    Args:
        adapter: A DispatchAdapter instance.

    Returns:
        Dict with adapter_id, adapter_kind, and capabilities.
    """
    return {
        "adapter_id": adapter.adapter_id,
        "adapter_kind": adapter.adapter_kind,
        "capabilities": sorted(adapter.capabilities),
    }


# Standard capabilities (v0.8+)
STANDARD_CAPABILITIES = frozenset({"dry_run", "apply", "timeout", "external"})

# Manifest schema version
MANIFEST_SCHEMA_VERSION = 1

# Valid config_schema types
MANIFEST_CONFIG_TYPES = frozenset({"string", "number", "boolean", "object", "array"})


def _get_adapter_manifest(module_path: str) -> Optional[Dict[str, Any]]:
    """
    Load a module and extract ADAPTER_MANIFEST if present.

    Args:
        module_path: Module path (e.g., "nexus_router_adapter_http")

    Returns:
        The manifest dict, or None if not present.
    """
    try:
        module = importlib.import_module(module_path)
        manifest = getattr(module, "ADAPTER_MANIFEST", None)
        if manifest is not None and isinstance(manifest, dict):
            return manifest
    except ImportError:
        pass  # Module import issues handled elsewhere
    return None


def _validate_manifest_schema(manifest: Dict[str, Any]) -> list[str]:
    """
    Validate manifest has correct structure.

    Returns list of error messages (empty if valid).
    """
    errors: list[str] = []

    # Required fields
    if "schema_version" not in manifest:
        errors.append("Missing required field: schema_version")
    elif manifest["schema_version"] != MANIFEST_SCHEMA_VERSION:
        errors.append(
            f"Invalid schema_version: {manifest['schema_version']} "
            f"(expected {MANIFEST_SCHEMA_VERSION})"
        )

    if "kind" not in manifest:
        errors.append("Missing required field: kind")
    elif not isinstance(manifest["kind"], str) or not manifest["kind"]:
        errors.append("Field 'kind' must be a non-empty string")

    if "capabilities" not in manifest:
        errors.append("Missing required field: capabilities")
    elif not isinstance(manifest["capabilities"], list):
        errors.append("Field 'capabilities' must be a list")
    elif not all(isinstance(c, str) for c in manifest["capabilities"]):
        errors.append("Field 'capabilities' must contain only strings")

    # Optional fields with type checks
    if "supported_router_versions" in manifest:
        if not isinstance(manifest["supported_router_versions"], str):
            errors.append("Field 'supported_router_versions' must be a string")

    if "error_codes" in manifest:
        if not isinstance(manifest["error_codes"], list):
            errors.append("Field 'error_codes' must be a list")
        elif not all(isinstance(c, str) for c in manifest["error_codes"]):
            errors.append("Field 'error_codes' must contain only strings")

    if "config_schema" in manifest:
        if not isinstance(manifest["config_schema"], dict):
            errors.append("Field 'config_schema' must be a dict")
        else:
            for key, schema in manifest["config_schema"].items():
                if not isinstance(schema, dict):
                    errors.append(f"config_schema['{key}'] must be a dict")
                    continue
                if "type" not in schema:
                    errors.append(f"config_schema['{key}'] missing required field: type")
                elif schema["type"] not in MANIFEST_CONFIG_TYPES:
                    errors.append(
                        f"config_schema['{key}'].type invalid: {schema['type']} "
                        f"(must be one of {sorted(MANIFEST_CONFIG_TYPES)})"
                    )
                if "required" not in schema:
                    errors.append(f"config_schema['{key}'] missing required field: required")
                elif not isinstance(schema["required"], bool):
                    errors.append(f"config_schema['{key}'].required must be a boolean")

    return errors


class ValidationCheck:
    """Result of a single validation check."""

    def __init__(self, check_id: str, status: str, message: str) -> None:
        self.check_id = check_id
        self.status = status  # "pass", "fail", "warn", "skip"
        self.message = message

    def to_dict(self) -> Dict[str, str]:
        return {
            "id": self.check_id,
            "status": self.status,
            "message": self.message,
        }


class ValidationResult:
    """Result of validate_adapter()."""

    def __init__(
        self,
        ok: bool,
        metadata: Optional[Dict[str, Any]],
        checks: list[ValidationCheck],
        error: Optional[str] = None,
    ) -> None:
        self.ok = ok
        self.metadata = metadata
        self.checks = checks
        self.error = error

    @property
    def errors(self) -> list[ValidationCheck]:
        """Checks with status='fail'."""
        return [c for c in self.checks if c.status == "fail"]

    @property
    def warnings(self) -> list[ValidationCheck]:
        """Checks with status='warn'."""
        return [c for c in self.checks if c.status == "warn"]

    def to_dict(self) -> Dict[str, Any]:
        result: Dict[str, Any] = {
            "ok": self.ok,
            "metadata": self.metadata,
            "checks": [c.to_dict() for c in self.checks],
            "errors": [c.to_dict() for c in self.errors],
            "warnings": [c.to_dict() for c in self.warnings],
        }
        if self.error is not None:
            result["error"] = self.error
        return result


def validate_adapter(
    factory_ref: str,
    config: Optional[Dict[str, Any]] = None,
    *,
    strict: bool = True,
) -> ValidationResult:
    """
    Validate an adapter package without dispatch.

    This is a read-only lint tool that checks adapter compliance with
    ADAPTER_SPEC.md. It loads the adapter but does not execute any calls.

    Args:
        factory_ref: Module and function reference ("module:function").
        config: Optional configuration to pass to factory.
        strict: If True, unknown capabilities cause failure. Default True.

    Returns:
        ValidationResult with ok, metadata, and checks.

    Example:
        result = validate_adapter(
            "nexus_router_adapter_http:create_adapter",
            config={"base_url": "https://example.com"},
        )
        if not result.ok:
            for check in result.checks:
                if check.status == "fail":
                    print(f"FAIL: {check.check_id}: {check.message}")

    Checks performed:
        LOAD_OK: load_adapter() succeeds
        PROTOCOL_FIELDS: adapter_id, adapter_kind, capabilities, call exist
        ADAPTER_ID_FORMAT: adapter_id is non-empty string
        ADAPTER_KIND_FORMAT: adapter_kind is non-empty string
        CAPABILITIES_TYPE: capabilities is a set-like of strings
        CAPABILITIES_VALID: only standard capabilities declared (strict mode)
        MANIFEST_PRESENT: ADAPTER_MANIFEST exists (warn if absent)
        MANIFEST_SCHEMA: manifest has required fields with correct types
        MANIFEST_KIND_MATCH: manifest kind matches adapter_kind
        MANIFEST_CAPS_MATCH: manifest capabilities match adapter
    """
    checks: list[ValidationCheck] = []
    config = config or {}

    # LOAD_OK: Try to load the adapter
    try:
        adapter = load_adapter(factory_ref, **config)
        checks.append(ValidationCheck(
            "LOAD_OK",
            "pass",
            f"Successfully loaded adapter from '{factory_ref}'",
        ))
    except AdapterLoadError as e:
        checks.append(ValidationCheck(
            "LOAD_OK",
            "fail",
            f"Failed to load adapter: {e}",
        ))
        return ValidationResult(
            ok=False,
            metadata=None,
            checks=checks,
            error=str(e),
        )

    # PROTOCOL_FIELDS: Check required protocol fields
    missing_fields = []
    for field in ("adapter_id", "adapter_kind", "capabilities", "call"):
        if not hasattr(adapter, field):
            missing_fields.append(field)

    if missing_fields:
        checks.append(ValidationCheck(
            "PROTOCOL_FIELDS",
            "fail",
            f"Missing required fields: {', '.join(missing_fields)}",
        ))
        return ValidationResult(
            ok=False,
            metadata=None,
            checks=checks,
            error=f"Missing protocol fields: {missing_fields}",
        )

    # Check call is callable
    if not callable(getattr(adapter, "call", None)):
        checks.append(ValidationCheck(
            "PROTOCOL_FIELDS",
            "fail",
            "Field 'call' is not callable",
        ))
        return ValidationResult(
            ok=False,
            metadata=None,
            checks=checks,
            error="call is not callable",
        )

    checks.append(ValidationCheck(
        "PROTOCOL_FIELDS",
        "pass",
        "All required protocol fields present and valid",
    ))

    # Extract metadata now that we know fields exist
    metadata = get_adapter_metadata(adapter)

    # ADAPTER_ID_FORMAT
    adapter_id = adapter.adapter_id
    if not isinstance(adapter_id, str) or not adapter_id:
        checks.append(ValidationCheck(
            "ADAPTER_ID_FORMAT",
            "fail",
            f"adapter_id must be non-empty string, got: {type(adapter_id).__name__}",
        ))
    else:
        checks.append(ValidationCheck(
            "ADAPTER_ID_FORMAT",
            "pass",
            f"adapter_id='{adapter_id}'",
        ))

    # ADAPTER_KIND_FORMAT
    adapter_kind = adapter.adapter_kind
    if not isinstance(adapter_kind, str) or not adapter_kind:
        checks.append(ValidationCheck(
            "ADAPTER_KIND_FORMAT",
            "fail",
            f"adapter_kind must be non-empty string, got: {type(adapter_kind).__name__}",
        ))
    else:
        checks.append(ValidationCheck(
            "ADAPTER_KIND_FORMAT",
            "pass",
            f"adapter_kind='{adapter_kind}'",
        ))

    # CAPABILITIES_TYPE: Check capabilities is set-like of strings
    capabilities = adapter.capabilities
    type_ok = True

    if not hasattr(capabilities, "__iter__"):
        checks.append(ValidationCheck(
            "CAPABILITIES_TYPE",
            "fail",
            f"capabilities must be iterable, got: {type(capabilities).__name__}",
        ))
        type_ok = False
    else:
        non_strings = [c for c in capabilities if not isinstance(c, str)]
        if non_strings:
            checks.append(ValidationCheck(
                "CAPABILITIES_TYPE",
                "fail",
                f"capabilities contains non-string values: {non_strings}",
            ))
            type_ok = False
        else:
            checks.append(ValidationCheck(
                "CAPABILITIES_TYPE",
                "pass",
                f"capabilities is valid set of {len(list(capabilities))} strings",
            ))

    # CAPABILITIES_VALID: Check only standard capabilities
    if type_ok:
        caps_set = set(capabilities)
        unknown = caps_set - STANDARD_CAPABILITIES

        if unknown:
            status = "fail" if strict else "warn"
            checks.append(ValidationCheck(
                "CAPABILITIES_VALID",
                status,
                f"Unknown capabilities (not in spec): {sorted(unknown)}",
            ))
        else:
            checks.append(ValidationCheck(
                "CAPABILITIES_VALID",
                "pass",
                f"All capabilities are standard: {sorted(caps_set)}",
            ))
    else:
        checks.append(ValidationCheck(
            "CAPABILITIES_VALID",
            "skip",
            "Skipped due to CAPABILITIES_TYPE failure",
        ))

    # MANIFEST_* checks: Validate ADAPTER_MANIFEST if present
    module_path = factory_ref.rsplit(":", 1)[0]
    manifest = _get_adapter_manifest(module_path)

    if manifest is None:
        # Warn if no manifest (optional but encouraged)
        checks.append(ValidationCheck(
            "MANIFEST_PRESENT",
            "warn",
            f"No ADAPTER_MANIFEST found in module '{module_path}' (optional but recommended)",
        ))
        # Skip other manifest checks
        checks.append(ValidationCheck(
            "MANIFEST_SCHEMA",
            "skip",
            "Skipped: no manifest present",
        ))
        checks.append(ValidationCheck(
            "MANIFEST_KIND_MATCH",
            "skip",
            "Skipped: no manifest present",
        ))
        checks.append(ValidationCheck(
            "MANIFEST_CAPS_MATCH",
            "skip",
            "Skipped: no manifest present",
        ))
    else:
        checks.append(ValidationCheck(
            "MANIFEST_PRESENT",
            "pass",
            f"ADAPTER_MANIFEST found in module '{module_path}'",
        ))

        # MANIFEST_SCHEMA: Validate structure
        schema_errors = _validate_manifest_schema(manifest)
        if schema_errors:
            checks.append(ValidationCheck(
                "MANIFEST_SCHEMA",
                "fail",
                f"Invalid manifest schema: {'; '.join(schema_errors)}",
            ))
            # Skip cross-checks if schema is invalid
            checks.append(ValidationCheck(
                "MANIFEST_KIND_MATCH",
                "skip",
                "Skipped: manifest schema invalid",
            ))
            checks.append(ValidationCheck(
                "MANIFEST_CAPS_MATCH",
                "skip",
                "Skipped: manifest schema invalid",
            ))
        else:
            checks.append(ValidationCheck(
                "MANIFEST_SCHEMA",
                "pass",
                "Manifest schema is valid",
            ))

            # MANIFEST_KIND_MATCH: Cross-check kind
            manifest_kind = manifest["kind"]
            if manifest_kind != adapter_kind:
                checks.append(ValidationCheck(
                    "MANIFEST_KIND_MATCH",
                    "fail",
                    f"Manifest kind '{manifest_kind}' does not match "
                    f"adapter_kind '{adapter_kind}'",
                ))
            else:
                checks.append(ValidationCheck(
                    "MANIFEST_KIND_MATCH",
                    "pass",
                    f"Manifest kind matches adapter_kind: '{adapter_kind}'",
                ))

            # MANIFEST_CAPS_MATCH: Cross-check capabilities
            manifest_caps = set(manifest["capabilities"])
            adapter_caps = set(adapter.capabilities)

            if manifest_caps != adapter_caps:
                extra_in_manifest = manifest_caps - adapter_caps
                missing_from_manifest = adapter_caps - manifest_caps
                mismatch_parts = []
                if extra_in_manifest:
                    mismatch_parts.append(f"extra in manifest: {sorted(extra_in_manifest)}")
                if missing_from_manifest:
                    mismatch_parts.append(f"missing from manifest: {sorted(missing_from_manifest)}")
                checks.append(ValidationCheck(
                    "MANIFEST_CAPS_MATCH",
                    "fail",
                    f"Manifest capabilities do not match adapter: {'; '.join(mismatch_parts)}",
                ))
            else:
                checks.append(ValidationCheck(
                    "MANIFEST_CAPS_MATCH",
                    "pass",
                    f"Manifest capabilities match adapter: {sorted(adapter_caps)}",
                ))

        # Add manifest to metadata
        metadata["manifest"] = manifest

    # Determine overall ok status
    ok = all(c.status in ("pass", "warn", "skip") for c in checks)

    return ValidationResult(
        ok=ok,
        metadata=metadata,
        checks=checks,
    )


def _render_config_param(name: str, schema: Dict[str, Any]) -> Dict[str, Any]:
    """Render a config_schema entry into human-friendly format."""
    rendered = {
        "name": name,
        "type": schema.get("type", "unknown"),
        "required": schema.get("required", False),
    }
    if "default" in schema:
        rendered["default"] = schema["default"]
    if "description" in schema:
        rendered["description"] = schema["description"]
    return rendered


class InspectionResult:
    """Result of inspect_adapter()."""

    def __init__(
        self,
        ok: bool,
        validation: ValidationResult,
        adapter_id: Optional[str],
        adapter_kind: Optional[str],
        capabilities: Optional[list[str]],
        manifest: Optional[Dict[str, Any]],
        config_params: Optional[list[Dict[str, Any]]],
        error_codes: Optional[list[str]],
        supported_router_versions: Optional[str],
    ) -> None:
        self.ok = ok
        self.validation = validation
        self.adapter_id = adapter_id
        self.adapter_kind = adapter_kind
        self.capabilities = capabilities
        self.manifest = manifest
        self.config_params = config_params
        self.error_codes = error_codes
        self.supported_router_versions = supported_router_versions

    @property
    def errors(self) -> list[ValidationCheck]:
        """Validation errors."""
        return self.validation.errors

    @property
    def warnings(self) -> list[ValidationCheck]:
        """Validation warnings."""
        return self.validation.warnings

    def to_dict(self) -> Dict[str, Any]:
        """Convert to serializable dict."""
        return {
            "ok": self.ok,
            "adapter_id": self.adapter_id,
            "adapter_kind": self.adapter_kind,
            "capabilities": self.capabilities,
            "supported_router_versions": self.supported_router_versions,
            "config_params": self.config_params,
            "error_codes": self.error_codes,
            "manifest": self.manifest,
            "validation": self.validation.to_dict(),
        }

    def render(self) -> str:
        """Render human-readable inspection report."""
        lines: list[str] = []

        # Header
        if self.ok:
            lines.append("✓ Adapter validation PASSED")
        else:
            lines.append("✗ Adapter validation FAILED")
        lines.append("")

        # Basic info
        lines.append("## Adapter Info")
        lines.append(f"  ID:           {self.adapter_id or '(unknown)'}")
        lines.append(f"  Kind:         {self.adapter_kind or '(unknown)'}")
        lines.append(f"  Capabilities: {', '.join(self.capabilities or []) or '(none)'}")
        lines.append("")

        # Validation summary
        lines.append("## Validation")
        for check in self.validation.checks:
            status_icon = {
                "pass": "✓",
                "fail": "✗",
                "warn": "⚠",
                "skip": "○",
            }.get(check.status, "?")
            lines.append(f"  {status_icon} {check.check_id}")
        lines.append("")

        # Errors/warnings
        if self.errors:
            lines.append("## Errors")
            for err in self.errors:
                lines.append(f"  ✗ {err.check_id}: {err.message}")
            lines.append("")

        if self.warnings:
            lines.append("## Warnings")
            for warn in self.warnings:
                lines.append(f"  ⚠ {warn.check_id}: {warn.message}")
            lines.append("")

        # Manifest info
        if self.manifest:
            lines.append("## Manifest")
            if self.supported_router_versions:
                lines.append(f"  Router versions: {self.supported_router_versions}")
            if self.error_codes:
                lines.append(f"  Error codes:     {', '.join(self.error_codes)}")
            lines.append("")

            # Config params
            if self.config_params:
                lines.append("## Configuration Parameters")
                for param in self.config_params:
                    req = "required" if param.get("required") else "optional"
                    type_str = param.get("type", "any")
                    default_str = ""
                    if "default" in param:
                        default_str = f", default={param['default']!r}"
                    lines.append(f"  {param['name']} ({type_str}, {req}{default_str})")
                    if param.get("description"):
                        lines.append(f"    {param['description']}")
                lines.append("")

        return "\n".join(lines)


def inspect_adapter(
    factory_ref: str,
    config: Optional[Dict[str, Any]] = None,
    *,
    strict: bool = True,
) -> InspectionResult:
    """
    Inspect an adapter package with human-friendly output.

    This is a read-only tool that validates an adapter and extracts
    metadata, config schema, and error codes for display.

    Args:
        factory_ref: Module and function reference ("module:function").
        config: Optional configuration to pass to factory.
        strict: If True, unknown capabilities cause failure. Default True.

    Returns:
        InspectionResult with validation status, metadata, and rendered config.

    Example:
        result = inspect_adapter(
            "nexus_router_adapter_http:create_adapter",
            config={"base_url": "https://example.com"},
        )
        print(result.render())
    """
    # Run validation first
    validation = validate_adapter(factory_ref, config, strict=strict)

    # Extract data from validation result
    metadata = validation.metadata or {}
    manifest = metadata.get("manifest")

    # Build config params from manifest
    config_params: Optional[list[Dict[str, Any]]] = None
    error_codes: Optional[list[str]] = None
    supported_router_versions: Optional[str] = None

    if manifest:
        # Extract config schema
        config_schema = manifest.get("config_schema", {})
        if config_schema:
            config_params = [
                _render_config_param(name, schema)
                for name, schema in sorted(config_schema.items())
            ]

        # Extract error codes
        error_codes = manifest.get("error_codes")

        # Extract supported versions
        supported_router_versions = manifest.get("supported_router_versions")

    return InspectionResult(
        ok=validation.ok,
        validation=validation,
        adapter_id=metadata.get("adapter_id"),
        adapter_kind=metadata.get("adapter_kind"),
        capabilities=metadata.get("capabilities"),
        manifest=manifest,
        config_params=config_params,
        error_codes=error_codes,
        supported_router_versions=supported_router_versions,
    )
