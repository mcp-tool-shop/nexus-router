"""Tests for validate_adapter (adapter lint tool)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from nexus_router.plugins import (
    STANDARD_CAPABILITIES,
    InspectionResult,
    ValidationCheck,
    ValidationResult,
    inspect_adapter,
    validate_adapter,
)
from nexus_router.tool import inspect_adapter as inspect_adapter_tool
from nexus_router.tool import validate_adapter as validate_adapter_tool


# Add fixtures directory to path for testing
FIXTURES_DIR = Path(__file__).parent / "fixtures"
sys.path.insert(0, str(FIXTURES_DIR))


class TestValidateAdapterSuccess:
    """Test validate_adapter with valid adapters."""

    def test_validate_toy_adapter(self) -> None:
        """Validate toy adapter passes all checks."""
        result = validate_adapter("toy_adapter_pkg:create_adapter")

        assert result.ok is True
        assert result.metadata is not None
        assert result.metadata["adapter_id"] == "toy"
        assert result.metadata["adapter_kind"] == "toy"
        assert result.error is None

        # Check all checks passed
        for check in result.checks:
            assert check.status == "pass", f"{check.check_id} failed: {check.message}"

    def test_validate_with_config(self) -> None:
        """Validate adapter with custom config."""
        result = validate_adapter(
            "toy_adapter_pkg:create_adapter",
            config={"adapter_id": "custom-id", "prefix": "test"},
        )

        assert result.ok is True
        assert result.metadata["adapter_id"] == "custom-id"

    def test_validate_http_adapter(self) -> None:
        """Validate HTTP adapter passes all checks."""
        result = validate_adapter(
            "nexus_router_adapter_http:create_adapter",
            config={"base_url": "https://example.com"},
        )

        assert result.ok is True
        assert result.metadata is not None
        assert result.metadata["adapter_kind"] == "http"
        assert "apply" in result.metadata["capabilities"]
        assert "timeout" in result.metadata["capabilities"]
        assert "external" in result.metadata["capabilities"]


class TestValidateAdapterLoadFailures:
    """Test validate_adapter with load failures."""

    def test_invalid_factory_ref_format(self) -> None:
        """Invalid factory_ref fails LOAD_OK."""
        result = validate_adapter("invalid_format")

        assert result.ok is False
        assert result.metadata is None
        assert result.error is not None
        assert "Expected 'module:function'" in result.error

        load_check = next(c for c in result.checks if c.check_id == "LOAD_OK")
        assert load_check.status == "fail"

    def test_module_not_found(self) -> None:
        """Non-existent module fails LOAD_OK."""
        result = validate_adapter("nonexistent_module_xyz:create_adapter")

        assert result.ok is False
        assert "Failed to import module" in result.error

    def test_function_not_found(self) -> None:
        """Non-existent function fails LOAD_OK."""
        result = validate_adapter("toy_adapter_pkg:nonexistent_function")

        assert result.ok is False
        assert "has no attribute" in result.error

    def test_factory_raises(self) -> None:
        """Factory that raises fails LOAD_OK."""
        result = validate_adapter("toy_adapter_pkg:create_adapter_raises")

        assert result.ok is False
        assert "Intentional factory error" in result.error


class TestValidateAdapterProtocolChecks:
    """Test protocol field validation."""

    def test_missing_protocol_fields(self) -> None:
        """Adapter missing fields fails at load time."""
        result = validate_adapter("toy_adapter_pkg:create_incomplete_adapter")

        assert result.ok is False
        # The load_adapter function catches missing fields
        assert result.error is not None
        assert "did not return a valid DispatchAdapter" in result.error

        load_check = next(c for c in result.checks if c.check_id == "LOAD_OK")
        assert load_check.status == "fail"


class TestValidateAdapterCapabilityChecks:
    """Test capability validation."""

    def test_standard_capabilities_pass(self) -> None:
        """Adapter with standard capabilities passes."""
        result = validate_adapter("toy_adapter_pkg:create_adapter")

        cap_check = next(c for c in result.checks if c.check_id == "CAPABILITIES_VALID")
        assert cap_check.status == "pass"

    def test_unknown_capabilities_strict_fail(self) -> None:
        """Unknown capabilities fail in strict mode."""
        result = validate_adapter(
            "toy_adapter_pkg:create_adapter",
            config={"capabilities": frozenset({"apply", "magic_power"})},
            strict=True,
        )

        assert result.ok is False

        cap_check = next(c for c in result.checks if c.check_id == "CAPABILITIES_VALID")
        assert cap_check.status == "fail"
        assert "magic_power" in cap_check.message

    def test_unknown_capabilities_non_strict_warn(self) -> None:
        """Unknown capabilities warn in non-strict mode."""
        result = validate_adapter(
            "toy_adapter_pkg:create_adapter",
            config={"capabilities": frozenset({"apply", "magic_power"})},
            strict=False,
        )

        # CAPABILITIES_VALID warns, but MANIFEST_CAPS_MATCH fails
        assert result.ok is False  # manifest mismatch causes failure

        cap_check = next(c for c in result.checks if c.check_id == "CAPABILITIES_VALID")
        assert cap_check.status == "warn"
        assert "magic_power" in cap_check.message

        # Verify manifest mismatch is the cause of failure
        manifest_check = next(c for c in result.checks if c.check_id == "MANIFEST_CAPS_MATCH")
        assert manifest_check.status == "fail"


class TestValidationResult:
    """Test ValidationResult serialization."""

    def test_to_dict_success(self) -> None:
        """to_dict() produces correct structure on success."""
        result = validate_adapter("toy_adapter_pkg:create_adapter")
        d = result.to_dict()

        assert "ok" in d
        assert "checks" in d
        assert "metadata" in d
        assert "errors" in d
        assert "warnings" in d
        assert d["ok"] is True
        assert isinstance(d["checks"], list)
        assert isinstance(d["errors"], list)
        assert isinstance(d["warnings"], list)
        assert all("id" in c and "status" in c and "message" in c for c in d["checks"])

    def test_to_dict_failure(self) -> None:
        """to_dict() includes error on failure."""
        result = validate_adapter("nonexistent:function")
        d = result.to_dict()

        assert d["ok"] is False
        assert "error" in d
        assert d["metadata"] is None

    def test_errors_property(self) -> None:
        """errors property returns only failed checks."""
        result = validate_adapter(
            "toy_adapter_pkg:create_adapter",
            config={"capabilities": frozenset({"invented"})},
            strict=True,
        )

        assert result.ok is False
        # Two errors: CAPABILITIES_VALID and MANIFEST_CAPS_MATCH
        error_ids = {e.check_id for e in result.errors}
        assert "CAPABILITIES_VALID" in error_ids
        assert "MANIFEST_CAPS_MATCH" in error_ids
        assert len(result.errors) == 2

    def test_warnings_property(self) -> None:
        """warnings property returns only warned checks."""
        result = validate_adapter(
            "toy_adapter_pkg:create_adapter",
            config={"capabilities": frozenset({"invented"})},
            strict=False,
        )

        # CAPABILITIES_VALID is warn, but MANIFEST_CAPS_MATCH is fail
        assert result.ok is False  # manifest mismatch causes failure
        warning_ids = {w.check_id for w in result.warnings}
        assert "CAPABILITIES_VALID" in warning_ids

    def test_errors_warnings_in_dict(self) -> None:
        """to_dict() includes errors and warnings arrays."""
        result = validate_adapter(
            "toy_adapter_pkg:create_adapter",
            config={"capabilities": frozenset({"invented"})},
            strict=False,
        )
        d = result.to_dict()

        # MANIFEST_CAPS_MATCH fails (error), CAPABILITIES_VALID warns
        error_ids = {e["id"] for e in d["errors"]}
        warning_ids = {w["id"] for w in d["warnings"]}
        assert "MANIFEST_CAPS_MATCH" in error_ids
        assert "CAPABILITIES_VALID" in warning_ids


class TestToolValidateAdapter:
    """Test tool.validate_adapter() public API."""

    def test_tool_api(self) -> None:
        """tool.validate_adapter() works with request dict."""
        response = validate_adapter_tool({
            "factory_ref": "toy_adapter_pkg:create_adapter",
        })

        assert response["ok"] is True
        assert "metadata" in response
        assert "checks" in response

    def test_tool_api_with_config(self) -> None:
        """tool.validate_adapter() passes config to factory."""
        response = validate_adapter_tool({
            "factory_ref": "toy_adapter_pkg:create_adapter",
            "config": {"adapter_id": "tool-test"},
        })

        assert response["ok"] is True
        assert response["metadata"]["adapter_id"] == "tool-test"

    def test_tool_api_strict_option(self) -> None:
        """tool.validate_adapter() respects strict option."""
        # Strict mode (default) - fails on CAPABILITIES_VALID and MANIFEST_CAPS_MATCH
        response = validate_adapter_tool({
            "factory_ref": "toy_adapter_pkg:create_adapter",
            "config": {"capabilities": frozenset({"invented"})},
        })
        assert response["ok"] is False

        # Non-strict mode - CAPABILITIES_VALID warns, but MANIFEST_CAPS_MATCH still fails
        response = validate_adapter_tool({
            "factory_ref": "toy_adapter_pkg:create_adapter",
            "config": {"capabilities": frozenset({"invented"})},
            "strict": False,
        })
        # Still fails because manifest capabilities don't match
        assert response["ok"] is False
        # Verify CAPABILITIES_VALID is warn (strict=False effect)
        caps_check = next(c for c in response["checks"] if c["id"] == "CAPABILITIES_VALID")
        assert caps_check["status"] == "warn"


class TestStandardCapabilities:
    """Test STANDARD_CAPABILITIES constant."""

    def test_standard_capabilities_defined(self) -> None:
        """STANDARD_CAPABILITIES includes expected values."""
        assert "dry_run" in STANDARD_CAPABILITIES
        assert "apply" in STANDARD_CAPABILITIES
        assert "timeout" in STANDARD_CAPABILITIES
        assert "external" in STANDARD_CAPABILITIES
        assert len(STANDARD_CAPABILITIES) == 4


class TestManifestValidation:
    """Test ADAPTER_MANIFEST validation."""

    def test_manifest_present_with_valid_manifest(self) -> None:
        """MANIFEST_PRESENT passes when manifest exists."""
        result = validate_adapter("toy_adapter_pkg:create_adapter")

        manifest_check = next(c for c in result.checks if c.check_id == "MANIFEST_PRESENT")
        assert manifest_check.status == "pass"
        assert "ADAPTER_MANIFEST found" in manifest_check.message

    def test_manifest_schema_valid(self) -> None:
        """MANIFEST_SCHEMA passes with valid manifest structure."""
        result = validate_adapter("toy_adapter_pkg:create_adapter")

        schema_check = next(c for c in result.checks if c.check_id == "MANIFEST_SCHEMA")
        assert schema_check.status == "pass"

    def test_manifest_kind_match(self) -> None:
        """MANIFEST_KIND_MATCH passes when kind matches adapter_kind."""
        result = validate_adapter("toy_adapter_pkg:create_adapter")

        kind_check = next(c for c in result.checks if c.check_id == "MANIFEST_KIND_MATCH")
        assert kind_check.status == "pass"
        assert "toy" in kind_check.message

    def test_manifest_caps_match(self) -> None:
        """MANIFEST_CAPS_MATCH passes when capabilities match."""
        result = validate_adapter("toy_adapter_pkg:create_adapter")

        caps_check = next(c for c in result.checks if c.check_id == "MANIFEST_CAPS_MATCH")
        assert caps_check.status == "pass"

    def test_manifest_caps_mismatch_fails(self) -> None:
        """MANIFEST_CAPS_MATCH fails when capabilities don't match."""
        # Pass custom capabilities that differ from manifest
        result = validate_adapter(
            "toy_adapter_pkg:create_adapter",
            config={"capabilities": frozenset({"timeout"})},  # Manifest has apply, dry_run
        )

        caps_check = next(c for c in result.checks if c.check_id == "MANIFEST_CAPS_MATCH")
        assert caps_check.status == "fail"
        assert "missing from manifest" in caps_check.message

    def test_manifest_in_metadata(self) -> None:
        """Manifest is included in metadata when present."""
        result = validate_adapter("toy_adapter_pkg:create_adapter")

        assert "manifest" in result.metadata
        manifest = result.metadata["manifest"]
        assert manifest["schema_version"] == 1
        assert manifest["kind"] == "toy"
        assert "apply" in manifest["capabilities"]
        assert "config_schema" in manifest

    def test_http_adapter_manifest(self) -> None:
        """HTTP adapter has valid manifest with full config_schema."""
        result = validate_adapter(
            "nexus_router_adapter_http:create_adapter",
            config={"base_url": "https://example.com"},
        )

        assert result.ok is True

        # All manifest checks pass
        for check in result.checks:
            if check.check_id.startswith("MANIFEST_"):
                assert check.status == "pass", f"{check.check_id}: {check.message}"

        # Manifest has expected structure
        manifest = result.metadata["manifest"]
        assert manifest["kind"] == "http"
        assert "base_url" in manifest["config_schema"]
        assert manifest["config_schema"]["base_url"]["required"] is True
        assert "TIMEOUT" in manifest["error_codes"]


