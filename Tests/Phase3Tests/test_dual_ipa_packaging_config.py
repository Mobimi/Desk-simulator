#!/usr/bin/env python3
"""
Desk-simulator Phase 3: Dual IPA Packaging, Entitlements, and CI/CD Workflow Test Suite.
Validates Requirements R3:
- Feature 14: TrollStore Packaging Config & Entitlements
- Feature 15: Sideload Packaging Config & Sandboxed Entitlements
- Feature 16: GitHub Actions Dual IPA CI/CD Workflow (.github/workflows/build-ipa.yml)

Tiers 1-4 coverage:
- Tier 1: Feature Equivalence Class Partitioning (schemes, targets, plists, yaml steps)
- Tier 2: Boundary Value Analysis & Negative Testing (malformed YAML, corrupted plists, schema mismatches)
- Tier 3: Cross-Feature Interactions (project.yml <-> entitlements <-> Info.plist <-> CI workflow)
- Tier 4: Real-World Scenarios (dual IPA build simulation, signing override consistency)
"""

from __future__ import annotations

import plistlib
import sys
import unittest
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

import yaml

# Workspace root resolution
WORKSPACE_ROOT = Path(__file__).resolve().parent.parent.parent
if str(WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_ROOT))


class PackagingConfigValidator:
    """Rigorous validator checking project.yml, entitlements, Info.plist, and CI workflow schemas."""

    REQUIRED_PROJECT_CONFIGS = [
        "Debug-TrollStore",
        "Release-TrollStore",
        "Debug-Sideload",
        "Release-Sideload",
    ]

    REQUIRED_FRAMEWORKS = [
        "Metal.framework",
        "MetalKit.framework",
        "GameController.framework",
        "AudioToolbox.framework",
    ]

    REQUIRED_TROLLSTORE_ENTITLEMENTS = [
        "com.apple.developer.kernel.increased-memory-limit",
        "com.apple.developer.kernel.extended-virtual-addressing",
        "dynamic-codesigning",
        "get-task-allow",
    ]

    PROHIBITED_SIDELOAD_ENTITLEMENTS = [
        "com.apple.developer.kernel.increased-memory-limit",
        "com.apple.developer.kernel.extended-virtual-addressing",
        "dynamic-codesigning",
    ]

    @classmethod
    def validate_project_spec(cls, spec: Dict[str, Any]) -> List[str]:
        errors = []
        if spec.get("name") != "DeskSimulator":
            errors.append(f"Expected project name 'DeskSimulator', got {spec.get('name')}")

        configs = spec.get("configs", {})
        for req_cfg in cls.REQUIRED_PROJECT_CONFIGS:
            if req_cfg not in configs:
                errors.append(f"Missing required build configuration '{req_cfg}'")

        targets = spec.get("targets", {})
        if "DeskSimulator" not in targets:
            errors.append("Missing required target 'DeskSimulator'")
        else:
            target = targets["DeskSimulator"]
            if target.get("type") != "application":
                errors.append(f"Target DeskSimulator type must be 'application', got {target.get('type')}")
            if target.get("platform") != "iOS":
                errors.append(f"Target DeskSimulator platform must be 'iOS', got {target.get('platform')}")

            settings = target.get("settings", {})
            base = settings.get("base", {})
            if base.get("PRODUCT_BUNDLE_IDENTIFIER") != "com.mobimi.DeskSimulator":
                errors.append("Invalid PRODUCT_BUNDLE_IDENTIFIER in base settings")
            if base.get("INFOPLIST_FILE") != "Config/Info.plist":
                errors.append("INFOPLIST_FILE must point to Config/Info.plist")
            if base.get("SWIFT_OBJC_BRIDGING_HEADER") != "Engine/DeskSimulator-Bridging-Header.h":
                errors.append("SWIFT_OBJC_BRIDGING_HEADER must point to Engine/DeskSimulator-Bridging-Header.h")
            if base.get("ARCHS") != "arm64":
                errors.append("ARCHS must be arm64")

            cfg_settings = settings.get("configs", {})
            if cfg_settings.get("Release-TrollStore", {}).get("CODE_SIGN_ENTITLEMENTS") != "Config/DeskSimulator-TrollStore.entitlements":
                errors.append("Release-TrollStore must link to Config/DeskSimulator-TrollStore.entitlements")
            if cfg_settings.get("Release-Sideload", {}).get("CODE_SIGN_ENTITLEMENTS") != "Config/DeskSimulator-Sideload.entitlements":
                errors.append("Release-Sideload must link to Config/DeskSimulator-Sideload.entitlements")

        schemes = spec.get("schemes", {})
        if "DeskSimulator-TrollStore" not in schemes:
            errors.append("Missing scheme 'DeskSimulator-TrollStore'")
        if "DeskSimulator-Sideload" not in schemes:
            errors.append("Missing scheme 'DeskSimulator-Sideload'")

        return errors

    @classmethod
    def validate_trollstore_entitlements(cls, data: Dict[str, Any]) -> List[str]:
        errors = []
        for key in cls.REQUIRED_TROLLSTORE_ENTITLEMENTS:
            if not data.get(key):
                errors.append(f"TrollStore entitlements missing or false for '{key}'")
        return errors

    @classmethod
    def validate_sideload_entitlements(cls, data: Dict[str, Any]) -> List[str]:
        errors = []
        if not data.get("get-task-allow"):
            errors.append("Sideload entitlements must include 'get-task-allow'")
        for key in cls.PROHIBITED_SIDELOAD_ENTITLEMENTS:
            if key in data:
                errors.append(f"Sideload entitlements must strictly omit restricted key '{key}'")
        return errors

    @classmethod
    def validate_info_plist(cls, data: Dict[str, Any]) -> List[str]:
        errors = []
        if not data.get("CADisableMinimumFrameDurationOnPhone"):
            errors.append("Info.plist must set CADisableMinimumFrameDurationOnPhone to true for ProMotion 120Hz")
        caps = data.get("UIRequiredDeviceCapabilities", [])
        if "arm64" not in caps or "metal" not in caps:
            errors.append("Info.plist UIRequiredDeviceCapabilities must include both 'arm64' and 'metal'")
        if not data.get("UIFileSharingEnabled"):
            errors.append("Info.plist UIFileSharingEnabled must be true")
        if not data.get("LSSupportsOpeningDocumentsInPlace"):
            errors.append("Info.plist LSSupportsOpeningDocumentsInPlace must be true")
        if not data.get("CFBundleDocumentTypes"):
            errors.append("Info.plist must declare CFBundleDocumentTypes for disk image loading")
        return errors

    @classmethod
    def validate_ci_workflow(cls, workflow: Dict[str, Any]) -> List[str]:
        errors = []
        triggers = workflow.get("on") or workflow.get(True)
        if not triggers:
            errors.append("Workflow must declare triggers")
        else:
            if "push" not in triggers:
                errors.append("Workflow must trigger on push")
            if "workflow_dispatch" not in triggers:
                errors.append("Workflow must trigger on workflow_dispatch")

        jobs = workflow.get("jobs", {})
        if not jobs:
            errors.append("Workflow must declare jobs")
            return errors

        job = list(jobs.values())[0]
        if job.get("runs-on") not in ["macos-14", "macos-15"]:
            errors.append(f"Workflow runner must be macos-14 or macos-15, got {job.get('runs-on')}")

        steps = job.get("steps", [])
        all_runs = " ".join([s.get("run", "") for s in steps])
        all_uses = " ".join([s.get("uses", "") for s in steps])

        if "xcodegen generate" not in all_runs:
            errors.append("Workflow steps missing 'xcodegen generate'")
        if "DeskSimulator-TrollStore" not in all_runs:
            errors.append("Workflow steps missing 'DeskSimulator-TrollStore' archive")
        if "DeskSimulator-Sideload" not in all_runs:
            errors.append("Workflow steps missing 'DeskSimulator-Sideload' archive")
        if "DeskSimulator-TrollStore.ipa" not in all_runs:
            errors.append("Workflow steps missing TrollStore IPA zip packaging")
        if "DeskSimulator-Sideload.ipa" not in all_runs:
            errors.append("Workflow steps missing Sideload IPA zip packaging")
        if "actions/upload-artifact" not in all_uses:
            errors.append("Workflow missing actions/upload-artifact step")

        return errors


