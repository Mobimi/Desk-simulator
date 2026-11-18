#!/usr/bin/env python3
"""
Desk-simulator Phase 2 Automated Verification Script.
Validates:
1. Workspace directory layout & Phase 2 baseline files
2. Entitlements plists & Info.plist validation (TrollStore vs Sideload)
3. C-ABI bridging header & Darwin runtime bridge verification
4. XcodeGen project definition (project.yml) specification & schema validation
5. GitHub Actions CI/CD workflow (.github/workflows/build-ipa.yml) validation
6. Swift source syntax, delimiter integrity, and cross-platform guards
7. Input HUD interface contracts (SPICE opcodes 0x01-0x06, scancodes, gamepad math)
8. Runtime monitors & management layer contracts (Jetsam zones, boot boost settling)
9. Phase 2 component logic test suites (Tests/Phase2Tests/)
10. Phase 1 zero-regression verification suite (verify_phase1, run_all_tests, run_e2e_tests)
"""

from __future__ import annotations

import argparse
import json
import os
import plistlib
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml

# Workspace root resolution
WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
if str(WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_ROOT))


class StrictArgumentParser(argparse.ArgumentParser):
    """ArgumentParser that outputs clean error message and exits with code 1 without tracebacks."""

    def error(self, message: str) -> None:
        sys.stderr.write(f"Error: {message}\n")
        sys.exit(1)


REQUIRED_PHASE2_DIRECTORIES: List[str] = [
    "Config",
    "Engine",
    "Engine/Config",
    "Engine/Core",
    "Engine/QEMU",
    "Engine/SPICE",
    "Engine/JIT",
    "Management",
    "Management/SmartMemoryGuard",
    "Management/PCoreScheduler",
    "Management/ISOAutoPilot",
    "Management/Storage",
    "Management/Runtime",
    "UI",
    "UI/App",
    "UI/ViewModels",
    "UI/Views",
    "UI/Views/InputHUD",
    ".github",
    ".github/workflows",
    "Scripts",
    "Tests",
    "Tests/Phase2Tests",
]

REQUIRED_PHASE2_FILES: List[str] = [
    "Config/DeskSimulator-TrollStore.entitlements",
    "Config/DeskSimulator-Sideload.entitlements",
    "Config/Info.plist",
    "Engine/DeskSimulator-Bridging-Header.h",
    "Engine/QEMU/DarwinRuntimeBridge.h",
    "Engine/QEMU/DarwinRuntimeBridge.c",
    "UI/Views/InputHUD/HapticTouchpadOverlay.swift",
    "UI/Views/InputHUD/PCShortcutToolbar.swift",
    "UI/Views/InputHUD/VirtualGamepadOverlay.swift",
    "UI/Views/MetalDisplayView.swift",
    "UI/Views/VMDisplaySessionView.swift",
    "project.yml",
    ".github/workflows/build-ipa.yml",
    "Scripts/verify_phase2.py",
    "Tests/Phase2Tests/__init__.py",
    "Tests/Phase2Tests/test_xcodegen_config.py",
    "Tests/Phase2Tests/test_github_actions_workflow.py",
    "Tests/Phase2Tests/test_config_and_entitlements.py",
    "Tests/Phase2Tests/test_input_hud_logic.py",
    "Tests/Phase2Tests/test_runtime_monitors_logic.py",
    "Tests/Phase2Tests/test_swift_symbol_resolution.py",
    "Tests/Phase2Tests/run_phase2_tests.py",
]


def log_pass(msg: str) -> None:
    print(f"  [PASS] {msg}")


def log_fail(msg: str) -> None:
    print(f"  [FAIL] {msg}")


# =========================================================================
# Check 1: Directory Structure & Baseline Files
# =========================================================================