class TestInspectAdapter:
    """Test inspect_adapter() function."""

    def test_inspect_toy_adapter(self) -> None:
        """inspect_adapter returns InspectionResult with correct fields."""
        result = inspect_adapter("toy_adapter_pkg:create_adapter")

        assert isinstance(result, InspectionResult)
        assert result.ok is True
        assert result.adapter_id == "toy"
        assert result.adapter_kind == "toy"
        assert result.capabilities is not None
        assert "apply" in result.capabilities
        assert "dry_run" in result.capabilities

    def test_inspect_http_adapter_with_manifest(self) -> None:
        """inspect_adapter extracts manifest data."""
        result = inspect_adapter(
            "nexus_router_adapter_http:create_adapter",
            config={"base_url": "https://example.com"},
        )

        assert result.ok is True
        assert result.adapter_kind == "http"
        assert result.supported_router_versions == ">=0.9,<1.0"
        assert result.error_codes is not None
        assert "TIMEOUT" in result.error_codes
        assert "CONNECTION_FAILED" in result.error_codes

    def test_inspect_config_params(self) -> None:
        """inspect_adapter extracts config_params from manifest."""
        result = inspect_adapter(
            "nexus_router_adapter_http:create_adapter",
            config={"base_url": "https://example.com"},
        )

        assert result.config_params is not None
        param_names = {p["name"] for p in result.config_params}
        assert "base_url" in param_names
        assert "timeout_s" in param_names
        assert "headers" in param_names

        # Check base_url param structure
        base_url_param = next(p for p in result.config_params if p["name"] == "base_url")
        assert base_url_param["type"] == "string"
        assert base_url_param["required"] is True
        assert "description" in base_url_param

        # Check timeout_s param has default
        timeout_param = next(p for p in result.config_params if p["name"] == "timeout_s")
        assert timeout_param["required"] is False
        assert timeout_param["default"] == 30.0

    def test_inspect_to_dict(self) -> None:
        """to_dict() includes all expected fields."""
        result = inspect_adapter("toy_adapter_pkg:create_adapter")
        d = result.to_dict()

        assert "ok" in d
        assert "adapter_id" in d
        assert "adapter_kind" in d
        assert "capabilities" in d
        assert "validation" in d
        assert "manifest" in d
        assert d["ok"] is True

    def test_inspect_render(self) -> None:
        """render() produces human-readable output."""
        result = inspect_adapter(
            "nexus_router_adapter_http:create_adapter",
            config={"base_url": "https://example.com"},
        )

        rendered = result.render()

        assert "Adapter validation PASSED" in rendered
        assert "http" in rendered
        assert "Capabilities:" in rendered
        assert "Configuration Parameters" in rendered
        assert "base_url" in rendered
        assert "TIMEOUT" in rendered

    def test_inspect_errors_property(self) -> None:
        """errors property returns validation errors."""
        result = inspect_adapter(
            "toy_adapter_pkg:create_adapter",
            config={"capabilities": frozenset({"invented"})},
            strict=True,
        )

        assert result.ok is False
        assert len(result.errors) > 0
        error_ids = {e.check_id for e in result.errors}
        assert "CAPABILITIES_VALID" in error_ids

    def test_inspect_warnings_property(self) -> None:
        """warnings property returns validation warnings."""
        # Use an adapter without manifest to get MANIFEST_PRESENT warning
        # Since toy_adapter has a manifest, we test via validation result
        result = inspect_adapter("toy_adapter_pkg:create_adapter")
        # No warnings expected for toy adapter with manifest
        assert len(result.warnings) == 0


