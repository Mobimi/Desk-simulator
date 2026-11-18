#!/usr/bin/env python3
"""
Unit tests validating the XcodeGen project definition (project.yml).
Ensures compliance with R3:
- Target DeskSimulator for iOS 15.0+, Swift 5.9+, arm64
- Bridging header Engine/DeskSimulator-Bridging-Header.h
- Info.plist Config/Info.plist
- Dual schemes & configurations: TrollStore & Sideload
- Frameworks: Metal, MetalKit, GameController, AudioToolbox
"""

import unittest
from pathlib import Path
import yaml

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent.parent


class TestXcodeGenConfig(unittest.TestCase):
    """Validates XcodeGen project.yml structure and semantics."""

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

    def test_build_configurations_declared(self):
        configs = self.spec.get("configs", {})
        self.assertIn("Debug-TrollStore", configs)
        self.assertIn("Release-TrollStore", configs)
        self.assertIn("Debug-Sideload", configs)
        self.assertIn("Release-Sideload", configs)
        self.assertEqual(configs["Debug-TrollStore"], "debug")
        self.assertEqual(configs["Release-TrollStore"], "release")
        self.assertEqual(configs["Debug-Sideload"], "debug")
        self.assertEqual(configs["Release-Sideload"], "release")

    def test_target_desk_simulator_exists(self):
        targets = self.spec.get("targets", {})
        self.assertIn("DeskSimulator", targets)
        target = targets["DeskSimulator"]
        self.assertEqual(target.get("type"), "application")
        self.assertEqual(target.get("platform"), "iOS")
        self.assertEqual(target.get("deploymentTarget"), "15.0")

    def test_target_sources(self):
        target = self.spec["targets"]["DeskSimulator"]
        sources = target.get("sources", [])
        paths = [s.get("path") if isinstance(s, dict) else s for s in sources]
        self.assertIn("Engine", paths)
        self.assertIn("Management", paths)
        self.assertIn("UI", paths)
        self.assertIn("Config", paths)

    def test_target_base_settings(self):
        target = self.spec["targets"]["DeskSimulator"]
        settings = target.get("settings", {})
        base = settings.get("base", {})
        self.assertEqual(base.get("PRODUCT_NAME"), "DeskSimulator")
        self.assertEqual(base.get("PRODUCT_BUNDLE_IDENTIFIER"), "com.mobimi.DeskSimulator")
        self.assertEqual(base.get("INFOPLIST_FILE"), "Config/Info.plist")
        self.assertEqual(base.get("SWIFT_OBJC_BRIDGING_HEADER"), "Engine/DeskSimulator-Bridging-Header.h")
        self.assertEqual(base.get("SWIFT_VERSION"), "5.9")
        self.assertEqual(base.get("ARCHS"), "arm64")
        self.assertEqual(base.get("IPHONEOS_DEPLOYMENT_TARGET"), "15.0")

        # Header search paths for bridging header inclusion
        header_paths = base.get("HEADER_SEARCH_PATHS", [])
        self.assertIn("$(SRCROOT)/Engine", header_paths)
        self.assertIn("$(SRCROOT)/Engine/QEMU", header_paths)

    def test_entitlements_by_configuration(self):
        target = self.spec["targets"]["DeskSimulator"]
        configs = target.get("settings", {}).get("configs", {})

        # TrollStore configurations must link DeskSimulator-TrollStore.entitlements
        self.assertEqual(
            configs.get("Release-TrollStore", {}).get("CODE_SIGN_ENTITLEMENTS"),
            "Config/DeskSimulator-TrollStore.entitlements"
        )
        self.assertEqual(
            configs.get("Debug-TrollStore", {}).get("CODE_SIGN_ENTITLEMENTS"),
            "Config/DeskSimulator-TrollStore.entitlements"
        )

        # Sideload configurations must link DeskSimulator-Sideload.entitlements
        self.assertEqual(
            configs.get("Release-Sideload", {}).get("CODE_SIGN_ENTITLEMENTS"),
            "Config/DeskSimulator-Sideload.entitlements"
        )
        self.assertEqual(
            configs.get("Debug-Sideload", {}).get("CODE_SIGN_ENTITLEMENTS"),
            "Config/DeskSimulator-Sideload.entitlements"
        )

    def test_required_framework_dependencies(self):
        target = self.spec["targets"]["DeskSimulator"]
        deps = target.get("dependencies", [])
        framework_sdks = [d.get("sdk") for d in deps if isinstance(d, dict) and "sdk" in d]
        expected_frameworks = [
            "Metal.framework",
            "MetalKit.framework",
            "GameController.framework",
            "AudioToolbox.framework",
        ]
        for fw in expected_frameworks:
            self.assertIn(fw, framework_sdks, f"Missing required system framework dependency: {fw}")

    def test_schemes_declared(self):
        schemes = self.spec.get("schemes", {})
        self.assertIn("DeskSimulator-TrollStore", schemes)
        self.assertIn("DeskSimulator-Sideload", schemes)

        ts_scheme = schemes["DeskSimulator-TrollStore"]
        self.assertEqual(ts_scheme.get("archive", {}).get("config"), "Release-TrollStore")

        sl_scheme = schemes["DeskSimulator-Sideload"]
        self.assertEqual(sl_scheme.get("archive", {}).get("config"), "Release-Sideload")


if __name__ == "__main__":
    unittest.main()