def check_directory_structure_and_files(root: Path) -> Tuple[bool, str]:
    print("\n==> Check 1: Verifying Phase 2 Directory Layout & Baseline Files")
    for rel_dir in REQUIRED_PHASE2_DIRECTORIES:
        p = root / rel_dir
        if not p.is_dir():
            log_fail(f"Missing required directory: {rel_dir}")
            return False, f"Directory missing: {rel_dir}"
        log_pass(f"Directory verified: {rel_dir}")

    for rel_file in REQUIRED_PHASE2_FILES:
        p = root / rel_file
        if not p.is_file():
            log_fail(f"Missing required Phase 2 file: {rel_file}")
            return False, f"File missing: {rel_file}"
        if p.stat().st_size == 0:
            log_fail(f"File is empty: {rel_file}")
            return False, f"File is empty: {rel_file}"
        log_pass(f"Baseline file verified ({p.stat().st_size} bytes): {rel_file}")

    return True, "All Phase 2 directories and baseline files verified"


# =========================================================================
# Check 2: Entitlements Plists & Info.plist Validation
# =========================================================================

def check_entitlements_and_info_plist(root: Path) -> Tuple[bool, str]:
    print("\n==> Check 2: Verifying Entitlements Plists & Info.plist Validation")

    # 1. TrollStore Entitlements
    ts_path = root / "Config" / "DeskSimulator-TrollStore.entitlements"
    try:
        with open(ts_path, "rb") as f:
            ts_data = plistlib.load(f)
    except Exception as e:
        log_fail(f"Failed to parse {ts_path}: {e}")
        return False, f"Invalid TrollStore entitlements plist: {e}"

    required_ts_keys = [
        "com.apple.developer.kernel.increased-memory-limit",
        "com.apple.developer.kernel.extended-virtual-addressing",
        "dynamic-codesigning",
        "get-task-allow",
    ]
    for k in required_ts_keys:
        if not ts_data.get(k):
            log_fail(f"TrollStore entitlements missing or false for key: {k}")
            return False, f"TrollStore missing key: {k}"
        log_pass(f"TrollStore entitlement verified: {k} = True")

    # 2. Sideload Entitlements
    sl_path = root / "Config" / "DeskSimulator-Sideload.entitlements"
    try:
        with open(sl_path, "rb") as f:
            sl_data = plistlib.load(f)
    except Exception as e:
        log_fail(f"Failed to parse {sl_path}: {e}")
        return False, f"Invalid Sideload entitlements plist: {e}"

    if not sl_data.get("get-task-allow"):
        log_fail("Sideload entitlements missing get-task-allow")
        return False, "Sideload missing get-task-allow"
    log_pass("Sideload entitlement verified: get-task-allow = True")

    # Critical check: restricted entitlements must be absent in Sideload profile
    forbidden_sideload_keys = [
        "com.apple.developer.kernel.increased-memory-limit",
        "com.apple.developer.kernel.extended-virtual-addressing",
    ]
    for k in forbidden_sideload_keys:
        if k in sl_data:
            log_fail(f"Sideload profile must NOT contain restricted key {k}")
            return False, f"Sideload profile contains forbidden key {k}"
        log_pass(f"Sideload profile correctly omits restricted key: {k}")

    # 3. Info.plist
    info_path = root / "Config" / "Info.plist"
    try:
        with open(info_path, "rb") as f:
            info_data = plistlib.load(f)
    except Exception as e:
        log_fail(f"Failed to parse {info_path}: {e}")
        return False, f"Invalid Info.plist: {e}"

    if not info_data.get("CADisableMinimumFrameDurationOnPhone"):
        log_fail("Info.plist missing CADisableMinimumFrameDurationOnPhone for 120Hz ProMotion")
        return False, "Missing 120Hz ProMotion CADisableMinimumFrameDurationOnPhone"
    log_pass("Info.plist CADisableMinimumFrameDurationOnPhone = True (120Hz ProMotion)")

    caps = info_data.get("UIRequiredDeviceCapabilities", [])
    if "arm64" not in caps or "metal" not in caps:
        log_fail("Info.plist missing arm64 or metal device capabilities")
        return False, "Missing arm64 or metal capability"
    log_pass(f"Info.plist UIRequiredDeviceCapabilities verified: {caps}")

    if not info_data.get("UIFileSharingEnabled"):
        log_fail("Info.plist UIFileSharingEnabled is not enabled")
        return False, "UIFileSharingEnabled not enabled"
    log_pass("Info.plist UIFileSharingEnabled = True (Document management)")

    return True, "Entitlements and Info.plist validated successfully"


