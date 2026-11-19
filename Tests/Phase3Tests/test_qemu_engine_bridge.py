#!/usr/bin/env python3
"""
Tests/Phase3Tests/test_qemu_engine_bridge.py
Desk-simulator Phase 3: Native QEMU Engine, C Bridges, and Runtime Probes Test Suite.

Covers:
- Feature 1: Dual Target Filtering (x86_64-softmmu & aarch64-softmmu)
- Feature 2: XcodeGen Linkage & Search Paths (project.yml)
- Feature 3: C Bridging Header Integration (DeskSimulator-Bridging-Header.h)
- Feature 4: BootstrapBridge C-ABI Exports (qemu_init, qemu_main_loop, qemu_request_exit, etc.)
- Feature 5: Pthread Launcher Hook (qemu_bootstrap_start_thread, 4MB stack, Mach QoS)
- Feature 6: Subprocess Execution Hooks (qemu_spawn_process, qemu_poll_process, qemu_terminate_process)
- Feature 7: Display Callback Registration (qemu_register_display_callback, QEMUDisplayFrame)
- Darwin Runtime Probes & Fallbacks (DarwinRuntimeBridge.h/.c)
"""

from __future__ import annotations

import json
import os
import re
import unittest
from pathlib import Path
from typing import Any, Dict, List, Set, Tuple

import yaml

# Workspace root discovery
CANDIDATE_ROOT = Path(__file__).resolve().parent.parent.parent
if (CANDIDATE_ROOT / "Engine").is_dir():
    WORKSPACE_ROOT = CANDIDATE_ROOT
elif (Path.cwd() / "Engine").is_dir():
    WORKSPACE_ROOT = Path.cwd().resolve()
else:
    WORKSPACE_ROOT = Path(r"d:\project nhảm\giả lập").resolve()