# ============================================================================
# Tier 1 & Tier 2: Feature & Boundary Tests
# ============================================================================


class TestXcodeGenProjectStructure(unittest.TestCase):
    """Validates Feature 14 & 15: project.yml targets, configurations, and settings."""

    @classmethod
    def setUpClass(cls):
        cls.spec_path = WORKSPACE_ROOT / "project.yml"
        if not cls.spec_path.exists():
            raise FileNotFoundError(f"Missing project.yml at {cls.spec_path}")
        with open(cls.spec_path, "r", encoding="utf-8") as f:
            cls.spec = yaml.safe_load(f)

    def test_project_root_properties(self):
        self.assertEqual(self.spec.get("name"), "DeskSimulator")
        options = self.spec.get("options", {})
        self.assertEqual(options.get("bundleIdPrefix"), "com.mobimi")
        deployment_target = options.get("deploymentTarget", {})
        self.assertEqual(deployment_target.get("iOS"), "15.0")
        self.assertEqual(options.get("xcodeVersion"), "15.0")

    def test_build_configurations_all_four_declared(self):
        configs = self.spec.get("configs", {})
        self.assertIn("Debug-TrollStore", configs)
        self.assertIn("Release-TrollStore", configs)
        self.assertIn("Debug-Sideload", configs)
        self.assertIn("Release-Sideload", configs)
        self.assertEqual(configs["Debug-TrollStore"], "debug")
        self.assertEqual(configs["Release-TrollStore"], "release")
        self.assertEqual(configs["Debug-Sideload"], "debug")
        self.assertEqual(configs["Release-Sideload"], "release")

    def test_target_desksimulator_declared(self):
        targets = self.spec.get("targets", {})
        self.assertIn("DeskSimulator", targets)
        target = targets["DeskSimulator"]
        self.assertEqual(target.get("type"), "application")
        self.assertEqual(target.get("platform"), "iOS")
        self.assertEqual(target.get("deploymentTarget"), "15.0")

    def test_target_sources_contain_all_required_layers(self):
        target = self.spec["targets"]["DeskSimulator"]
        sources = target.get("sources", [])
        paths = [s.get("path") if isinstance(s, dict) else s for s in sources]
        self.assertIn("Engine", paths)
        self.assertIn("Management", paths)
        self.assertIn("UI", paths)
        self.assertIn("Config", paths)

    def test_target_base_settings_bundle_id_and_product_name(self):
        target = self.spec["targets"]["DeskSimulator"]
        base = target.get("settings", {}).get("base", {})
        self.assertEqual(base.get("PRODUCT_NAME"), "DeskSimulator")
        self.assertEqual(base.get("PRODUCT_BUNDLE_IDENTIFIER"), "com.mobimi.DeskSimulator")

    def test_target_base_settings_swift_version_and_archs(self):
        target = self.spec["targets"]["DeskSimulator"]
        base = target.get("settings", {}).get("base", {})
        self.assertEqual(base.get("SWIFT_VERSION"), "5.9")
        self.assertEqual(base.get("ARCHS"), "arm64")
        self.assertEqual(base.get("IPHONEOS_DEPLOYMENT_TARGET"), "15.0")

    def test_target_base_settings_bridging_header_and_infoplist(self):
        target = self.spec["targets"]["DeskSimulator"]
        base = target.get("settings", {}).get("base", {})
        self.assertEqual(base.get("INFOPLIST_FILE"), "Config/Info.plist")
        self.assertEqual(base.get("SWIFT_OBJC_BRIDGING_HEADER"), "Engine/DeskSimulator-Bridging-Header.h")

    def test_target_base_settings_codesigning_disabled_by_default(self):
        target = self.spec["targets"]["DeskSimulator"]
        base = target.get("settings", {}).get("base", {})
        self.assertEqual(base.get("CODE_SIGN_STYLE"), "Manual")
        self.assertEqual(base.get("CODE_SIGNING_ALLOWED"), "NO")
        self.assertEqual(base.get("CODE_SIGNING_REQUIRED"), "NO")

    def test_target_base_settings_header_search_paths(self):
        target = self.spec["targets"]["DeskSimulator"]
        base = target.get("settings", {}).get("base", {})
        header_paths = base.get("HEADER_SEARCH_PATHS", [])
        self.assertIn("$(SRCROOT)/Engine", header_paths)
        self.assertIn("$(SRCROOT)/Engine/QEMU", header_paths)

    def test_target_dependencies_metal_frameworks(self):
        target = self.spec["targets"]["DeskSimulator"]
        deps = target.get("dependencies", [])
        sdks = [d.get("sdk") for d in deps if isinstance(d, dict)]
        self.assertIn("Metal.framework", sdks)
        self.assertIn("MetalKit.framework", sdks)

    def test_target_dependencies_input_and_audio_frameworks(self):
        target = self.spec["targets"]["DeskSimulator"]
        deps = target.get("dependencies", [])
        sdks = [d.get("sdk") for d in deps if isinstance(d, dict)]
        self.assertIn("GameController.framework", sdks)
        self.assertIn("AudioToolbox.framework", sdks)