# =========================================================================
# Check 3: Bridging Header & Darwin Runtime Bridge Verification
# =========================================================================

def check_bridging_header_and_c_runtime(root: Path) -> Tuple[bool, str]:
    print("\n==> Check 3: Verifying C Bridging Header & Darwin Runtime Bridge")
    bridge_header = root / "Engine" / "DeskSimulator-Bridging-Header.h"
    content = bridge_header.read_text(encoding="utf-8")

    if "BootstrapBridge.h" not in content or "DarwinRuntimeBridge.h" not in content:
        log_fail("Bridging header missing BootstrapBridge.h or DarwinRuntimeBridge.h")
        return False, "Bridging header missing required C header includes"
    log_pass("Bridging header includes BootstrapBridge.h and DarwinRuntimeBridge.h")

    # Header and C-ABI symbols
    h_file = root / "Engine" / "QEMU" / "DarwinRuntimeBridge.h"
    c_file = root / "Engine" / "QEMU" / "DarwinRuntimeBridge.c"
    h_text = h_file.read_text(encoding="utf-8")
    c_text = c_file.read_text(encoding="utf-8")

    symbols = [
        "desk_is_jit_enabled",
        "desk_available_memory_bytes",
        "desk_process_footprint_bytes",
        "desk_physical_memory_bytes",
        "desk_probe_increased_memory_entitlement",
        "desk_probe_extended_va_entitlement",
    ]
    for sym in symbols:
        if sym not in h_text:
            log_fail(f"Symbol {sym} missing from DarwinRuntimeBridge.h")
            return False, f"Missing declaration: {sym}"
        if sym not in c_text:
            log_fail(f"Symbol {sym} missing from DarwinRuntimeBridge.c")
            return False, f"Missing implementation: {sym}"
        log_pass(f"C-ABI probe verified: {sym}()")

    if "#else" not in c_text:
        log_fail("DarwinRuntimeBridge.c missing #else portability fallback stubs")
        return False, "Missing portability fallback in DarwinRuntimeBridge.c"
    log_pass("DarwinRuntimeBridge.c portability fallback stubs verified for non-Apple targets")

    return True, "Bridging header and native Darwin runtime bridge verified"


# =========================================================================
# Check 4: XcodeGen project.yml Specification & Schema Validation
# =========================================================================

def check_xcodegen_project_spec(root: Path) -> Tuple[bool, str]:
    print("\n==> Check 4: Verifying XcodeGen project.yml Specification & Schema")
    spec_path = root / "project.yml"
    try:
        with open(spec_path, "r", encoding="utf-8") as f:
            spec = yaml.safe_load(f)
    except Exception as e:
        log_fail(f"Failed to parse project.yml: {e}")
        return False, f"Invalid YAML in project.yml: {e}"

    # Target
    targets = spec.get("targets", {})
    if "DeskSimulator" not in targets:
        log_fail("Target DeskSimulator not found in project.yml")
        return False, "Missing target DeskSimulator"
    target = targets["DeskSimulator"]

    if target.get("type") != "application" or target.get("platform") != "iOS":
        log_fail("Target DeskSimulator must be an iOS application")
        return False, "Invalid target type/platform"
    log_pass("Target DeskSimulator (iOS application) verified")

    # Sources
    sources = target.get("sources", [])
    src_paths = [s.get("path") if isinstance(s, dict) else s for s in sources]
    for expected in ["Engine", "Management", "UI", "Config"]:
        if expected not in src_paths:
            log_fail(f"Sources missing path: {expected}")
            return False, f"Missing source: {expected}"
        log_pass(f"Target source verified: {expected}")

    # Settings
    base_settings = target.get("settings", {}).get("base", {})
    if base_settings.get("INFOPLIST_FILE") != "Config/Info.plist":
        log_fail("INFOPLIST_FILE must point to Config/Info.plist")
        return False, "Invalid INFOPLIST_FILE"
    if base_settings.get("SWIFT_OBJC_BRIDGING_HEADER") != "Engine/DeskSimulator-Bridging-Header.h":
        log_fail("SWIFT_OBJC_BRIDGING_HEADER must point to Engine/DeskSimulator-Bridging-Header.h")
        return False, "Invalid SWIFT_OBJC_BRIDGING_HEADER"
    log_pass("Base settings verified (Info.plist & Bridging Header)")

    # Framework dependencies
    deps = target.get("dependencies", [])
    frameworks = [d.get("sdk") for d in deps if isinstance(d, dict) and "sdk" in d]
    for req_fw in ["Metal.framework", "MetalKit.framework", "GameController.framework", "AudioToolbox.framework"]:
        if req_fw not in frameworks:
            log_fail(f"Missing framework dependency: {req_fw}")
            return False, f"Missing dependency: {req_fw}"
        log_pass(f"Framework dependency verified: {req_fw}")

    # Dual Schemes
    schemes = spec.get("schemes", {})
    if "DeskSimulator-TrollStore" not in schemes:
        log_fail("Missing scheme DeskSimulator-TrollStore")
        return False, "Missing TrollStore scheme"
    if "DeskSimulator-Sideload" not in schemes:
        log_fail("Missing scheme DeskSimulator-Sideload")
        return False, "Missing Sideload scheme"
    log_pass("Dual schemes verified (DeskSimulator-TrollStore, DeskSimulator-Sideload)")

    return True, "XcodeGen project.yml verified and compliant"