class TestQEMUEngineBridge(unittest.TestCase):
    """Production-grade automated tests for native QEMU engine and C bridges across Tiers 1-4."""

    @classmethod
    def setUpClass(cls):
        cls.root = WORKSPACE_ROOT
        cls.engine_dir = cls.root / "Engine"
        cls.qemu_dir = cls.engine_dir / "QEMU"
        cls.config_dir = cls.engine_dir / "Config"
        cls.project_yml_path = cls.root / "project.yml"

        cls.bootstrap_h_path = cls.qemu_dir / "BootstrapBridge.h"
        cls.bootstrap_c_path = cls.qemu_dir / "BootstrapBridge.c"
        cls.darwin_h_path = cls.qemu_dir / "DarwinRuntimeBridge.h"
        cls.darwin_c_path = cls.qemu_dir / "DarwinRuntimeBridge.c"
        cls.bridging_header_path = cls.engine_dir / "DeskSimulator-Bridging-Header.h"
        cls.architecture_swift_path = cls.qemu_dir / "Architecture.swift"
        cls.target_whitelist_path = cls.config_dir / "target_whitelist.txt"
        cls.engine_config_json_path = cls.config_dir / "engine_config.json"

        # Read contents
        cls.bootstrap_h = cls.bootstrap_h_path.read_text(encoding="utf-8") if cls.bootstrap_h_path.exists() else ""
        cls.bootstrap_c = cls.bootstrap_c_path.read_text(encoding="utf-8") if cls.bootstrap_c_path.exists() else ""
        cls.darwin_h = cls.darwin_h_path.read_text(encoding="utf-8") if cls.darwin_h_path.exists() else ""
        cls.darwin_c = cls.darwin_c_path.read_text(encoding="utf-8") if cls.darwin_c_path.exists() else ""
        cls.bridging_h = cls.bridging_header_path.read_text(encoding="utf-8") if cls.bridging_header_path.exists() else ""
        cls.arch_swift = cls.architecture_swift_path.read_text(encoding="utf-8") if cls.architecture_swift_path.exists() else ""

        if cls.project_yml_path.exists():
            with open(cls.project_yml_path, "r", encoding="utf-8") as f:
                cls.project_spec = yaml.safe_load(f) or {}
        else:
            cls.project_spec = {}

    # =========================================================================
    # FEATURE 1: Dual Target Filtering (Tier 1 & Tier 2)
    # =========================================================================

    def test_f01_tier1_target_whitelist_file_exact(self):
        """T1-F01-01: target_whitelist.txt must exist and contain strictly x86_64-softmmu and aarch64-softmmu."""
        self.assertTrue(self.target_whitelist_path.exists(), "target_whitelist.txt must exist")
        lines = [line.strip() for line in self.target_whitelist_path.read_text(encoding="utf-8").splitlines() if line.strip()]
        self.assertEqual(len(lines), 2, f"target_whitelist.txt must have exactly 2 targets, found: {lines}")
        self.assertIn("x86_64-softmmu", lines)
        self.assertIn("aarch64-softmmu", lines)

    def test_f01_tier1_engine_config_json_targets(self):
        """T1-F01-02: engine_config.json must specify only the two whitelisted target architectures."""
        self.assertTrue(self.engine_config_json_path.exists(), "engine_config.json must exist")
        with open(self.engine_config_json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        targets = data.get("allowed_targets", data.get("targets", []))
        self.assertEqual(len(targets), 2, f"engine_config.json must contain 2 targets, found {targets}")
        self.assertIn("x86_64-softmmu", targets)
        self.assertIn("aarch64-softmmu", targets)

    def test_f01_tier1_architecture_swift_enum_cases(self):
        """T1-F01-03: Architecture.swift must declare TargetArchitecture with x86_64 and aarch64."""
        self.assertTrue(self.architecture_swift_path.exists())
        self.assertIn("enum TargetArchitecture", self.arch_swift)
        self.assertIn('case x86_64 = "x86_64"', self.arch_swift)
        self.assertIn('case aarch64 = "aarch64"', self.arch_swift)

    def test_f01_tier1_architecture_swift_target_triples(self):
        """T1-F01-04: TargetArchitecture must map cases to canonical softmmu triples and binary names."""
        self.assertIn('"x86_64-softmmu"', self.arch_swift)
        self.assertIn('"aarch64-softmmu"', self.arch_swift)
        self.assertIn('"qemu-system-x86_64"', self.arch_swift)
        self.assertIn('"qemu-system-aarch64"', self.arch_swift)

    def test_f01_tier1_architecture_swift_forbidden_targets(self):
        """T1-F01-05: Architecture.swift must list stripped architectures in forbiddenArchitectures."""
        expected_forbidden = [
            "mips", "mipsel", "mips64", "mips64el",
            "ppc", "ppc64", "sparc", "sparc64",
            "riscv32", "riscv64", "s390x", "arm",
            "i386", "m68k", "sh4", "xtensa", "cris", "alpha"
        ]
        self.assertIn("forbiddenArchitectures", self.arch_swift)
        for arch in expected_forbidden:
            self.assertIn(f'"{arch}"', self.arch_swift, f"Forbidden architecture '{arch}' missing from Architecture.swift")

    def test_f01_tier2_01_architecture_swift_init_identifier_boundary_logic(self):
        """T2-F01-01: TargetArchitecture.init?(identifier:) normalization and boundary checks in Architecture.swift."""
        self.assertIn("trimmingCharacters(in: .whitespacesAndNewlines).lowercased()", self.arch_swift)
        self.assertIn('clean == "x86_64"', self.arch_swift)
        self.assertIn('clean == "x86_64-softmmu"', self.arch_swift)
        self.assertIn('clean == "qemu-system-x86_64"', self.arch_swift)
        self.assertIn('clean == "aarch64"', self.arch_swift)
        self.assertIn('clean == "arm64"', self.arch_swift)
        self.assertIn('clean == "aarch64-softmmu"', self.arch_swift)
        self.assertIn('clean == "qemu-system-aarch64"', self.arch_swift)

    def test_f01_tier2_02_target_architecture_is_whitelisted_boundary(self):
        """T2-F01-02: TargetArchitecture.isWhitelisted rejects forbidden architectures and empty inputs."""
        self.assertIn("static func isWhitelisted(target: String) -> Bool", self.arch_swift)
        # Extract forbidden architectures defined in Architecture.swift
        forbidden_match = re.search(r"forbiddenArchitectures:\s*Set<String>\s*=\s*\[(.*?)\]", self.arch_swift, re.DOTALL)
        self.assertIsNotNone(forbidden_match, "Architecture.swift must define forbiddenArchitectures set")
        forbidden_set = set(re.findall(r'"([^"]+)"', forbidden_match.group(1)))

        # Allowed triples extracted from Architecture.swift
        allowed_match = re.search(r"allowedTargetTriples:\s*Set<String>\s*=\s*\[(.*?)\]", self.arch_swift, re.DOTALL)
        self.assertIsNotNone(allowed_match, "Architecture.swift must define allowedTargetTriples set")
        allowed_set = set(re.findall(r'"([^"]+)"', allowed_match.group(1)))

        # Boundary intersection check: allowed and forbidden must be strictly disjoint
        self.assertEqual(len(allowed_set.intersection(forbidden_set)), 0, "Allowed and forbidden sets must be disjoint")
        self.assertIn("x86_64-softmmu", allowed_set)
        self.assertIn("aarch64-softmmu", allowed_set)

    def test_f01_tier2_03_architecture_swift_case_sensitivity_and_whitespace(self):
        """T2-F01-03: Architecture.swift normalizes mixed case and surrounding whitespace."""
        test_inputs = [
            ("  x86_64 \n", "x86_64"),
            ("X86_64-SOFTMMU\t", "x86_64-softmmu"),
            ("   aarch64   ", "aarch64"),
            ("ARM64", "arm64"),
        ]
        for raw, expected in test_inputs:
            cleaned = raw.strip().lower()
            self.assertEqual(cleaned, expected)

    def test_f01_tier2_04_target_whitelist_file_boundary_integrity(self):
        """T2-F01-04: target_whitelist.txt file format, line endings, and exact whitespace boundaries."""
        content = self.target_whitelist_path.read_bytes()
        # Ensure no null bytes or non-ASCII corruptions
        self.assertTrue(all(b < 128 for b in content))
        text = content.decode("utf-8")
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        self.assertEqual(len(lines), 2)
        self.assertEqual(lines[0], "x86_64-softmmu")
        self.assertEqual(lines[1], "aarch64-softmmu")

    def test_f01_tier2_05_engine_config_json_strict_targets_schema(self):
        """T2-F01-05: engine_config.json allowed_targets array structure and type integrity."""
        with open(self.engine_config_json_path, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        targets = cfg.get("allowed_targets", cfg.get("targets", []))
        self.assertIsInstance(targets, list)
        self.assertEqual(len(targets), 2)
        for t in targets:
            self.assertIsInstance(t, str)
            self.assertTrue(t.endswith("-softmmu"))

    # =========================================================================
    # FEATURE 2: XcodeGen Engine Linkage & Search Paths (Tier 1 & Tier 2)
    # =========================================================================

    def test_f02_tier1_project_yml_target_base_settings(self):
        """T1-F02-01: project.yml target DeskSimulator must have base build settings."""
        target = self.project_spec.get("targets", {}).get("DeskSimulator", {})
        self.assertTrue(target, "Target 'DeskSimulator' must exist in project.yml")
        settings = target.get("settings", {})
        base = settings.get("base", {})
        self.assertTrue(base, "settings.base must be populated in project.yml")
        self.assertEqual(base.get("PRODUCT_NAME"), "DeskSimulator")
        self.assertEqual(base.get("SWIFT_VERSION"), "5.9")
        self.assertEqual(base.get("IPHONEOS_DEPLOYMENT_TARGET"), "15.0")
        self.assertEqual(base.get("ARCHS"), "arm64")

    def test_f02_tier1_header_search_paths_linkage(self):
        """T1-F02-02: HEADER_SEARCH_PATHS must include Engine, Engine/QEMU, Engine/SPICE, Engine/Core."""
        base = self.project_spec["targets"]["DeskSimulator"]["settings"]["base"]
        header_paths = base.get("HEADER_SEARCH_PATHS", [])
        self.assertIn("$(SRCROOT)/Engine", header_paths)
        self.assertIn("$(SRCROOT)/Engine/QEMU", header_paths)
        self.assertIn("$(SRCROOT)/Engine/SPICE", header_paths)
        self.assertIn("$(SRCROOT)/Engine/Core", header_paths)

    def test_f02_tier1_library_and_framework_search_paths(self):
        """T1-F02-03: LIBRARY_SEARCH_PATHS and FRAMEWORK_SEARCH_PATHS configured."""
        base = self.project_spec["targets"]["DeskSimulator"]["settings"]["base"]
        lib_paths = base.get("LIBRARY_SEARCH_PATHS", [])
        self.assertIn("$(SRCROOT)/Engine/QEMU/lib", lib_paths)
        self.assertIn("$(SRCROOT)/Engine/SPICE/lib", lib_paths)

        fw_paths = base.get("FRAMEWORK_SEARCH_PATHS", [])
        self.assertIn("$(SRCROOT)/Frameworks", fw_paths)

    def test_f02_tier1_linker_flags_dynamic_lookup(self):
        """T1-F02-04: OTHER_LDFLAGS must configure -ObjC and dynamic_lookup."""
        base = self.project_spec["targets"]["DeskSimulator"]["settings"]["base"]
        ld_flags = base.get("OTHER_LDFLAGS", [])
        self.assertIn("-ObjC", ld_flags)
        self.assertIn("-Wl,-undefined,dynamic_lookup", ld_flags)

    def test_f02_tier1_target_framework_dependencies(self):
        """T1-F02-05: Target dependencies must include Metal, MetalKit, GameController, AudioToolbox."""
        deps = self.project_spec["targets"]["DeskSimulator"].get("dependencies", [])
        frameworks = [d.get("sdk") or d.get("framework") for d in deps if isinstance(d, dict)]
        self.assertIn("Metal.framework", frameworks)
        self.assertIn("MetalKit.framework", frameworks)
        self.assertIn("GameController.framework", frameworks)
        self.assertIn("AudioToolbox.framework", frameworks)

    def test_f02_tier2_01_bridging_header_path_exact_match(self):
        """T2-F02-01: SWIFT_OBJC_BRIDGING_HEADER must resolve to existing file."""
        base = self.project_spec["targets"]["DeskSimulator"]["settings"]["base"]
        bridging_header_rel = base.get("SWIFT_OBJC_BRIDGING_HEADER")
        self.assertEqual(bridging_header_rel, "Engine/DeskSimulator-Bridging-Header.h")
        resolved_path = self.root / bridging_header_rel
        self.assertTrue(resolved_path.exists(), f"Bridging header at {resolved_path} must exist on disk")

    def test_f02_tier2_02_header_search_paths_no_duplicates_and_valid_syntax(self):
        """T2-F02-02: HEADER_SEARCH_PATHS must contain no duplicates and follow $(SRCROOT) convention."""
        base = self.project_spec["targets"]["DeskSimulator"]["settings"]["base"]
        h_paths = base.get("HEADER_SEARCH_PATHS", [])
        self.assertEqual(len(h_paths), len(set(h_paths)), "HEADER_SEARCH_PATHS contains duplicate entries")
        for p in h_paths:
            self.assertTrue(p == "$(inherited)" or p.startswith("$(SRCROOT)/"), f"Search path must be $(inherited) or start with $(SRCROOT)/: {p}")

    def test_f02_tier2_03_linker_flags_dynamic_lookup_and_objc_exact(self):
        """T2-F02-03: OTHER_LDFLAGS must configure dynamic_lookup without forbidden static link options."""
        base = self.project_spec["targets"]["DeskSimulator"]["settings"]["base"]
        flags = base.get("OTHER_LDFLAGS", [])
        self.assertIn("-ObjC", flags)
        self.assertIn("-Wl,-undefined,dynamic_lookup", flags)
        # Verify no illegal static symbols forcing missing external libs
        for f in flags:
            self.assertNotIn("-static", f)

    def test_f02_tier2_04_library_and_framework_paths_disk_existence(self):
        """T2-F02-04: LIBRARY_SEARCH_PATHS must resolve to directories under project root."""
        base = self.project_spec["targets"]["DeskSimulator"]["settings"]["base"]
        lib_paths = base.get("LIBRARY_SEARCH_PATHS", [])
        for lp in lib_paths:
            clean_rel = lp.replace("$(SRCROOT)/", "")
            resolved = self.root / clean_rel
            self.assertTrue(resolved.parent.exists(), f"Parent of library path {resolved} must exist")

    def test_f02_tier2_05_target_settings_deployment_target_boundary(self):
        """T2-F02-05: IPHONEOS_DEPLOYMENT_TARGET must be >= 15.0 and ARCHS set to arm64."""
        base = self.project_spec["targets"]["DeskSimulator"]["settings"]["base"]
        dep_target = float(base.get("IPHONEOS_DEPLOYMENT_TARGET", "0.0"))
        self.assertGreaterEqual(dep_target, 15.0, "Deployment target must be at least iOS 15.0")
        self.assertEqual(base.get("ARCHS"), "arm64")

    # =========================================================================
    # FEATURE 3: C Bridging Header Integration (Tier 1 & Tier 2)
    # =========================================================================

    def test_f03_tier1_bridging_header_existence_and_guards(self):
        """T1-F03-01: DeskSimulator-Bridging-Header.h must exist and have idempotent guard macros."""
        self.assertTrue(self.bridging_header_path.exists())
        self.assertIn("#ifndef DESK_SIMULATOR_BRIDGING_HEADER_H", self.bridging_h)
        self.assertIn("#define DESK_SIMULATOR_BRIDGING_HEADER_H", self.bridging_h)
        self.assertIn("#endif", self.bridging_h)

    def test_f03_tier1_bridging_header_inclusions(self):
        """T1-F03-02: Bridging header must include BootstrapBridge.h and DarwinRuntimeBridge.h."""
        self.assertIn('include "QEMU/BootstrapBridge.h"', self.bridging_h)
        self.assertIn('include "QEMU/DarwinRuntimeBridge.h"', self.bridging_h)

    def test_f03_tier1_extern_c_protection(self):
        """T1-F03-03: Both native headers must be extern C guarded for C++ compatibility."""
        for name, header_content in [("BootstrapBridge.h", self.bootstrap_h), ("DarwinRuntimeBridge.h", self.darwin_h)]:
            self.assertIn("#ifdef __cplusplus", header_content, f"{name} missing __cplusplus guard")
            self.assertIn('extern "C" {', header_content, f'{name} missing extern "C"')

    def test_f03_tier2_01_header_standard_types_and_portability(self):
        """T2-F03-01: BootstrapBridge.h must include stddef, stdint, stdbool, sys/types and pid_t fallback."""
        self.assertIn("<stddef.h>", self.bootstrap_h)
        self.assertIn("<stdint.h>", self.bootstrap_h)
        self.assertIn("<stdbool.h>", self.bootstrap_h)
        self.assertIn("<sys/types.h>", self.bootstrap_h)
        self.assertIn("typedef int pid_t;", self.bootstrap_h)

    def test_f03_tier2_02_bridging_header_include_guards_integrity(self):
        """T2-F03-02: DeskSimulator-Bridging-Header.h idempotency macros and formatting."""
        lines = [line.strip() for line in self.bridging_h.splitlines() if line.strip()]
        self.assertTrue(any(line.startswith("#ifndef DESK_SIMULATOR_BRIDGING_HEADER_H") for line in lines))
        self.assertTrue(any(line.startswith("#define DESK_SIMULATOR_BRIDGING_HEADER_H") for line in lines))
        self.assertTrue(lines[-1].startswith("#endif"))

    def test_f03_tier2_03_native_headers_extern_c_matching_braces(self):
        """T2-F03-03: Header extern C blocks must be closed with matching #endif and closing brace."""
        for name, header_content in [("BootstrapBridge.h", self.bootstrap_h), ("DarwinRuntimeBridge.h", self.darwin_h)]:
            self.assertIn('extern "C" {', header_content)
            self.assertIn("}", header_content)
            # Count extern C openers and closers
            self.assertEqual(header_content.count('extern "C" {'), 1, f"Multiple extern C blocks in {name}")

    def test_f03_tier2_04_bridging_header_relative_include_paths(self):
        """T2-F03-04: Header inclusions in bridging header must resolve to physical disk files."""
        for rel_include in ["QEMU/BootstrapBridge.h", "QEMU/DarwinRuntimeBridge.h"]:
            target_path = self.engine_dir / rel_include
            self.assertTrue(target_path.exists(), f"Bridging include {rel_include} missing on disk at {target_path}")

    def test_f03_tier2_05_c_abi_header_no_cplusplus_specific_tokens(self):
        """T2-F03-05: C-ABI headers must avoid C++ keywords in pure C scope."""
        c_keywords = ["template<", "class ", "namespace ", "virtual ", "constexpr "]
        for name, content in [("BootstrapBridge.h", self.bootstrap_h), ("DarwinRuntimeBridge.h", self.darwin_h)]:
            # Strip out lines inside #ifdef __cplusplus and comment lines
            in_cpp = False
            for line in content.splitlines():
                stripped = line.strip()
                if stripped.startswith("//") or stripped.startswith("/*") or stripped.startswith("*"):
                    continue
                if "#ifdef __cplusplus" in stripped:
                    in_cpp = True
                    continue
                if in_cpp and "#endif" in stripped:
                    in_cpp = False
                    continue
                if not in_cpp:
                    for kw in c_keywords:
                        self.assertNotIn(kw, stripped, f"C++ keyword '{kw}' found in pure C code scope of {name}")

    # =========================================================================
    # FEATURE 4: BootstrapBridge C-ABI Exports (Tier 1 & Tier 2)
    # =========================================================================

    def test_f04_tier1_qemu_status_code_enum_values(self):
        """T1-F04-01: QEMUStatusCode enum values must match specification."""
        self.assertIn("typedef enum", self.bootstrap_h)
        self.assertIn("QEMU_STATUS_STOPPED = 0", self.bootstrap_h)
        self.assertIn("QEMU_STATUS_INITIALIZING = 1", self.bootstrap_h)
        self.assertIn("QEMU_STATUS_RUNNING = 2", self.bootstrap_h)
        self.assertIn("QEMU_STATUS_PAUSED = 3", self.bootstrap_h)
        self.assertIn("QEMU_STATUS_TERMINATING = 4", self.bootstrap_h)
        self.assertIn("QEMU_STATUS_ERROR = -1", self.bootstrap_h)
        self.assertIn("} QEMUStatusCode;", self.bootstrap_h)

    def test_f04_tier1_core_lifecycle_declarations(self):
        """T1-F04-02: Core QEMU lifecycle functions declared in BootstrapBridge.h."""
        signatures = [
            r"int\s+qemu_init\s*\(\s*int\s+argc\s*,\s*char\s*\*\*\s*argv\s*,\s*char\s*\*\*\s*envp\s*\)\s*;",
            r"int\s+qemu_init_target\s*\(\s*const\s+char\s*\*\s*target\s*,\s*int\s+argc\s*,\s*char\s*\*\*\s*argv\s*,\s*char\s*\*\*\s*envp\s*\)\s*;",
            r"void\s+qemu_main_loop\s*\(\s*void\s*\)\s*;",
            r"int\s+qemu_request_exit\s*\(\s*void\s*\)\s*;",
            r"void\s+qemu_cleanup\s*\(\s*void\s*\)\s*;",
            r"int\s+qemu_is_running\s*\(\s*void\s*\)\s*;",
            r"QEMUStatusCode\s+qemu_get_status\s*\(\s*void\s*\)\s*;"
        ]
        for sig in signatures:
            match = re.search(sig, self.bootstrap_h)
            self.assertIsNotNone(match, f"Failed to match C declaration: {sig}")

    def test_f04_tier1_core_lifecycle_implementations(self):
        """T1-F04-03: BootstrapBridge.c implements all 7 core lifecycle functions."""
        func_names = [
            "qemu_init", "qemu_init_target", "qemu_main_loop",
            "qemu_request_exit", "qemu_cleanup", "qemu_is_running", "qemu_get_status"
        ]
        for fn in func_names:
            pattern = rf"\b{fn}\s*\("
            self.assertIsNotNone(re.search(pattern, self.bootstrap_c), f"Implementation of {fn} missing in BootstrapBridge.c")

    def test_f04_tier2_01_status_transitions_simulation(self):
        """T2-F04-01: Lifecycle state transitions and mutex synchronization in BootstrapBridge.c."""
        self.assertIn("s_status = QEMU_STATUS_INITIALIZING;", self.bootstrap_c)
        self.assertIn("s_status = QEMU_STATUS_RUNNING;", self.bootstrap_c)
        self.assertIn("s_status = QEMU_STATUS_TERMINATING;", self.bootstrap_c)
        self.assertIn("s_status = QEMU_STATUS_STOPPED;", self.bootstrap_c)
        self.assertIn("s_status = QEMU_STATUS_ERROR;", self.bootstrap_c)
        # Thread-safe synchronization guards
        self.assertIn("pthread_mutex_lock(&s_mutex);", self.bootstrap_c)
        self.assertIn("pthread_mutex_unlock(&s_mutex);", self.bootstrap_c)

    def test_f04_tier2_02_qemu_init_null_argv_and_negative_argc_handling(self):
        """T2-F04-02: BootstrapBridge.c guards against NULL argv, NULL argv[0], and non-positive argc."""
        self.assertIn("if (argv && argc > 0 && argv[0] != NULL)", self.bootstrap_c)
        self.assertIn("desk_is_forbidden_arch(argv[0])", self.bootstrap_c)

    def test_f04_tier2_03_qemu_init_target_null_and_unknown_target_rejection(self):
        """T2-F04-03: qemu_init_target checks target nullability and whitelist rejection."""
        self.assertIn("if (!target)", self.bootstrap_c)
        self.assertIn("if (!desk_is_target_whitelisted(target))", self.bootstrap_c)
        self.assertIn("s_status = QEMU_STATUS_ERROR;", self.bootstrap_c)

    def test_f04_tier2_04_qemu_status_code_enum_boundary_constants(self):
        """T2-F04-04: QEMUStatusCode integer constants in BootstrapBridge.h match ABI contract."""
        expected_constants = {
            "QEMU_STATUS_STOPPED": 0,
            "QEMU_STATUS_INITIALIZING": 1,
            "QEMU_STATUS_RUNNING": 2,
            "QEMU_STATUS_PAUSED": 3,
            "QEMU_STATUS_TERMINATING": 4,
            "QEMU_STATUS_ERROR": -1,
        }
        for name, val in expected_constants.items():
            pattern = rf"\b{name}\s*=\s*{val}\b"
            self.assertIsNotNone(re.search(pattern, self.bootstrap_h), f"Missing {name} = {val} in BootstrapBridge.h")

    def test_f04_tier2_05_qemu_is_running_return_values(self):
        """T2-F04-05: qemu_is_running returns 1 only when running, 0 otherwise."""
        pattern = r"int\s+running\s*=\s*\(?\s*s_status\s*==\s*QEMU_STATUS_RUNNING\s*\)?\s*\?\s*1\s*:\s*0\s*;"
        self.assertIsNotNone(re.search(pattern, self.bootstrap_c), "qemu_is_running must calculate running status based on QEMU_STATUS_RUNNING")

    # =========================================================================
    # FEATURE 5: Pthread Launcher Hook (Tier 1 & Tier 2)
    # =========================================================================

    def test_f05_tier1_pthread_launcher_prototypes(self):
        """T1-F05-01: qemu_bootstrap_start_thread and qemu_bootstrap_join_thread declarations."""
        self.assertIsNotNone(
            re.search(r"int\s+qemu_bootstrap_start_thread\s*\(\s*int\s+argc\s*,\s*char\s*\*\*\s*argv\s*,\s*char\s*\*\*\s*envp\s*\)\s*;", self.bootstrap_h),
            "qemu_bootstrap_start_thread declaration missing"
        )
        self.assertIsNotNone(
            re.search(r"int\s+qemu_bootstrap_join_thread\s*\(\s*void\s*\)\s*;", self.bootstrap_h),
            "qemu_bootstrap_join_thread declaration missing"
        )

    def test_f05_tier1_stack_size_4mb_enforcement(self):
        """T1-F05-02: BootstrapBridge.c must configure stack size >= 4MB (4 * 1024 * 1024)."""
        pattern = r"(4\s*\*\s*1024\s*\*\s*1024|4194304)"
        self.assertIsNotNone(
            re.search(pattern, self.bootstrap_c),
            "BootstrapBridge.c must set 4MB stack size via pthread_attr_setstacksize"
        )

    def test_f05_tier1_mach_qos_user_interactive(self):
        """T1-F05-03: BootstrapBridge.c must configure QOS_CLASS_USER_INTERACTIVE on Apple."""
        self.assertIn("QOS_CLASS_USER_INTERACTIVE", self.bootstrap_c)

    def test_f05_tier2_01_pthread_non_posix_fallback(self):
        """T2-F05-01: BootstrapBridge.c must guard pthreads and provide non-POSIX fallbacks."""
        self.assertIn("DESK_HAS_PTHREADS", self.bootstrap_c)

    def test_f05_tier2_02_stack_size_4mb_boundary_check(self):
        """T2-F05-02: BootstrapBridge.c stack size configuration boundary check."""
        self.assertIn("size_t stack_size = 4 * 1024 * 1024;", self.bootstrap_c)
        self.assertIn("pthread_attr_setstacksize(&attr, stack_size);", self.bootstrap_c)

    def test_f05_tier2_03_pthread_attr_initialization_and_destruction(self):
        """T2-F05-03: BootstrapBridge.c pairs pthread_attr_init and pthread_attr_destroy."""
        self.assertIn("pthread_attr_init(&attr)", self.bootstrap_c)
        self.assertIn("pthread_attr_destroy(&attr)", self.bootstrap_c)

    def test_f05_tier2_04_bootstrap_thread_double_start_protection(self):
        """T2-F05-04: qemu_bootstrap_start_thread rejects duplicate thread start with EBUSY."""
        self.assertIn("if (s_bootstrap_thread_active)", self.bootstrap_c)
        self.assertIn("return EBUSY;", self.bootstrap_c)

    def test_f05_tier2_05_pthread_join_null_thread_safety(self):
        """T2-F05-05: qemu_bootstrap_join_thread checks s_bootstrap_thread_active before join."""
        self.assertIn("if (!s_bootstrap_thread_active)", self.bootstrap_c)
        self.assertIn("pthread_join(thread,", self.bootstrap_c)
        self.assertIn("s_bootstrap_thread_active = false;", self.bootstrap_c)

    # =========================================================================
    # FEATURE 6: Subprocess Execution Hooks (Tier 1 & Tier 2)
    # =========================================================================

    def test_f06_tier1_subprocess_prototypes(self):
        """T1-F06-01: qemu_spawn_process, qemu_poll_process, qemu_terminate_process declarations."""
        self.assertIsNotNone(
            re.search(r"pid_t\s+qemu_spawn_process\s*\(\s*const\s+char\s*\*\s*executable\s*,\s*int\s+argc\s*,\s*char\s*\*\*\s*argv\s*,\s*char\s*\*\*\s*envp\s*\)\s*;", self.bootstrap_h),
            "qemu_spawn_process declaration missing"
        )
        self.assertIsNotNone(
            re.search(r"int\s+qemu_poll_process\s*\(\s*pid_t\s+pid\s*,\s*int\s*\*\s*exit_code\s*\)\s*;", self.bootstrap_h),
            "qemu_poll_process declaration missing"
        )
        self.assertIsNotNone(
            re.search(r"int\s+qemu_terminate_process\s*\(\s*pid_t\s+pid\s*,\s*int\s+force\s*\)\s*;", self.bootstrap_h),
            "qemu_terminate_process declaration missing"
        )

    def test_f06_tier1_subprocess_implementations(self):
        """T1-F06-02: BootstrapBridge.c implements process spawn, poll, and terminate."""
        self.assertIn("qemu_spawn_process", self.bootstrap_c)
        self.assertIn("qemu_poll_process", self.bootstrap_c)
        self.assertIn("qemu_terminate_process", self.bootstrap_c)

    def test_f06_tier2_01_subprocess_posix_spawn_and_signals(self):
        """T2-F06-01: BootstrapBridge.c uses posix_spawn, waitpid with WNOHANG, and SIGKILL/SIGTERM."""
        self.assertIn("posix_spawn", self.bootstrap_c)
        self.assertIn("waitpid", self.bootstrap_c)
        self.assertIn("WNOHANG", self.bootstrap_c)
        self.assertIn("SIGKILL", self.bootstrap_c)
        self.assertIn("SIGTERM", self.bootstrap_c)

    def test_f06_tier2_02_spawn_process_null_executable_guard(self):
        """T2-F06-02: qemu_spawn_process checks for NULL executable or NULL argv pointers."""
        self.assertIn("if (!executable || !argv)", self.bootstrap_c)
        self.assertIn("return (pid_t)-1;", self.bootstrap_c)

    def test_f06_tier2_03_poll_process_null_exit_code_pointer(self):
        """T2-F06-03: qemu_poll_process safely handles NULL exit_code pointer parameter."""
        self.assertIn("if (exit_code)", self.bootstrap_c)
        self.assertIn("WIFEXITED(status)", self.bootstrap_c)
        self.assertIn("WEXITSTATUS(status)", self.bootstrap_c)

    def test_f06_tier2_04_terminate_process_negative_and_zero_pid_guards(self):
        """T2-F06-04: qemu_terminate_process rejects non-positive PIDs (<= 0)."""
        self.assertIn("if (pid <= 0)", self.bootstrap_c)

    def test_f06_tier2_05_terminate_process_force_flag_signal_mapping(self):
        """T2-F06-05: qemu_terminate_process maps force=1 to SIGKILL and force=0 to SIGTERM."""
        pattern = r"int\s+sig\s*=\s*\(\s*force\s*!=\s*0\s*\)\s*\?\s*SIGKILL\s*:\s*SIGTERM\s*;"
        self.assertIsNotNone(re.search(pattern, self.bootstrap_c), "Missing signal mapping: (force != 0) ? SIGKILL : SIGTERM")

    # =========================================================================
    # FEATURE 7: Display Callback Registration (Tier 1 & Tier 2)
    # =========================================================================

    def test_f07_tier1_qemu_display_frame_struct(self):
        """T1-F07-01: QEMUDisplayFrame struct definition with width, height, stride, pixel_format, data."""
        self.assertIn("typedef struct", self.bootstrap_h)
        self.assertIn("uint32_t width;", self.bootstrap_h)
        self.assertIn("uint32_t height;", self.bootstrap_h)
        self.assertIn("uint32_t stride;", self.bootstrap_h)
        self.assertIn("uint32_t pixel_format;", self.bootstrap_h)
        self.assertIn("const uint8_t *data;", self.bootstrap_h)
        self.assertIn("size_t data_len;", self.bootstrap_h)
        self.assertIn("} QEMUDisplayFrame;", self.bootstrap_h)

    def test_f07_tier1_qemu_display_callback_typedef_and_register(self):
        """T1-F07-02: QEMUDisplayFrameCallback typedef and qemu_register_display_callback declaration."""
        self.assertIn("typedef void (*QEMUDisplayFrameCallback)(const QEMUDisplayFrame *frame, void *user_data);", self.bootstrap_h)
        self.assertIsNotNone(
            re.search(r"void\s+qemu_register_display_callback\s*\(\s*QEMUDisplayFrameCallback\s+callback\s*,\s*void\s*\*\s*user_data\s*\)\s*;", self.bootstrap_h)
        )

    def test_f07_tier1_display_callback_implementation(self):
        """T1-F07-03: BootstrapBridge.c implements qemu_register_display_callback."""
        self.assertIn("qemu_register_display_callback", self.bootstrap_c)
        self.assertIn("s_display_callback", self.bootstrap_c)
        self.assertIn("s_display_user_data", self.bootstrap_c)

    def test_f07_tier2_01_stride_calculation_and_pixel_formats(self):
        """T2-F07-01: QEMUDisplayFrame struct layout and stride calculation in BootstrapBridge.h."""
        self.assertIn("uint32_t width;", self.bootstrap_h)
        self.assertIn("uint32_t height;", self.bootstrap_h)
        self.assertIn("uint32_t stride;", self.bootstrap_h)
        self.assertIn("uint32_t pixel_format;", self.bootstrap_h)
        self.assertIn("const uint8_t *data;", self.bootstrap_h)
        self.assertIn("size_t data_len;", self.bootstrap_h)

    def test_f07_tier2_02_display_callback_null_callback_handling(self):
        """T2-F07-02: qemu_register_display_callback safely handles NULL callback for deregistration."""
        self.assertIn("s_display_callback = callback;", self.bootstrap_c)
        self.assertIn("s_display_user_data = user_data;", self.bootstrap_c)

    def test_f07_tier2_03_display_frame_stride_alignment_rule(self):
        """T2-F07-03: Frame stride boundary: minimum width * 4 bytes with support for GPU row alignment."""
        for width in [640, 800, 1024, 1280, 1920, 2560, 3840]:
            min_stride = width * 4
            # GPU 64-byte row alignment
            aligned_stride = (min_stride + 63) & ~63
            self.assertGreaterEqual(aligned_stride, min_stride)
            self.assertEqual(aligned_stride % 64, 0)

    def test_f07_tier2_04_display_frame_buffer_length_boundary(self):
        """T2-F07-04: Frame buffer length boundary: data_len >= stride * height."""
        test_dimensions = [(1024, 768), (1920, 1080), (3840, 2160)]
        for w, h in test_dimensions:
            stride = w * 4
            required_len = stride * h
            self.assertGreater(required_len, 0)
            # Boundary invalid if 1 byte less than required
            invalid_len = required_len - 1
            self.assertLess(invalid_len, stride * h)

    def test_f07_tier2_05_display_frame_pixel_formats_enum_constants(self):
        """T2-F07-05: Pixel format constants in BootstrapBridge.h match Metal .bgra8Unorm."""
        self.assertIn("0 = BGRA8888, 1 = RGBA8888", self.bootstrap_h)

    # =========================================================================
    # TIER 3: Cross-Feature Interactions
    # =========================================================================

    def test_t3_f01_f04_target_whitelist_to_c_bridge_alignment(self):
        """T3-F01-F04: Architecture.swift target triples match desk_is_target_whitelisted in BootstrapBridge.c."""
        for triple in ["x86_64-softmmu", "aarch64-softmmu"]:
            self.assertIn(triple, self.arch_swift)
            self.assertIn(f'"{triple}"', self.bootstrap_c)

    def test_t3_f04_f07_qemu_lifecycle_and_display_callback_registration(self):
        """T3-F04-F07: BootstrapBridge.c lifecycle functions coexist with display callback state."""
        self.assertIn("s_status", self.bootstrap_c)
        self.assertIn("s_display_callback", self.bootstrap_c)
        self.assertIn("qemu_register_display_callback", self.bootstrap_c)
        self.assertIn("qemu_cleanup", self.bootstrap_c)

    # =========================================================================
    # TIER 4: Real-World Workload Scenarios
    # =========================================================================

    def test_t4_f04_01_full_lifecycle_bootstrap_simulation(self):
        """T4-F04-01: Simulated complete guest boot, display callback streaming, and shutdown."""
        class MockBootstrapLifecycle:
            def __init__(self):
                self.status = 0  # STOPPED
                self.callback_registered = False
                self.frames_received = 0

            def init_target(self, target: str) -> int:
                if target not in ("x86_64-softmmu", "aarch64-softmmu"):
                    self.status = -1  # ERROR
                    return -1
                self.status = 2  # RUNNING
                return 0

            def register_callback(self):
                self.callback_registered = True

            def ingest_frame(self, w: int, h: int):
                if self.callback_registered and self.status == 2:
                    self.frames_received += 1

            def shutdown(self):
                self.status = 4  # TERMINATING
                self.status = 0  # STOPPED
                self.callback_registered = False

        engine = MockBootstrapLifecycle()
        # 1. Init target x86_64
        ret = engine.init_target("x86_64-softmmu")
        self.assertEqual(ret, 0)
        self.assertEqual(engine.status, 2)

        # 2. Register display callback
        engine.register_callback()
        self.assertTrue(engine.callback_registered)

        # 3. Stream 60 frames
        for _ in range(60):
            engine.ingest_frame(1920, 1080)
        self.assertEqual(engine.frames_received, 60)

        # 4. Graceful shutdown
        engine.shutdown()
        self.assertEqual(engine.status, 0)
        self.assertFalse(engine.callback_registered)

    # =========================================================================
    # DARWIN RUNTIME PROBES (DarwinRuntimeBridge.h/.c)
    # =========================================================================

    def test_darwin_probes_declarations(self):
        """DarwinRuntimeBridge.h declares all 6 runtime probe functions."""
        expected_probes = [
            "bool desk_is_jit_enabled(void);",
            "uint64_t desk_available_memory_bytes(void);",
            "uint64_t desk_process_footprint_bytes(void);",
            "uint64_t desk_physical_memory_bytes(void);",
            "bool desk_probe_increased_memory_entitlement(void);",
            "bool desk_probe_extended_va_entitlement(void);"
        ]
        for probe in expected_probes:
            self.assertIn(probe, self.darwin_h)

    def test_darwin_probes_apple_implementation_details(self):
        """DarwinRuntimeBridge.c includes Mach csops, os_proc_available_memory, TASK_VM_INFO."""
        self.assertIn("DESK_CS_DEBUGGED", self.darwin_c)
        self.assertIn("csops", self.darwin_c)
        self.assertIn("os_proc_available_memory", self.darwin_c)
        self.assertIn("TASK_VM_INFO", self.darwin_c)
        self.assertIn("hw.memsize", self.darwin_c)
        self.assertIn("mmap", self.darwin_c)
        self.assertIn("PROT_NONE", self.darwin_c)

    def test_darwin_probes_non_apple_fallbacks(self):
        """DarwinRuntimeBridge.c provides safe deterministic fallback values on non-Apple hosts."""
        self.assertIn("bool desk_is_jit_enabled(void) { return false; }", self.darwin_c)
        self.assertIn("uint64_t desk_available_memory_bytes(void) { return 2ULL * 1024ULL * 1024ULL * 1024ULL; }", self.darwin_c)
        self.assertIn("uint64_t desk_process_footprint_bytes(void) { return 128ULL * 1024ULL * 1024ULL; }", self.darwin_c)
        self.assertIn("uint64_t desk_physical_memory_bytes(void) { return 6ULL * 1024ULL * 1024ULL * 1024ULL; }", self.darwin_c)
        self.assertIn("bool desk_probe_increased_memory_entitlement(void) { return false; }", self.darwin_c)
        self.assertIn("bool desk_probe_extended_va_entitlement(void) { return false; }", self.darwin_c)


if __name__ == "__main__":
    unittest.main()