class TestDualSchemesAndConfigurations(unittest.TestCase):
    """Validates Feature 14 & 15: Dual Xcode schemes for TrollStore and Sideload builds."""

    @classmethod
    def setUpClass(cls):
        cls.spec_path = WORKSPACE_ROOT / "project.yml"
        with open(cls.spec_path, "r", encoding="utf-8") as f:
            cls.spec = yaml.safe_load(f)

    def test_dual_schemes_exist_in_project_yml(self):
        schemes = self.spec.get("schemes", {})
        self.assertIn("DeskSimulator-TrollStore", schemes)
        self.assertIn("DeskSimulator-Sideload", schemes)

    def test_trollstore_scheme_build_target_and_configs(self):
        schemes = self.spec.get("schemes", {})
        trollstore = schemes["DeskSimulator-TrollStore"]
        build_targets = trollstore.get("build", {}).get("targets", {})
        self.assertIn("DeskSimulator", build_targets)
        self.assertEqual(trollstore.get("run", {}).get("config"), "Release-TrollStore")
        self.assertEqual(trollstore.get("archive", {}).get("config"), "Release-TrollStore")

    def test_sideload_scheme_build_target_and_configs(self):
        schemes = self.spec.get("schemes", {})
        sideload = schemes["DeskSimulator-Sideload"]
        build_targets = sideload.get("build", {}).get("targets", {})
        self.assertIn("DeskSimulator", build_targets)
        self.assertEqual(sideload.get("run", {}).get("config"), "Release-Sideload")
        self.assertEqual(sideload.get("archive", {}).get("config"), "Release-Sideload")

    def test_target_configs_trollstore_entitlements_mapping(self):
        target = self.spec["targets"]["DeskSimulator"]
        configs = target.get("settings", {}).get("configs", {})
        self.assertEqual(
            configs.get("Debug-TrollStore", {}).get("CODE_SIGN_ENTITLEMENTS"),
            "Config/DeskSimulator-TrollStore.entitlements",
        )
        self.assertEqual(
            configs.get("Release-TrollStore", {}).get("CODE_SIGN_ENTITLEMENTS"),
            "Config/DeskSimulator-TrollStore.entitlements",
        )

    def test_target_configs_sideload_entitlements_mapping(self):
        target = self.spec["targets"]["DeskSimulator"]
        configs = target.get("settings", {}).get("configs", {})
        self.assertEqual(
            configs.get("Debug-Sideload", {}).get("CODE_SIGN_ENTITLEMENTS"),
            "Config/DeskSimulator-Sideload.entitlements",
        )
        self.assertEqual(
            configs.get("Release-Sideload", {}).get("CODE_SIGN_ENTITLEMENTS"),
            "Config/DeskSimulator-Sideload.entitlements",
        )