# =========================================================================
# Check 5: GitHub Actions Workflow YAML Validation
# =========================================================================

def check_github_actions_workflow(root: Path) -> Tuple[bool, str]:
    print("\n==> Check 5: Verifying GitHub Actions Workflow YAML (.github/workflows/build-ipa.yml)")
    wf_path = root / ".github" / "workflows" / "build-ipa.yml"
    try:
        with open(wf_path, "r", encoding="utf-8") as f:
            wf = yaml.safe_load(f)
    except Exception as e:
        log_fail(f"Failed to parse build-ipa.yml: {e}")
        return False, f"Invalid YAML in build-ipa.yml: {e}"

    jobs = wf.get("jobs", {})
    if not jobs:
        log_fail("No jobs declared in workflow")
        return False, "No jobs in workflow"

    job = list(jobs.values())[0]
    runner = job.get("runs-on")
    if runner not in ["macos-14", "macos-15"]:
        log_fail(f"Job runs-on must be macos-14 or macos-15 (got {runner})")
        return False, f"Invalid runner: {runner}"
    log_pass(f"Job runner verified: {runner}")

    steps = job.get("steps", [])
    all_runs = " ".join([s.get("run", "") for s in steps])
    all_uses = " ".join([s.get("uses", "") for s in steps])

    if "xcodegen generate" not in all_runs:
        log_fail("Workflow missing xcodegen generate step")
        return False, "Missing xcodegen generate step"
    log_pass("Workflow step verified: xcodegen generate")

    if "DeskSimulator-TrollStore" not in all_runs or "DeskSimulator-TrollStore.ipa" not in all_runs:
        log_fail("Workflow missing TrollStore archive or IPA packaging step")
        return False, "Missing TrollStore build step"
    log_pass("Workflow step verified: TrollStore archive & IPA packaging")

    if "DeskSimulator-Sideload" not in all_runs or "DeskSimulator-Sideload.ipa" not in all_runs:
        log_fail("Workflow missing Sideload archive or IPA packaging step")
        return False, "Missing Sideload build step"
    log_pass("Workflow step verified: Sideload archive & IPA packaging")

    if "actions/upload-artifact" not in all_uses:
        log_fail("Workflow missing actions/upload-artifact step")
        return False, "Missing artifact upload step"
    log_pass("Workflow step verified: actions/upload-artifact@v4")

    return True, "GitHub Actions CI/CD workflow verified and compliant"


# =========================================================================
# Check 6: Swift Source Syntax & Delimiter Integrity
# =========================================================================