class TestInspectAdapterTool:
    """Test tool.inspect_adapter() public API."""

    def test_tool_api(self) -> None:
        """tool.inspect_adapter() works with request dict."""
        response = inspect_adapter_tool({
            "factory_ref": "toy_adapter_pkg:create_adapter",
        })

        assert response["ok"] is True
        assert response["adapter_id"] == "toy"
        assert response["adapter_kind"] == "toy"
        assert "validation" in response

    def test_tool_api_with_render(self) -> None:
        """tool.inspect_adapter() includes rendered output when requested."""
        response = inspect_adapter_tool({
            "factory_ref": "nexus_router_adapter_http:create_adapter",
            "config": {"base_url": "https://example.com"},
            "render": True,
        })

        assert "rendered" in response
        assert "Adapter validation PASSED" in response["rendered"]
        assert "Configuration Parameters" in response["rendered"]

    def test_tool_api_without_render(self) -> None:
        """tool.inspect_adapter() omits rendered output by default."""
        response = inspect_adapter_tool({
            "factory_ref": "toy_adapter_pkg:create_adapter",
        })

        assert "rendered" not in response

    def test_tool_api_strict_option(self) -> None:
        """tool.inspect_adapter() respects strict option."""
        response = inspect_adapter_tool({
            "factory_ref": "toy_adapter_pkg:create_adapter",
            "config": {"capabilities": frozenset({"invented"})},
            "strict": True,
        })

        assert response["ok"] is False