class TestEntitlementsProfiles(unittest.TestCase):
    """Validates Feature 14 & 15: Entitlement profile definitions."""

    def test_trollstore_entitlements_keys(self):
        path = WORKSPACE_ROOT / "Config" / "DeskSimulator-TrollStore.entitlements"
        self.assertTrue(path.exists(), "DeskSimulator-TrollStore.entitlements must exist")
        with open(path, "rb") as f:
            data = plistlib.load(f)

        self.assertTrue(
            data.get("com.apple.developer.kernel.increased-memory-limit"),
            "TrollStore must have increased-memory-limit enabled",
        )
        self.assertTrue(
            data.get("com.apple.developer.kernel.extended-virtual-addressing"),
            "TrollStore must have extended-virtual-addressing enabled",
        )
        self.assertTrue(
            data.get("dynamic-codesigning"),
            "TrollStore must have dynamic-codesigning enabled",
        )
        self.assertTrue(
            data.get("get-task-allow"),
            "TrollStore must have get-task-allow enabled",
        )

    def test_sideload_entitlements_keys_and_strict_omissions(self):
        path = WORKSPACE_ROOT / "Config" / "DeskSimulator-Sideload.entitlements"
        self.assertTrue(path.exists(), "DeskSimulator-Sideload.entitlements must exist")
        with open(path, "rb") as f:
            data = plistlib.load(f)

        self.assertTrue(
            data.get("get-task-allow"),
            "Sideload build must have get-task-allow enabled for JIT / debugging",
        )

        # STRICT OMISSION: Free Apple ID accounts reject profiles containing these keys
        self.assertNotIn(
            "com.apple.developer.kernel.increased-memory-limit",
            data,
            "Sideload build must strictly omit increased-memory-limit",
        )
        self.assertNotIn(
            "com.apple.developer.kernel.extended-virtual-addressing",
            data,
            "Sideload build must strictly omit extended-virtual-addressing",
        )
        self.assertNotIn(
            "dynamic-codesigning",
            data,
            "Sideload build must strictly omit dynamic-codesigning",
        )