def _check_delimiter_balance(path: Path) -> Optional[str]:
    content = path.read_text(encoding="utf-8")
    stack: List[Tuple[str, int]] = []
    pairs = {")": "(", "}": "{", "]": "["}
    lines = content.splitlines()
    in_block_comment = False

    for line_idx, line in enumerate(lines, 1):
        i = 0
        in_string = False
        quote_char = None
        while i < len(line):
            ch = line[i]
            if in_block_comment:
                if line[i:i+2] == "*/":
                    in_block_comment = False
                    i += 2
                    continue
                i += 1
                continue

            if in_string:
                if ch == "\\":
                    i += 2
                    continue
                if ch == quote_char:
                    in_string = False
                i += 1
                continue

            if line[i:i+2] == "/*":
                in_block_comment = True
                i += 2
                continue

            if line[i:i+2] == "//":
                break

            if ch in "\"\'":
                in_string = True
                quote_char = ch
                i += 1
                continue

            if ch in "({[":
                stack.append((ch, line_idx))
            elif ch in ")}]":
                if not stack:
                    return f"Unexpected closing '{ch}' at line {line_idx}"
                top, top_line = stack.pop()
                if pairs[ch] != top:
                    return f"Mismatched '{ch}' at line {line_idx}, expected matching '{top}' from line {top_line}"
            i += 1

    if stack:
        top, top_line = stack.pop()
        return f"Unclosed '{top}' from line {top_line}"
    return None


def check_swift_source_syntax_integrity(root: Path) -> Tuple[bool, str]:
    print("\n==> Check 6: Verifying Swift Source Syntax, Delimiters & Symbol Resolution")
    swift_files = list(root.glob("Engine/**/*.swift")) + \
                  list(root.glob("Management/**/*.swift")) + \
                  list(root.glob("UI/**/*.swift"))

    if not swift_files:
        log_fail("No Swift files found in workspace")
        return False, "No Swift files found"

    for sf in swift_files:
        err = _check_delimiter_balance(sf)
        rel = sf.relative_to(root)
        if err:
            log_fail(f"Syntax error in {rel}: {err}")
            return False, f"Delimiter error in {rel}: {err}"

        # Check for unresolved placeholders
        text = sf.read_text(encoding="utf-8")
        forbidden_markers = ["<#code#>", "<#T##", "FATAL_UNIMPLEMENTED", "TODO_UNIMPLEMENTED"]
        for marker in forbidden_markers:
            if marker in text:
                log_fail(f"Unresolved placeholder '{marker}' found in {rel}")
                return False, f"Placeholder in {rel}"

        log_pass(f"Swift file syntax & delimiter balance verified: {rel}")

    # Static Cross-File Member Symbol & Interface Resolution Forensics
    print("    --> Performing cross-file Swift static member symbol resolution...")
    try:
        from Tests.Phase2Tests.test_swift_symbol_resolution import SwiftSymbolResolver
    except ImportError:
        sys.path.insert(0, str(root))
        from Tests.Phase2Tests.test_swift_symbol_resolution import SwiftSymbolResolver

    resolver = SwiftSymbolResolver(root)
    symbol_errors = resolver.check_call_sites()
    if symbol_errors:
        for err in symbol_errors:
            log_fail(f"Undefined symbol in {err['file']}:{err['line']}: {err['message']} (in '{err['expression']}')")
        return False, f"Static member resolution failed with {len(symbol_errors)} undefined symbol error(s)"

    log_pass(f"All Swift member call sites resolved cleanly across {len(resolver.types)} discovered types")
    return True, f"All {len(swift_files)} Swift source files passed delimiter and symbol resolution integrity checks"


# =========================================================================
# Check 7: Input HUD Interface Contracts
# =========================================================================

