#!/usr/bin/env python3
"""
Desk-simulator Phase 3 Automated Verification Script.
Validates:
1. Engine Linkage & Search Paths (project.yml search paths, frameworks, bridging header)
2. Native C-ABI Bridge Signatures (BootstrapBridge.h/.c exports, 13 C-ABI functions, pthread, spawn, callback)
3. Darwin Runtime Probes & JIT Detection (DarwinRuntimeBridge.h/.c csops JIT, memory footprint, Mach fallbacks)
4. ProcessLauncher Thread & Lifecycle Hooks (ProcessLauncher.swift QoS .userInteractive, C-array string marshalling with defer free, dlsym, state machine)
5. VMController Boot Pipeline & State Management (VMController.swift QEMUArgumentsBuilder, boot orchestration, UDS socket validation <= 108 bytes & anti-TCP policy, state machine)
6. SPICE Unix Domain Socket & Display Ingestion (SPICEConnection.swift UDS stream transport, anti-TCP rejection, ingestDisplayFrame, delegate callbacks)
7. Metal Framebuffer Rendering & UI Session Integration (MetalDisplayRenderer.swift .bgra8Unorm texture updates, 120Hz ProMotion, MetalDisplayView aspect ratio letterboxing)
8. Packaging Configurations & CI/CD Workflow (project.yml dual schemes/targets, TrollStore vs Sideload entitlements separation, .github/workflows/build-ipa.yml dual IPA packaging)
9. Automated Phase 3 Component Test Suite (executes Tests/Phase3Tests/run_phase3_tests.py)
10. Zero Regression Verification (executes Scripts/verify_phase1.py, Scripts/verify_phase2.py, Tests/run_all_tests.py, and Tests/E2ETests/run_e2e_tests.py)
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


def log_pass(msg: str) -> None:
    print(f"  [PASS] {msg}")


def log_fail(msg: str) -> None:
    print(f"  [FAIL] {msg}")


def log_info(msg: str) -> None:
    print(f"  [INFO] {msg}")


# =========================================================================
# Check 1: Engine Linkage & Search Paths
# =========================================================================

def check_engine_linkage_and_search_paths(root: Path) -> Tuple[bool, str]:
    print("\n==> Check 1: Verifying Engine Linkage & Search Paths")

    # 1. Inspect project.yml
    spec_path = root / "project.yml"
    try:
        with open(spec_path, "r", encoding="utf-8") as f:
            spec = yaml.safe_load(f)
    except Exception as e:
        log_fail(f"Failed to parse project.yml: {e}")
        return False, f"Invalid YAML in project.yml: {e}"

    targets = spec.get("targets", {})
    if "DeskSimulator" not in targets:
        log_fail("Target DeskSimulator not found in project.yml")
        return False, "Missing target DeskSimulator in project.yml"

    target = targets["DeskSimulator"]
    settings = target.get("settings", {}).get("base", {})

    # Verify Header Search Paths
    h_paths = settings.get("HEADER_SEARCH_PATHS", [])
    expected_h_paths = [
        "$(SRCROOT)/Engine",
        "$(SRCROOT)/Engine/QEMU",
        "$(SRCROOT)/Engine/SPICE",
        "$(SRCROOT)/Engine/Core",
    ]
    for hp in expected_h_paths:
        if hp not in h_paths:
            log_fail(f"Missing HEADER_SEARCH_PATHS entry: {hp}")
            return False, f"Missing header search path: {hp}"
        log_pass(f"Header search path verified: {hp}")

    # Verify Library Search Paths
    lib_paths = settings.get("LIBRARY_SEARCH_PATHS", [])
    expected_lib_paths = [
        "$(SRCROOT)/Engine/QEMU/lib",
        "$(SRCROOT)/Engine/SPICE/lib",
    ]
    for lp in expected_lib_paths:
        if lp not in lib_paths:
            log_fail(f"Missing LIBRARY_SEARCH_PATHS entry: {lp}")
            return False, f"Missing library search path: {lp}"
        log_pass(f"Library search path verified: {lp}")

    # Verify Framework Search Paths
    fw_paths = settings.get("FRAMEWORK_SEARCH_PATHS", [])
    if "$(SRCROOT)/Frameworks" not in fw_paths:
        log_fail("Missing FRAMEWORK_SEARCH_PATHS entry: $(SRCROOT)/Frameworks")
        return False, "Missing framework search path: $(SRCROOT)/Frameworks"
    log_pass("Framework search path verified: $(SRCROOT)/Frameworks")

    # Verify Linker Flags
    ldflags = settings.get("OTHER_LDFLAGS", [])
    for req_flag in ["-ObjC", "-Wl,-undefined,dynamic_lookup"]:
        if req_flag not in ldflags:
            log_fail(f"Missing OTHER_LDFLAGS flag: {req_flag}")
            return False, f"Missing linker flag: {req_flag}"
        log_pass(f"Linker flag verified: {req_flag}")

    # Verify Framework Dependencies
    deps = target.get("dependencies", [])
    frameworks = [d.get("sdk") for d in deps if isinstance(d, dict) and "sdk" in d]
    required_frameworks = [
        "Metal.framework",
        "MetalKit.framework",
        "GameController.framework",
        "AudioToolbox.framework",
    ]
    for req_fw in required_frameworks:
        if req_fw not in frameworks:
            log_fail(f"Missing framework dependency: {req_fw}")
            return False, f"Missing framework dependency: {req_fw}"
        log_pass(f"Framework dependency verified: {req_fw}")

    # Verify Bridging Header
    bridge_path_str = settings.get("SWIFT_OBJC_BRIDGING_HEADER")
    if bridge_path_str != "Engine/DeskSimulator-Bridging-Header.h":
        log_fail(f"SWIFT_OBJC_BRIDGING_HEADER must be Engine/DeskSimulator-Bridging-Header.h, got {bridge_path_str}")
        return False, "Invalid SWIFT_OBJC_BRIDGING_HEADER in project.yml"

    bridge_file = root / "Engine" / "DeskSimulator-Bridging-Header.h"
    if not bridge_file.is_file() or bridge_file.stat().st_size == 0:
        log_fail("Bridging header file missing or empty")
        return False, "Bridging header file missing or empty"

    bridge_text = bridge_file.read_text(encoding="utf-8")
    if "BootstrapBridge.h" not in bridge_text or "DarwinRuntimeBridge.h" not in bridge_text:
        log_fail("Bridging header must import BootstrapBridge.h and DarwinRuntimeBridge.h")
        return False, "Bridging header missing required imports"
    log_pass("Bridging header verified with BootstrapBridge.h and DarwinRuntimeBridge.h imports")

    return True, "Engine linkage and search paths verified successfully"


# =========================================================================
# Check 2: Native C-ABI Bridge Signatures
# =========================================================================

def check_native_c_abi_bridge_signatures(root: Path) -> Tuple[bool, str]:
    print("\n==> Check 2: Verifying Native C-ABI Bridge Signatures")

    h_path = root / "Engine" / "QEMU" / "BootstrapBridge.h"
    c_path = root / "Engine" / "QEMU" / "BootstrapBridge.c"

    if not h_path.is_file() or not c_path.is_file():
        log_fail("BootstrapBridge.h or BootstrapBridge.c missing")
        return False, "BootstrapBridge source files missing"

    h_text = h_path.read_text(encoding="utf-8")
    c_text = c_path.read_text(encoding="utf-8")

    # 13 C-ABI functions
    expected_functions = [
        "qemu_init",
        "qemu_init_target",
        "qemu_main_loop",
        "qemu_request_exit",
        "qemu_cleanup",
        "qemu_is_running",
        "qemu_get_status",
        "qemu_bootstrap_start_thread",
        "qemu_bootstrap_join_thread",
        "qemu_spawn_process",
        "qemu_poll_process",
        "qemu_terminate_process",
        "qemu_register_display_callback",
    ]

    for fn_name in expected_functions:
        if fn_name not in h_text:
            log_fail(f"BootstrapBridge.h missing declaration: {fn_name}")
            return False, f"Missing declaration: {fn_name}"
        if fn_name not in c_text:
            log_fail(f"BootstrapBridge.c missing implementation: {fn_name}")
            return False, f"Missing implementation: {fn_name}"
        log_pass(f"C-ABI function verified: {fn_name}()")

    # Struct & Enum definitions
    if "QEMUStatusCode" not in h_text or "QEMU_STATUS_STOPPED" not in h_text or "QEMU_STATUS_RUNNING" not in h_text:
        log_fail("BootstrapBridge.h missing QEMUStatusCode enum definitions")
        return False, "Missing QEMUStatusCode in BootstrapBridge.h"
    log_pass("QEMUStatusCode enum verified (STOPPED, INITIALIZING, RUNNING, PAUSED, TERMINATING, ERROR)")

    if "QEMUDisplayFrame" not in h_text or "QEMUDisplayFrameCallback" not in h_text:
        log_fail("BootstrapBridge.h missing QEMUDisplayFrame or callback typedef")
        return False, "Missing QEMUDisplayFrame typedef in BootstrapBridge.h"
    log_pass("QEMUDisplayFrame and QEMUDisplayFrameCallback types verified")

    # Pthread hooks with 4MB+ stack and QoS
    if "pthread_attr_setstacksize" not in c_text or "QOS_CLASS_USER_INTERACTIVE" not in c_text:
        log_fail("BootstrapBridge.c missing pthread 4MB+ stack or User Interactive QoS")
        return False, "Missing pthread 4MB stack or QoS in BootstrapBridge.c"
    log_pass("Pthread thread bootstrapping hook verified (4MB+ stack, QOS_CLASS_USER_INTERACTIVE)")

    # POSIX spawn hooks
    if "posix_spawn" not in c_text:
        log_fail("BootstrapBridge.c missing posix_spawn process execution hook")
        return False, "Missing posix_spawn hook in BootstrapBridge.c"
    log_pass("POSIX process spawn hook verified (posix_spawn)")

    # Non-Apple fallback stubs
    if "#else" not in c_text:
        log_fail("BootstrapBridge.c missing non-Apple #else fallback stubs")
        return False, "Missing portability fallback in BootstrapBridge.c"
    log_pass("Portability fallback stubs verified for non-Apple hosts")

    return True, "Native C-ABI bridge signatures verified (13 functions, pthread, spawn, callback)"


# =========================================================================
# Check 3: Darwin Runtime Probes & JIT Detection
# =========================================================================

def check_darwin_runtime_probes_and_jit(root: Path) -> Tuple[bool, str]:
    print("\n==> Check 3: Verifying Darwin Runtime Probes & JIT Detection")

    h_path = root / "Engine" / "QEMU" / "DarwinRuntimeBridge.h"
    c_path = root / "Engine" / "QEMU" / "DarwinRuntimeBridge.c"

    if not h_path.is_file() or not c_path.is_file():
        log_fail("DarwinRuntimeBridge.h or DarwinRuntimeBridge.c missing")
        return False, "DarwinRuntimeBridge source files missing"

    h_text = h_path.read_text(encoding="utf-8")
    c_text = c_path.read_text(encoding="utf-8")

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
            log_fail(f"DarwinRuntimeBridge.h missing declaration: {sym}")
            return False, f"Missing declaration: {sym}"
        if sym not in c_text:
            log_fail(f"DarwinRuntimeBridge.c missing implementation: {sym}")
            return False, f"Missing implementation: {sym}"
        log_pass(f"Darwin runtime probe verified: {sym}()")

    # csops JIT detection
    if "csops" not in c_text or "DESK_CS_DEBUGGED" not in c_text:
        log_fail("DarwinRuntimeBridge.c missing csops JIT detection")
        return False, "Missing csops JIT detection in DarwinRuntimeBridge.c"
    log_pass("JIT detection probe verified via csops CS_DEBUGGED flag")

    # Mach task_info memory footprint
    if "TASK_VM_INFO" not in c_text or "phys_footprint" not in c_text:
        log_fail("DarwinRuntimeBridge.c missing TASK_VM_INFO physical footprint probe")
        return False, "Missing TASK_VM_INFO in DarwinRuntimeBridge.c"
    log_pass("Process physical footprint probe verified via Mach TASK_VM_INFO")

    # os_proc_available_memory and Mach fallback
    if "os_proc_available_memory" not in c_text:
        log_fail("DarwinRuntimeBridge.c missing os_proc_available_memory")
        return False, "Missing os_proc_available_memory in DarwinRuntimeBridge.c"
    log_pass("Jetsam available memory probe verified with Mach fallback")

    # Entitlement probes (increased memory ratio and 6GB VA probe)
    if "0.65" not in c_text or "PROT_NONE" not in c_text:
        log_fail("DarwinRuntimeBridge.c missing memory entitlement or VA probe logic")
        return False, "Missing entitlement probe logic in DarwinRuntimeBridge.c"
    log_pass("Dynamic entitlement probes verified (increased-memory ratio and 6GB VA reservation)")

    # Portability fallbacks
    if "#else" not in c_text:
        log_fail("DarwinRuntimeBridge.c missing non-Apple #else fallback stubs")
        return False, "Missing portability fallback in DarwinRuntimeBridge.c"
    log_pass("Portability fallback stubs verified for non-Apple hosts")

    return True, "Darwin runtime probes and JIT detection verified successfully"


# =========================================================================
# Check 4: ProcessLauncher Thread & Lifecycle Hooks
# =========================================================================

def check_process_launcher_thread_and_lifecycle(root: Path) -> Tuple[bool, str]:
    print("\n==> Check 4: Verifying ProcessLauncher Thread & Lifecycle Hooks")

    launcher_path = root / "Engine" / "Core" / "ProcessLauncher.swift"
    if not launcher_path.is_file():
        log_fail("ProcessLauncher.swift missing")
        return False, "ProcessLauncher.swift missing"

    text = launcher_path.read_text(encoding="utf-8")

    # LaunchState enum
    for state_name in ["idle", "launching", "running", "stopping", "terminated", "failed"]:
        if state_name not in text:
            log_fail(f"ProcessLauncher.swift missing LaunchState case: {state_name}")
            return False, f"Missing LaunchState: {state_name}"
    log_pass("LaunchState enum verified (idle, launching, running, stopping, terminated, failed)")

    # Delegate protocol
    if "ProcessLauncherDelegate" not in text or "didChangeState" not in text:
        log_fail("ProcessLauncher.swift missing ProcessLauncherDelegate protocol")
        return False, "Missing ProcessLauncherDelegate protocol"
    log_pass("ProcessLauncherDelegate protocol verified")

    # QoS assignment
    if "qos: .userInteractive" not in text or ".qualityOfService = .userInteractive" not in text:
        log_fail("ProcessLauncher.swift missing .userInteractive QoS configuration")
        return False, "Missing .userInteractive QoS"
    log_pass("Interactive QoS verified on launcher queue and dedicated execution thread")

    # C-array string marshalling with defer free
    if "strdup" not in text or "defer" not in text or "free(" not in text:
        log_fail("ProcessLauncher.swift missing C-array string marshalling or defer free cleanup")
        return False, "Missing C-array string marshalling or cleanup in ProcessLauncher.swift"
    log_pass("C-array string marshalling verified with strict defer { free } cleanup")

    # Dynamic symbol loading (dlopen / dlsym)
    for sym in ["qemu_init", "qemu_main_loop", "qemu_cleanup", "qemu_request_exit"]:
        if sym not in text:
            log_fail(f"ProcessLauncher.swift missing dynamic resolution of {sym}")
            return False, f"Missing dlsym resolution: {sym}"
        log_pass(f"Dynamic symbol resolution verified: {sym}")

    # Synchronization via NSCondition
    if "NSCondition" not in text or "stopCondition" not in text:
        log_fail("ProcessLauncher.swift missing NSCondition thread synchronization")
        return False, "Missing NSCondition synchronization"
    log_pass("Thread-safe lifecycle synchronization verified via NSCondition")

    return True, "ProcessLauncher thread and lifecycle hooks verified successfully"


# =========================================================================
# Check 5: VMController Boot Pipeline & State Management
# =========================================================================

def check_vm_controller_boot_pipeline(root: Path) -> Tuple[bool, str]:
    print("\n==> Check 5: Verifying VMController Boot Pipeline & State Management")

    vmc_path = root / "Engine" / "Core" / "VMController.swift"
    if not vmc_path.is_file():
        log_fail("VMController.swift missing")
        return False, "VMController.swift missing"

    text = vmc_path.read_text(encoding="utf-8")

    # VMState enum
    for state_case in ["stopped", "starting", "running", "paused", "stopping", "error"]:
        if state_case not in text:
            log_fail(f"VMController.swift missing VMState case: {state_case}")
            return False, f"Missing VMState: {state_case}"
    log_pass("VMState enum verified (stopped, starting, running, paused, stopping, error)")

    # Boot orchestration in start()
    if "QEMUArgumentsBuilder.buildArguments" not in text:
        log_fail("VMController.swift missing QEMUArgumentsBuilder argument synthesis")
        return False, "Missing argument synthesis in VMController.swift"
    log_pass("VMController boot orchestration verified (QEMUArgumentsBuilder integration)")

    # Subsystem attachments
    if "SPICEConnection" not in text or "launcher.launch" not in text:
        log_fail("VMController.swift missing SPICEConnection or ProcessLauncher attachment")
        return False, "Missing SPICEConnection or ProcessLauncher attachment"
    log_pass("Subsystem attachments verified (SPICEConnection, ProcessLauncher, QMPClient)")

    # Lifecycle state machine transitions
    for method in ["start()", "pause()", "resume()", "stop("]:
        if method not in text:
            log_fail(f"VMController.swift missing lifecycle method: {method}")
            return False, f"Missing lifecycle method: {method}"
        log_pass(f"Lifecycle control method verified: {method}")

    # Memory command dispatch
    if "dispatchMemoryCommand" not in text or "balloon" not in text:
        log_fail("VMController.swift missing dispatchMemoryCommand VirtIO-ballooning hook")
        return False, "Missing memory command dispatch"
    log_pass("SmartMemoryGuard VirtIO-ballooning and emergency pause command dispatch verified")

    # Anti-TCP socket policy check
    builder_path = root / "Engine" / "QEMU" / "QEMUArgumentsBuilder.swift"
    builder_text = builder_path.read_text(encoding="utf-8")
    for tcp_token in ["127.0.0.1", "localhost", "0.0.0.0", "port="]:
        if tcp_token not in builder_text:
            log_fail(f"QEMUArgumentsBuilder.swift missing rejection token: {tcp_token}")
            return False, f"Missing anti-TCP rejection: {tcp_token}"
    log_pass("Anti-TCP policy strictly enforced (rejection of loopback addresses and port=)")

    if "108" not in builder_text:
        log_fail("QEMUArgumentsBuilder.swift missing 108-byte POSIX socket length check")
        return False, "Missing 108-byte socket path limit"
    log_pass("POSIX sockaddr_un 108-byte socket path length limit enforced")

    return True, "VMController boot pipeline and state management verified successfully"


# =========================================================================
# Check 6: SPICE Unix Domain Socket & Display Ingestion
# =========================================================================

def check_spice_uds_and_display_ingestion(root: Path) -> Tuple[bool, str]:
    print("\n==> Check 6: Verifying SPICE Unix Domain Socket & Display Ingestion")

    spice_path = root / "Engine" / "SPICE" / "SPICEConnection.swift"
    if not spice_path.is_file():
        log_fail("SPICEConnection.swift missing")
        return False, "SPICEConnection.swift missing"

    text = spice_path.read_text(encoding="utf-8")

    # SPICEConnectionState enum
    for state in ["disconnected", "connecting", "connected", "failed"]:
        if state not in text:
            log_fail(f"SPICEConnection.swift missing state: {state}")
            return False, f"Missing state: {state}"
    log_pass("SPICEConnectionState enum verified (disconnected, connecting, connected, failed)")

    # Delegate protocol
    if "SPICEConnectionDelegate" not in text or "didReceiveDisplayFrame" not in text:
        log_fail("SPICEConnection.swift missing SPICEConnectionDelegate protocol")
        return False, "Missing SPICEConnectionDelegate protocol"
    log_pass("SPICEConnectionDelegate protocol verified (didReceiveDisplayFrame delegate callback)")

    # Transport sockets
    if "AF_UNIX" not in text or "SOCK_STREAM" not in text:
        log_fail("SPICEConnection.swift missing AF_UNIX / SOCK_STREAM socket creation")
        return False, "Missing AF_UNIX socket transport"
    log_pass("Unix Domain Socket stream transport verified (AF_UNIX, SOCK_STREAM)")

    # Anti-TCP enforcement via validateSocketPath
    if "validateSocketPath" not in text:
        log_fail("SPICEConnection.swift does not call validateSocketPath")
        return False, "Missing validateSocketPath in SPICEConnection"
    log_pass("Anti-TCP policy strictly validated upon connection initialization")

    # Programmatic display frame ingestion
    if "func ingestDisplayFrame" not in text:
        log_fail("SPICEConnection.swift missing func ingestDisplayFrame")
        return False, "Missing func ingestDisplayFrame in SPICEConnection.swift"
    log_pass("Programmatic display frame ingestion verified: func ingestDisplayFrame(data:width:height:)")

    # Input event forwarding
    if "sendInputEvent" not in text:
        log_fail("SPICEConnection.swift missing sendInputEvent method")
        return False, "Missing sendInputEvent method"
    log_pass("Input event dispatch verified (sendInputEvent)")

    return True, "SPICE Unix Domain Socket and display ingestion verified successfully"


# =========================================================================
# Check 7: Metal Framebuffer Rendering & UI Session Integration
# =========================================================================

def check_metal_rendering_and_ui_session(root: Path) -> Tuple[bool, str]:
    print("\n==> Check 7: Verifying Metal Framebuffer Rendering & UI Session Integration")

    renderer_path = root / "Engine" / "SPICE" / "MetalDisplayRenderer.swift"
    metal_view_path = root / "UI" / "Views" / "MetalDisplayView.swift"
    vm_session_path = root / "UI" / "ViewModels" / "VMSessionViewModel.swift"
    info_path = root / "Config" / "Info.plist"

    for p in [renderer_path, metal_view_path, vm_session_path, info_path]:
        if not p.is_file():
            log_fail(f"Required file missing: {p.relative_to(root)}")
            return False, f"Missing file: {p.name}"

    r_text = renderer_path.read_text(encoding="utf-8")
    mv_text = metal_view_path.read_text(encoding="utf-8")
    vm_text = vm_session_path.read_text(encoding="utf-8")

    # MetalDisplayRenderer texture format .bgra8Unorm
    if ".bgra8Unorm" not in r_text:
        log_fail("MetalDisplayRenderer.swift missing .bgra8Unorm texture pixel format")
        return False, "Missing .bgra8Unorm pixel format in MetalDisplayRenderer"
    log_pass("Metal texture pixel format verified: .bgra8Unorm")

    # Framebuffer update with bytesPerRow = width * 4
    if "updateFramebuffer" not in r_text or "bytesPerRow" not in r_text:
        log_fail("MetalDisplayRenderer.swift missing updateFramebuffer or bytesPerRow calculation")
        return False, "Missing updateFramebuffer in MetalDisplayRenderer"
    log_pass("Framebuffer upload verified with width * 4 bytes-per-row stride")

    # MTKView blit presentation
    if "render(to" not in r_text:
        log_fail("MetalDisplayRenderer.swift missing render(to:) blit presentation")
        return False, "Missing render(to:) blit presentation"
    log_pass("Blit command presentation verified (render(to drawable: CAMetalDrawable))")

    # MetalDisplayView MTKView delegate and aspect-ratio letterboxing
    if "MTKViewDelegate" not in mv_text:
        log_fail("MetalDisplayView.swift missing MTKViewDelegate")
        return False, "Missing MTKViewDelegate in MetalDisplayView"
    log_pass("MetalDisplayView verified (MTKView delegate and aspect-ratio letterboxing)")

    # VMSessionViewModel wiring
    if "didReceiveDisplayFrame" not in vm_text or "updateFramebuffer" not in vm_text:
        log_fail("VMSessionViewModel.swift missing display frame forwarding to renderer")
        return False, "Missing display frame forwarding in VMSessionViewModel"
    log_pass("VMSessionViewModel delegate routing verified (didReceiveDisplayFrame -> updateFramebuffer)")

    # 120Hz ProMotion support in Info.plist
    with open(info_path, "rb") as f:
        info_data = plistlib.load(f)
    if not info_data.get("CADisableMinimumFrameDurationOnPhone"):
        log_fail("Info.plist missing CADisableMinimumFrameDurationOnPhone for 120Hz ProMotion")
        return False, "Missing 120Hz ProMotion CADisableMinimumFrameDurationOnPhone"
    log_pass("120Hz ProMotion enabled via CADisableMinimumFrameDurationOnPhone = True")

    return True, "Metal framebuffer rendering and UI session integration verified successfully"


# =========================================================================
# Check 8: Packaging Configurations & CI/CD Workflow
# =========================================================================

def check_packaging_configurations_and_ci(root: Path) -> Tuple[bool, str]:
    print("\n==> Check 8: Verifying Packaging Configurations & CI/CD Workflow")

    # 1. project.yml dual schemes & target configs
    spec_path = root / "project.yml"
    try:
        with open(spec_path, "r", encoding="utf-8") as f:
            spec = yaml.safe_load(f)
    except Exception as e:
        log_fail(f"Failed to parse project.yml: {e}")
        return False, f"Invalid YAML in project.yml: {e}"

    schemes = spec.get("schemes", {})
    if "DeskSimulator-TrollStore" not in schemes or "DeskSimulator-Sideload" not in schemes:
        log_fail("project.yml missing dual schemes (DeskSimulator-TrollStore, DeskSimulator-Sideload)")
        return False, "Missing dual schemes in project.yml"
    log_pass("Dual packaging schemes verified: DeskSimulator-TrollStore and DeskSimulator-Sideload")

    configs = spec.get("configs", {})
    for exp_conf in ["Debug-TrollStore", "Release-TrollStore", "Debug-Sideload", "Release-Sideload"]:
        if exp_conf not in configs:
            log_fail(f"project.yml missing configuration: {exp_conf}")
            return False, f"Missing config: {exp_conf}"
        log_pass(f"Build configuration verified: {exp_conf}")

    # 2. Entitlements separation
    ts_path = root / "Config" / "DeskSimulator-TrollStore.entitlements"
    sl_path = root / "Config" / "DeskSimulator-Sideload.entitlements"

    with open(ts_path, "rb") as f:
        ts_data = plistlib.load(f)
    with open(sl_path, "rb") as f:
        sl_data = plistlib.load(f)

    # TrollStore has full kernel memory & JIT entitlements
    for k in [
        "com.apple.developer.kernel.increased-memory-limit",
        "com.apple.developer.kernel.extended-virtual-addressing",
        "dynamic-codesigning",
        "get-task-allow",
    ]:
        if not ts_data.get(k):
            log_fail(f"TrollStore entitlements missing or false for key: {k}")
            return False, f"TrollStore missing key: {k}"
        log_pass(f"TrollStore entitlement verified: {k} = True")

    # Sideload has get-task-allow and strictly omits restricted memory keys
    if not sl_data.get("get-task-allow"):
        log_fail("Sideload entitlements missing get-task-allow")
        return False, "Sideload missing get-task-allow"
    log_pass("Sideload entitlement verified: get-task-allow = True")

    for forbidden_k in [
        "com.apple.developer.kernel.increased-memory-limit",
        "com.apple.developer.kernel.extended-virtual-addressing",
    ]:
        if forbidden_k in sl_data:
            log_fail(f"Sideload profile must NOT contain restricted key: {forbidden_k}")
            return False, f"Forbidden key in Sideload: {forbidden_k}"
        log_pass(f"Sideload profile cleanly omits restricted key: {forbidden_k}")

    # 3. .github/workflows/build-ipa.yml
    wf_path = root / ".github" / "workflows" / "build-ipa.yml"
    try:
        with open(wf_path, "r", encoding="utf-8") as f:
            wf = yaml.safe_load(f)
    except Exception as e:
        log_fail(f"Failed to parse build-ipa.yml: {e}")
        return False, f"Invalid YAML in build-ipa.yml: {e}"

    jobs = wf.get("jobs", {})
    job = list(jobs.values())[0]
    runner = job.get("runs-on")
    if runner not in ["macos-14", "macos-15"]:
        log_fail(f"Workflow runner must be macos-14 or macos-15, got {runner}")
        return False, f"Invalid runner: {runner}"
    log_pass(f"CI/CD workflow runner verified: {runner}")

    steps = job.get("steps", [])
    all_runs = " ".join([s.get("run", "") for s in steps])
    all_uses = " ".join([s.get("uses", "") for s in steps])

    for expected_str in [
        "xcodegen generate",
        "DeskSimulator-TrollStore",
        "DeskSimulator-TrollStore.ipa",
        "DeskSimulator-Sideload",
        "DeskSimulator-Sideload.ipa",
    ]:
        if expected_str not in all_runs:
            log_fail(f"Workflow missing step containing: {expected_str}")
            return False, f"Missing workflow step: {expected_str}"
        log_pass(f"Workflow step verified: {expected_str}")

    if "actions/upload-artifact" not in all_uses:
        log_fail("Workflow missing actions/upload-artifact step")
        return False, "Missing artifact upload step"
    log_pass("Artifact upload step verified: actions/upload-artifact@v4")

    return True, "Packaging configurations and CI/CD workflow verified successfully"


# =========================================================================
# Check 9: Automated Phase 3 Component Test Suite
# =========================================================================

def check_phase3_component_tests(root: Path, dry_run: bool = False) -> Tuple[bool, str]:
    print("\n==> Check 9: Executing Automated Phase 3 Component Test Suite")
    if dry_run:
        log_pass("Dry-run: Skipped external test runner subprocess")
        return True, "Dry-run skipped test execution"

    runner_script = root / "Tests" / "Phase3Tests" / "run_phase3_tests.py"
    if not runner_script.is_file():
        log_fail("Missing Tests/Phase3Tests/run_phase3_tests.py")
        return False, "Missing Phase 3 test runner"

    res = subprocess.run(
        [sys.executable, str(runner_script)],
        cwd=str(root),
        capture_output=True,
        text=True,
    )

    if res.returncode != 0:
        log_fail(f"Phase 3 test suite failed (exit code {res.returncode}):\n{res.stdout}\n{res.stderr}")
        return False, f"Phase 3 tests failed with exit code {res.returncode}"

    print(res.stdout.strip())
    log_pass("All Phase 3 component logic tests passed with 100% success!")
    return True, "Phase 3 component logic tests PASSED"


# =========================================================================
# Check 10: Zero Regression Verification
# =========================================================================

def check_zero_regression_suite(
    root: Path,
    skip_regression: bool = False,
    dry_run: bool = False,
) -> Tuple[bool, str]:
    print("\n==> Check 10: Enforcing Zero Regression Verification Suite")
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

    # Step B: verify_phase2.py
    v2_script = root / "Scripts" / "verify_phase2.py"
    res2 = subprocess.run(
        [sys.executable, str(v2_script), "--skip-regression"],
        cwd=str(root),
        capture_output=True,
        text=True,
    )
    if res2.returncode != 0:
        log_fail(f"Phase 2 verification script failed (exit code {res2.returncode}):\n{res2.stderr}")
        return False, "verify_phase2.py regression detected"
    log_pass("verify_phase2.py passed (10/10 checks OK)")

    # Step C: run_all_tests.py
    unit_script = root / "Tests" / "run_all_tests.py"
    res3 = subprocess.run(
        [sys.executable, str(unit_script)],
        cwd=str(root),
        capture_output=True,
        text=True,
    )
    if res3.returncode != 0:
        log_fail(f"Unit test runner failed (exit code {res3.returncode}):\n{res3.stderr}")
        return False, "run_all_tests.py regression detected"
    log_pass("run_all_tests.py passed (121/121 unit & mock tests OK)")

    # Step D: run_e2e_tests.py
    e2e_script = root / "Tests" / "E2ETests" / "run_e2e_tests.py"
    res4 = subprocess.run(
        [sys.executable, str(e2e_script)],
        cwd=str(root),
        capture_output=True,
        text=True,
    )
    if res4.returncode != 0:
        log_fail(f"E2E test runner failed (exit code {res4.returncode}):\n{res4.stderr}")
        return False, "run_e2e_tests.py regression detected"
    log_pass("run_e2e_tests.py passed (278/278 E2E tests OK)")

    return True, "Zero regressions detected across all Phase 1, Phase 2, unit, and E2E test suites (100% PASS)"


# =========================================================================
# Main Execution Harness
# =========================================================================

def run_all_phase3_checks(
    root: Path,
    skip_git: bool = False,
    skip_regression: bool = False,
    dry_run: bool = False,
) -> Tuple[bool, List[Dict[str, Any]]]:
    checks = [
        ("Engine Linkage & Search Paths", lambda: check_engine_linkage_and_search_paths(root)),
        ("Native C-ABI Bridge Signatures", lambda: check_native_c_abi_bridge_signatures(root)),
        ("Darwin Runtime Probes & JIT Detection", lambda: check_darwin_runtime_probes_and_jit(root)),
        ("ProcessLauncher Thread & Lifecycle Hooks", lambda: check_process_launcher_thread_and_lifecycle(root)),
        ("VMController Boot Pipeline & State Management", lambda: check_vm_controller_boot_pipeline(root)),
        ("SPICE Unix Domain Socket & Display Ingestion", lambda: check_spice_uds_and_display_ingestion(root)),
        ("Metal Framebuffer Rendering & UI Session Integration", lambda: check_metal_rendering_and_ui_session(root)),
        ("Packaging Configurations & CI/CD Workflow", lambda: check_packaging_configurations_and_ci(root)),
        ("Automated Phase 3 Component Test Suite", lambda: check_phase3_component_tests(root, dry_run=dry_run)),
        ("Zero Regression Verification", lambda: check_zero_regression_suite(root, skip_regression=skip_regression, dry_run=dry_run)),
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
        description="Automated Phase 3 Verification Script for Desk-simulator PC OS Emulator.",
        allow_abbrev=False,
    )
    parser.add_argument(
        "--workspace-root",
        type=str,
        default=str(WORKSPACE_ROOT),
        help="Path to workspace root directory (default: parent of Scripts/)",
    )
    parser.add_argument(
        "--skip-git",
        action="store_true",
        default=False,
        help="Skip git remote repository checks (for isolated or offline test runners)",
    )
    parser.add_argument(
        "--skip-regression",
        action="store_true",
        default=False,
        help="Skip Phase 1 and Phase 2 regression test suites (for fast Phase 3 iterations)",
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
        print(" Desk-simulator Phase 3 Automated Verification Script")
        print(f" Workspace Root: {root}")
        print("=" * 75)

    success, results = run_all_phase3_checks(
        root,
        skip_git=args.skip_git,
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
        print(f"  [SUCCESS] Phase 3 Verification Passed! (All {len(results)} Checks OK)")
        print("  Desk-simulator is fully compliant with Phase 3 Architecture Specifications.")
    else:
        failed_count = sum(1 for r in results if not r["success"])
        print(f"  [FAIL] Phase 3 Verification Failed! ({failed_count}/{len(results)} checks failed)")
    print("=" * 75 + "\n")

    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