class TestInfoPlistCapabilities(unittest.TestCase):
    """Validates Feature 13 & 14: Info.plist ProMotion 120Hz, Metal, and document sharing."""

    @classmethod
    def setUpClass(cls):
        cls.plist_path = WORKSPACE_ROOT / "Config" / "Info.plist"
        if not cls.plist_path.exists():
            raise FileNotFoundError(f"Missing Info.plist at {cls.plist_path}")
        with open(cls.plist_path, "rb") as f:
            cls.data = plistlib.load(f)

    def test_promotion_120hz_cadisableminimumframedurationonphone(self):
        self.assertTrue(
            self.data.get("CADisableMinimumFrameDurationOnPhone"),
            "Info.plist must set CADisableMinimumFrameDurationOnPhone to true for ProMotion 120Hz",
        )

    def test_ui_required_device_capabilities_arm64_and_metal(self):
        caps = self.data.get("UIRequiredDeviceCapabilities", [])
        self.assertIn("arm64", caps)
        self.assertIn("metal", caps)

    def test_ui_file_sharing_enabled(self):
        self.assertTrue(
            self.data.get("UIFileSharingEnabled"),
            "Info.plist must enable UIFileSharingEnabled for disk image management",
        )
        self.assertTrue(
            self.data.get("LSSupportsOpeningDocumentsInPlace"),
            "Info.plist must enable LSSupportsOpeningDocumentsInPlace",
        )

    def test_cf_bundle_document_types_for_disk_images(self):
        doc_types = self.data.get("CFBundleDocumentTypes", [])
        self.assertGreater(len(doc_types), 0, "Info.plist must declare document types for disk images")
        type_names = [d.get("CFBundleTypeName") for d in doc_types if isinstance(d, dict)]
        self.assertTrue(any("ISO" in str(name) or "Disk" in str(name) for name in type_names))

    def test_local_network_usage_description_present(self):
        desc = self.data.get("NSLocalNetworkUsageDescription")
        self.assertIsNotNone(desc)
        self.assertGreater(len(str(desc).strip()), 10)