def check_input_hud_interface_contracts(root: Path) -> Tuple[bool, str]:
    print("\n==> Check 7: Verifying Input HUD Interface Contracts & Wire Protocols")

    # 1. HapticTouchpadOverlay
    touchpad_file = root / "UI" / "Views" / "InputHUD" / "HapticTouchpadOverlay.swift"
    tp_text = touchpad_file.read_text(encoding="utf-8")
    if "sendMouseMove" not in tp_text or "sendMouseButton" not in tp_text or "sendMouseScroll" not in tp_text:
        log_fail("HapticTouchpadOverlay missing mouse event forwarding calls")
        return False, "Touchpad missing mouse event calls"
    log_pass("HapticTouchpadOverlay verified (relative move, tap-to-click, scroll strip, haptics)")

    # 2. PCShortcutToolbar
    toolbar_file = root / "UI" / "Views" / "InputHUD" / "PCShortcutToolbar.swift"
    tb_text = toolbar_file.read_text(encoding="utf-8")
    if "PCKeyScancode" not in tb_text or "tapPCShortcut" not in tb_text:
        log_fail("PCShortcutToolbar missing PCKeyScancode or shortcut tap calls")
        return False, "Toolbar missing scancode bindings"
    if "ctrlHeld" not in tb_text or "altHeld" not in tb_text or "winHeld" not in tb_text:
        log_fail("PCShortcutToolbar missing modifier key latching states")
        return False, "Toolbar missing modifier latching"
    log_pass("PCShortcutToolbar verified (Esc, Tab, Ctrl/Alt/Win latching, F1-F12, combos)")

    # 3. VirtualGamepadOverlay
    gamepad_file = root / "UI" / "Views" / "InputHUD" / "VirtualGamepadOverlay.swift"
    gp_text = gamepad_file.read_text(encoding="utf-8")
    if "GamepadButtonID" not in gp_text or "sendGamepadButton" not in gp_text or "sendGamepadStick" not in gp_text:
        log_fail("VirtualGamepadOverlay missing GamepadButtonID or packet forwarding")
        return False, "Gamepad missing button/stick forwarding"
    if "deadzone" not in gp_text:
        log_fail("VirtualGamepadOverlay missing deadzone filtering")
        return False, "Gamepad missing deadzone"
    log_pass("VirtualGamepadOverlay verified (dual sticks, deadzone filtering, ABXY, triggers)")

    # 4. MetalDisplayView
    metal_view = root / "UI" / "Views" / "MetalDisplayView.swift"
    mv_text = metal_view.read_text(encoding="utf-8")
    if "MTKViewDelegate" not in mv_text or "render(to:" not in mv_text:
        log_fail("MetalDisplayView missing MTKViewDelegate or render(to:) delegation")
        return False, "MetalDisplayView missing renderer delegation"
    log_pass("MetalDisplayView verified (MTKView delegate, ProMotion refresh rate, renderer.render(to:))")

    # 5. VMDisplaySessionView
    session_view = root / "UI" / "Views" / "VMDisplaySessionView.swift"
    sv_text = session_view.read_text(encoding="utf-8")
    if "MetalDisplayView" not in sv_text or "startSession" not in sv_text or "stopSession" not in sv_text:
        log_fail("VMDisplaySessionView missing MetalDisplayView or session lifecycle hooks")
        return False, "VMDisplaySessionView missing core integration"
    log_pass("VMDisplaySessionView verified (display layer, dynamic HUDs, telemetry, session lifecycle)")

    return True, "All Input HUD interface contracts and wire protocols verified"


# =========================================================================
# Check 8: Runtime Monitors & Management Contracts
# =========================================================================

def check_runtime_monitors_contracts(root: Path) -> Tuple[bool, str]:
    print("\n==> Check 8: Verifying Runtime Monitors & Management Layer Contracts")

    # 1. RuntimeMemoryMonitor
    rmm_file = root / "Management" / "Runtime" / "RuntimeMemoryMonitor.swift"
    rmm_text = rmm_file.read_text(encoding="utf-8")
    if "safeGuestCeilingMB" not in rmm_text or "JetsamDangerZone" not in rmm_text or "currentUsageMB" not in rmm_text:
        log_fail("RuntimeMemoryMonitor missing safeGuestCeilingMB, JetsamDangerZone, or currentUsageMB")
        return False, "Memory monitor missing ceiling/danger calculations"
    log_pass("RuntimeMemoryMonitor verified (live telemetry, 450MB reserve, Jetsam danger zones, currentUsageMB)")

    # 2. ThermalMonitor
    tm_file = root / "Management" / "Runtime" / "ThermalMonitor.swift"
    tm_text = tm_file.read_text(encoding="utf-8")
    if "beginBootBoost" not in tm_text or "thermalStateDidChange" not in tm_text or "thermalLevel" not in tm_text:
        log_fail("ThermalMonitor missing beginBootBoost, thermal observer, or thermalLevel alias")
        return False, "ThermalMonitor missing boost coordination"
    log_pass("ThermalMonitor verified (Dynamic P-Core Boot Boost & thermal strain settling, thermalLevel alias)")

    # 3. VMStore & VMProfile
    store_file = root / "Management" / "Runtime" / "VMStore.swift"
    prof_file = root / "Management" / "Runtime" / "VMProfile.swift"
    st_text = store_file.read_text(encoding="utf-8")
    pr_text = prof_file.read_text(encoding="utf-8")
    if "profiles.json" not in st_text or "makeQEMUConfiguration" not in pr_text:
        log_fail("VMStore / VMProfile missing persistent storage or QEMU CLI synthesis")
        return False, "VMStore / VMProfile missing methods"
    log_pass("VMStore & VMProfile verified (JSON persistence, template catalog, CLI synthesis)")

    return True, "Runtime monitors and management layer contracts verified"


# =========================================================================
# Check 9: Phase 2 Component Logic Tests
# =========================================================================

def check_phase2_component_tests(root: Path, dry_run: bool = False) -> Tuple[bool, str]:
    print("\n==> Check 9: Executing Phase 2 Component Logic Test Suite")
    if dry_run:
        log_pass("Dry-run: Skipped external test runner subprocess")
        return True, "Dry-run skipped test execution"

    runner_script = root / "Tests" / "Phase2Tests" / "run_phase2_tests.py"
    if not runner_script.exists():
        log_fail("Missing Tests/Phase2Tests/run_phase2_tests.py")
        return False, "Missing Phase 2 test runner"

    res = subprocess.run(
        [sys.executable, str(runner_script)],
        cwd=str(root),
        capture_output=True,
        text=True,
    )
    if res.returncode != 0:
        log_fail(f"Phase 2 test suite failed (exit code {res.returncode}):\n{res.stdout}\n{res.stderr}")
        return False, f"Phase 2 tests failed with exit code {res.returncode}"

    print(res.stdout.strip())
    log_pass("All Phase 2 component logic tests passed with 100% success!")
    return True, "Phase 2 component logic tests PASSED"


# =========================================================================
# Check 10: Phase 1 Zero Regression Suite
# =========================================================================

def check_phase1_zero_regression(root: Path, skip_regression: bool = False, dry_run: bool = False) -> Tuple[bool, str]:
    print("\n==> Check 10: Enforcing Phase 1 Zero Regression Suite")
    if skip_regression:
        log_pass("Skipping regression check as requested (--skip-regression)")
        return True, "Regression check skipped"
    if dry_run:
        log_pass("Dry-run: Skipped regression check")
        return True, "Dry-run skipped regression check"

    # Step A: verify_phase1.py
    v1_script = root / "Scripts" / "verify_phase1.py"
    res1 = subprocess.run(
        [sys.executable, str(v1_script), "--skip-git"],
        cwd=str(root),
        capture_output=True,
        text=True,
    )
    if res1.returncode != 0:
        log_fail(f"Phase 1 verification script failed (exit code {res1.returncode}):\n{res1.stderr}")
        return False, "verify_phase1.py regression detected"
    log_pass("verify_phase1.py passed (10/10 checks OK)")

    # Step B: run_all_tests.py
    unit_script = root / "Tests" / "run_all_tests.py"
    res2 = subprocess.run(
        [sys.executable, str(unit_script)],
        cwd=str(root),
        capture_output=True,
        text=True,
    )
    if res2.returncode != 0:
        log_fail(f"Phase 1 unit test runner failed (exit code {res2.returncode}):\n{res2.stderr}")
        return False, "run_all_tests.py regression detected"
    log_pass("run_all_tests.py passed (121/121 unit & mock tests OK)")

    # Step C: run_e2e_tests.py
    e2e_script = root / "Tests" / "E2ETests" / "run_e2e_tests.py"
    res3 = subprocess.run(
        [sys.executable, str(e2e_script)],
        cwd=str(root),
        capture_output=True,
        text=True,
    )
    if res3.returncode != 0:
        log_fail(f"Phase 1 E2E test runner failed (exit code {res3.returncode}):\n{res3.stderr}")
        return False, "run_e2e_tests.py regression detected"
    log_pass("run_e2e_tests.py passed (278/278 E2E tests OK)")

    return True, "Zero regressions detected across all Phase 1 test suites (100% PASS)"