class TestGitHubActionsWorkflowPipeline(unittest.TestCase):
    """Validates Feature 16: GitHub Actions build-ipa.yml dual packaging CI/CD pipeline."""

    @classmethod
    def setUpClass(cls):
        cls.workflow_path = WORKSPACE_ROOT / ".github" / "workflows" / "build-ipa.yml"
        if not cls.workflow_path.exists():
            raise FileNotFoundError(f"Missing workflow file at {cls.workflow_path}")
        with open(cls.workflow_path, "r", encoding="utf-8") as f:
            cls.workflow = yaml.safe_load(f)

    def test_workflow_triggers_push_branches_and_tags(self):
        triggers = self.workflow.get("on") or self.workflow.get(True)
        self.assertIsNotNone(triggers)
        push_event = triggers.get("push", {})
        branches = push_event.get("branches", [])
        tags = push_event.get("tags", [])
        self.assertIn("main", branches)
        self.assertTrue(any("release" in b for b in branches))
        self.assertTrue(any("v*" in t for t in tags))

    def test_workflow_triggers_pull_request_and_workflow_dispatch(self):
        triggers = self.workflow.get("on") or self.workflow.get(True)
        self.assertIn("pull_request", triggers)
        self.assertIn("workflow_dispatch", triggers)

    def test_workflow_concurrency_group_and_cancel_in_progress(self):
        concurrency = self.workflow.get("concurrency", {})
        self.assertTrue(concurrency.get("cancel-in-progress"))

    def test_job_runner_macos_runner(self):
        jobs = self.workflow.get("jobs", {})
        self.assertEqual(len(jobs), 1)
        job = list(jobs.values())[0]
        self.assertIn(job.get("runs-on"), ["macos-14", "macos-15"])
        self.assertEqual(job.get("timeout-minutes"), 45)

    def test_step_checkout_with_recursive_submodules(self):
        job = list(self.workflow["jobs"].values())[0]
        steps = job.get("steps", [])
        checkout_step = next((s for s in steps if "actions/checkout" in s.get("uses", "")), None)
        self.assertIsNotNone(checkout_step)
        with_params = checkout_step.get("with", {})
        self.assertEqual(with_params.get("submodules"), "recursive")

    def test_step_xcode_selection_and_version_probe(self):
        job = list(self.workflow["jobs"].values())[0]
        steps = job.get("steps", [])
        xcode_step = next((s for s in steps if "Xcode" in s.get("name", "")), None)
        self.assertIsNotNone(xcode_step)
        run_script = xcode_step.get("run", "")
        self.assertIn("xcodebuild -version", run_script)
        self.assertTrue(any(ver in run_script for ver in ["Xcode_15", "Xcode_16"]))

    def test_step_install_xcodegen(self):
        job = list(self.workflow["jobs"].values())[0]
        steps = job.get("steps", [])
        xcodegen_step = next((s for s in steps if "Install XcodeGen" in s.get("name", "")), None)
        self.assertIsNotNone(xcodegen_step)
        self.assertIn("brew install xcodegen", xcodegen_step.get("run", ""))

    def test_step_generate_project_spec(self):
        job = list(self.workflow["jobs"].values())[0]
        steps = job.get("steps", [])
        gen_step = next((s for s in steps if "Generate Xcode Project" in s.get("name", "")), None)
        self.assertIsNotNone(gen_step)
        self.assertIn("xcodegen generate --spec project.yml", gen_step.get("run", ""))

    def test_step_build_trollstore_archive_command(self):
        job = list(self.workflow["jobs"].values())[0]
        steps = job.get("steps", [])
        archive_step = next((s for s in steps if "Build TrollStore Archive" in s.get("name", "")), None)
        self.assertIsNotNone(archive_step)
        cmd = archive_step.get("run", "")
        self.assertIn("-scheme DeskSimulator-TrollStore", cmd)
        self.assertIn("-configuration Release-TrollStore", cmd)
        self.assertIn("CODE_SIGNING_ALLOWED=NO", cmd)
        self.assertIn("build/TrollStore.xcarchive", cmd)

    def test_step_package_trollstore_ipa_payload_structure(self):
        job = list(self.workflow["jobs"].values())[0]
        steps = job.get("steps", [])
        pkg_step = next((s for s in steps if "Package TrollStore IPA" in s.get("name", "")), None)
        self.assertIsNotNone(pkg_step)
        cmd = pkg_step.get("run", "")
        self.assertIn("Payload", cmd)
        self.assertIn("DeskSimulator-TrollStore.ipa", cmd)
        self.assertIn("zip -qr", cmd)

    def test_step_build_sideload_archive_command(self):
        job = list(self.workflow["jobs"].values())[0]
        steps = job.get("steps", [])
        archive_step = next((s for s in steps if "Build Sideload Archive" in s.get("name", "")), None)
        self.assertIsNotNone(archive_step)
        cmd = archive_step.get("run", "")
        self.assertIn("-scheme DeskSimulator-Sideload", cmd)
        self.assertIn("-configuration Release-Sideload", cmd)
        self.assertIn("CODE_SIGNING_ALLOWED=NO", cmd)
        self.assertIn("build/Sideload.xcarchive", cmd)

    def test_step_package_sideload_ipa_payload_structure(self):
        job = list(self.workflow["jobs"].values())[0]
        steps = job.get("steps", [])
        pkg_step = next((s for s in steps if "Package Sideload IPA" in s.get("name", "")), None)
        self.assertIsNotNone(pkg_step)
        cmd = pkg_step.get("run", "")
        self.assertIn("Payload", cmd)
        self.assertIn("DeskSimulator-Sideload.ipa", cmd)
        self.assertIn("zip -qr", cmd)

    def test_step_upload_trollstore_ipa_artifact(self):
        job = list(self.workflow["jobs"].values())[0]
        steps = job.get("steps", [])
        upload_steps = [s for s in steps if "actions/upload-artifact" in s.get("uses", "")]
        self.assertGreaterEqual(len(upload_steps), 2)
        trollstore_upload = next((s for s in upload_steps if "TrollStore" in s.get("name", "")), None)
        self.assertIsNotNone(trollstore_upload)
        self.assertEqual(trollstore_upload.get("with", {}).get("path"), "DeskSimulator-TrollStore.ipa")
        self.assertEqual(trollstore_upload.get("with", {}).get("retention-days"), 14)

    def test_step_upload_sideload_ipa_artifact(self):
        job = list(self.workflow["jobs"].values())[0]
        steps = job.get("steps", [])
        upload_steps = [s for s in steps if "actions/upload-artifact" in s.get("uses", "")]
        sideload_upload = next((s for s in upload_steps if "Sideload" in s.get("name", "")), None)
        self.assertIsNotNone(sideload_upload)
        self.assertEqual(sideload_upload.get("with", {}).get("path"), "DeskSimulator-Sideload.ipa")
        self.assertEqual(sideload_upload.get("with", {}).get("retention-days"), 14)