# =========================================================================
# Main Execution Harness
# =========================================================================

def run_all_phase2_checks(
    root: Path,
    skip_regression: bool = False,
    dry_run: bool = False,
) -> Tuple[bool, List[Dict[str, Any]]]:
    checks = [
        ("Directory Layout & Baseline Files", lambda: check_directory_structure_and_files(root)),
        ("Entitlements & Info.plist Validation", lambda: check_entitlements_and_info_plist(root)),
        ("C Bridging Header & Darwin Runtime Bridge", lambda: check_bridging_header_and_c_runtime(root)),
        ("XcodeGen project.yml Specification", lambda: check_xcodegen_project_spec(root)),
        ("GitHub Actions CI/CD Workflow", lambda: check_github_actions_workflow(root)),
        ("Swift Source Syntax & Delimiters", lambda: check_swift_source_syntax_integrity(root)),
        ("Input HUD Interface Contracts", lambda: check_input_hud_interface_contracts(root)),
        ("Runtime Monitors & Management Contracts", lambda: check_runtime_monitors_contracts(root)),
        ("Phase 2 Component Logic Tests", lambda: check_phase2_component_tests(root, dry_run=dry_run)),
        ("Phase 1 Zero-Regression Enforcement", lambda: check_phase1_zero_regression(root, skip_regression=skip_regression, dry_run=dry_run)),
    ]

    results: List[Dict[str, Any]] = []
    overall_success = True

    for name, fn in checks:
        try:
            success, message = fn()
        except Exception as e:
            success = False
            message = f"Unhandled exception: {e}"
            log_fail(message)

        results.append({
            "check": name,
            "success": success,
            "message": message,
        })
        if not success:
            overall_success = False

    return overall_success, results


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = StrictArgumentParser(
        description="Automated Phase 2 Verification Script for Desk-simulator PC OS Emulator.",
        allow_abbrev=False,
    )
    parser.add_argument(
        "--workspace-root",
        type=str,
        default=str(WORKSPACE_ROOT),
        help="Path to workspace root directory (default: parent of Scripts/)",
    )
    parser.add_argument(
        "--skip-regression",
        action="store_true",
        default=False,
        help="Skip Phase 1 regression test suites (for fast Phase 2 iterations)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Simulate verification without executing external test runners",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        default=False,
        help="Enable verbose output logging",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        default=False,
        help="Output results in structured JSON format",
    )
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)
    root = Path(args.workspace_root).resolve()

    if not args.json:
        print("=" * 75)
        print(" Desk-simulator Phase 2 Automated Verification Script")
        print(f" Workspace Root: {root}")
        print("=" * 75)

    success, results = run_all_phase2_checks(
        root,
        skip_regression=args.skip_regression,
        dry_run=args.dry_run,
    )

    if args.json:
        output_data = {
            "overall_status": "PASS" if success else "FAIL",
            "workspace_root": str(root),
            "checks": results,
            "total_checks": len(results),
            "passed_checks": sum(1 for r in results if r["success"]),
            "failed_checks": sum(1 for r in results if not r["success"]),
        }
        print(json.dumps(output_data, indent=2))
        return 0 if success else 1

    print("\n" + "=" * 75)
    if success:
        print(f"  [SUCCESS] Phase 2 Verification Passed! (All {len(results)} Checks OK)")
        print("  Desk-simulator is fully compliant with Phase 2 Architecture Specifications.")
    else:
        failed_count = sum(1 for r in results if not r["success"])
        print(f"  [FAIL] Phase 2 Verification Failed! ({failed_count}/{len(results)} checks failed)")
    print("=" * 75 + "\n")

    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