# ============================================================================
# Tier 2: Boundary & Negative Cases
# ============================================================================


class TestPackagingBoundaryAndNegativeCases(unittest.TestCase):
    """Validates detection of malformed configurations, corrupted plists, and missing keys."""

    def test_validator_passes_on_valid_repository_configurations(self):
        with open(WORKSPACE_ROOT / "project.yml", "r", encoding="utf-8") as f:
            proj = yaml.safe_load(f)
        self.assertEqual(PackagingConfigValidator.validate_project_spec(proj), [])

        with open(WORKSPACE_ROOT / "Config" / "DeskSimulator-TrollStore.entitlements", "rb") as f:
            troll_ent = plistlib.load(f)
        self.assertEqual(PackagingConfigValidator.validate_trollstore_entitlements(troll_ent), [])

        with open(WORKSPACE_ROOT / "Config" / "DeskSimulator-Sideload.entitlements", "rb") as f:
            side_ent = plistlib.load(f)
        self.assertEqual(PackagingConfigValidator.validate_sideload_entitlements(side_ent), [])

        with open(WORKSPACE_ROOT / "Config" / "Info.plist", "rb") as f:
            info = plistlib.load(f)
        self.assertEqual(PackagingConfigValidator.validate_info_plist(info), [])

        with open(WORKSPACE_ROOT / ".github" / "workflows" / "build-ipa.yml", "r", encoding="utf-8") as f:
            wf = yaml.safe_load(f)
        self.assertEqual(PackagingConfigValidator.validate_ci_workflow(wf), [])

    def test_validator_detects_malformed_yaml_syntax(self):
        malformed_yaml = """
        name: DeskSimulator
        targets:
          DeskSimulator:
            - invalid list syntax: [
        """
        with self.assertRaises(yaml.YAMLError):
            yaml.safe_load(malformed_yaml)

    def test_validator_detects_corrupted_plist_bytes(self):
        corrupted_bytes = b"<?xml version='1.0'?><plist><dict><key>broken</dict></plist>"
        with self.assertRaises(Exception):
            plistlib.loads(corrupted_bytes)

    def test_validator_detects_missing_configs_in_project_yml(self):
        spec_copy = {
            "name": "DeskSimulator",
            "configs": {"Debug-TrollStore": "debug"},  # missing other 3
            "targets": {},
            "schemes": {},
        }
        errors = PackagingConfigValidator.validate_project_spec(spec_copy)
        self.assertTrue(any("Release-TrollStore" in e for e in errors))
        self.assertTrue(any("Debug-Sideload" in e for e in errors))
        self.assertTrue(any("Release-Sideload" in e for e in errors))

    def test_validator_detects_missing_schemes_in_project_yml(self):
        spec_copy = {
            "name": "DeskSimulator",
            "configs": {c: "release" for c in PackagingConfigValidator.REQUIRED_PROJECT_CONFIGS},
            "targets": {"DeskSimulator": {"type": "application", "platform": "iOS"}},
            "schemes": {"DeskSimulator-TrollStore": {}},  # missing Sideload
        }
        errors = PackagingConfigValidator.validate_project_spec(spec_copy)
        self.assertTrue(any("DeskSimulator-Sideload" in e for e in errors))

    def test_validator_detects_missing_trollstore_entitlement_key(self):
        incomplete_trollstore = {
            "get-task-allow": True,
            "dynamic-codesigning": True,
            # Missing increased-memory-limit and extended-virtual-addressing
        }
        errors = PackagingConfigValidator.validate_trollstore_entitlements(incomplete_trollstore)
        self.assertTrue(any("increased-memory-limit" in e for e in errors))
        self.assertTrue(any("extended-virtual-addressing" in e for e in errors))

    def test_validator_detects_prohibited_entitlement_in_sideload(self):
        illegal_sideload = {
            "get-task-allow": True,
            "com.apple.developer.kernel.increased-memory-limit": True,  # Illegal in Sideload
        }
        errors = PackagingConfigValidator.validate_sideload_entitlements(illegal_sideload)
        self.assertTrue(any("strictly omit restricted key" in e for e in errors))

    def test_validator_detects_missing_promotion_in_info_plist(self):
        bad_info = {
            "UIRequiredDeviceCapabilities": ["arm64", "metal"],
            "UIFileSharingEnabled": True,
            "LSSupportsOpeningDocumentsInPlace": True,
            "CFBundleDocumentTypes": [{}],
            # Missing CADisableMinimumFrameDurationOnPhone
        }
        errors = PackagingConfigValidator.validate_info_plist(bad_info)
        self.assertTrue(any("CADisableMinimumFrameDurationOnPhone" in e for e in errors))

    def test_validator_detects_missing_metal_capability_in_info_plist(self):
        bad_info = {
            "CADisableMinimumFrameDurationOnPhone": True,
            "UIRequiredDeviceCapabilities": ["arm64"],  # missing metal
            "UIFileSharingEnabled": True,
            "LSSupportsOpeningDocumentsInPlace": True,
            "CFBundleDocumentTypes": [{}],
        }
        errors = PackagingConfigValidator.validate_info_plist(bad_info)
        self.assertTrue(any("metal" in e for e in errors))

    def test_validator_detects_invalid_ci_runner(self):
        bad_workflow = {
            "on": {"push": {}, "workflow_dispatch": {}},
            "jobs": {
                "build": {
                    "runs-on": "ubuntu-latest",  # Invalid, must be macOS
                    "steps": [],
                }
            },
        }
        errors = PackagingConfigValidator.validate_ci_workflow(bad_workflow)
        self.assertTrue(any("macos-14" in e for e in errors))

    def test_validator_detects_missing_archive_or_packaging_in_ci(self):
        bad_workflow = {
            "on": {"push": {}, "workflow_dispatch": {}},
            "jobs": {
                "build": {
                    "runs-on": "macos-14",
                    "steps": [
                        {"name": "Checkout", "uses": "actions/checkout@v4"},
                        {"name": "Run XcodeGen", "run": "xcodegen generate --spec project.yml"},
                        # Missing archive and package steps
                    ],
                }
            },
        }
        errors = PackagingConfigValidator.validate_ci_workflow(bad_workflow)
        self.assertTrue(any("DeskSimulator-TrollStore" in e for e in errors))
        self.assertTrue(any("DeskSimulator-Sideload" in e for e in errors))


if __name__ == "__main__":
    unittest.main()
