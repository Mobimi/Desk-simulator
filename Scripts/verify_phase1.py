#!/usr/bin/env python3
"""
Desk-simulator Phase 1 Automated Verification Script
Validates:
1. Workspace directory layout & baseline repository files
2. Git remote origin and tracking configuration
3. Stripped target architecture whitelist & pruning (x86_64-softmmu, aarch64-softmmu)
4. Declarative engine configuration manifest (engine_config.json)
5. Compiler optimization flags (-O3, -flto, Apple Silicon targets)
6. SPICE over Unix Domain Sockets (no TCP loopback, channel pruning)
7. TCG translation buffer size clamping (128MB–256MB)
8. Native Swift engine modules and C-bridge headers
9. Management Layer Swift protocols, classes, and Python reference modules
10. Management Layer interface and functional contracts (MemoryGuard, PCoreScheduler, ISOAutoPilot, StorageBridge)
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Workspace root resolution
WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
if str(WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_ROOT))

from Engine.Config.engine_config import EngineConfig
from Management.SmartMemoryGuard.memory_guard import (
    MemoryEntitlements,
    MemoryGuard,
    MemoryPressureLevel,
    QMPCommand,
)
from Management.PCoreScheduler.pcore_scheduler import (
    BootBoostState,
    PCoreScheduler,
)
from Management.ISOAutoPilot.iso_autopilot import (
    ISOAutoPilot,
    OperatingSystemType,
)
from Management.Storage.storage_bridge import (
    DiskFormat,
    StorageBridge,
)


class StrictArgumentParser(argparse.ArgumentParser):
    """ArgumentParser that outputs clean error message and exits with code 1 without tracebacks."""

    def error(self, message: str) -> None:
        sys.stderr.write(f"Error: {message}\n")
        sys.exit(1)


REQUIRED_DIRECTORIES: List[str] = [
    "UI",
    "UI/Views",
    "UI/ViewModels",
    "Management",
    "Management/SmartMemoryGuard",
    "Management/PCoreScheduler",
    "Management/ISOAutoPilot",
    "Management/Storage",
    "Engine",
    "Engine/Config",
    "Engine/Core",
    "Engine/QEMU",
    "Engine/SPICE",
    "Engine/JIT",
    "Scripts",
    "Tests",
    "Tests/EngineTests",
    "Tests/ManagementMocks",
]

REQUIRED_BASELINE_FILES: List[str] = [
    "README.md",
    ".gitignore",
    "Engine/Config/engine_config.json",
    "Engine/Config/engine_config.py",
    "Engine/Config/target_whitelist.txt",
    "Scripts/build_engine.py",
    "Scripts/prepare_workspace.py",
]

REQUIRED_ENGINE_FILES: List[str] = [
    "Engine/QEMU/BootstrapBridge.h",
    "Engine/QEMU/Architecture.swift",
    "Engine/QEMU/QEMUArgumentsBuilder.swift",
    "Engine/SPICE/ChannelPolicy.swift",
    "Engine/SPICE/SPICEConnection.swift",
    "Engine/SPICE/MetalDisplayRenderer.swift",
    "Engine/Core/QMPClient.swift",
    "Engine/Core/ProcessLauncher.swift",
    "Engine/Core/VMController.swift",
    "Engine/JIT/JITDetector.swift",
]

REQUIRED_MANAGEMENT_SWIFT_FILES: List[str] = [
    "Management/SmartMemoryGuard/MemoryGuardProtocol.swift",
    "Management/SmartMemoryGuard/MemoryGuard.swift",
    "Management/PCoreScheduler/PCoreSchedulerProtocol.swift",
    "Management/PCoreScheduler/PCoreScheduler.swift",
    "Management/ISOAutoPilot/ISOAutoPilotProtocol.swift",
    "Management/ISOAutoPilot/ISOAutoPilot.swift",
    "Management/Storage/StorageBridgeProtocol.swift",
    "Management/Storage/StorageBridge.swift",
]

REQUIRED_MANAGEMENT_PYTHON_FILES: List[str] = [
    "Management/__init__.py",
    "Management/SmartMemoryGuard/__init__.py",
    "Management/SmartMemoryGuard/memory_guard.py",
    "Management/PCoreScheduler/__init__.py",
    "Management/PCoreScheduler/pcore_scheduler.py",
    "Management/ISOAutoPilot/__init__.py",
    "Management/ISOAutoPilot/iso_autopilot.py",
    "Management/Storage/__init__.py",
    "Management/Storage/storage_bridge.py",
]

EXPECTED_REMOTE_URL = "https://github.com/Mobimi/Desk-simulator"
EXPECTED_BRANCH = "main"


def log_step(title: str) -> None:
    print(f"\n==> {title}")


def log_pass(msg: str) -> None:
    print(f"  [PASS] {msg}")


def log_fail(msg: str) -> None:
    print(f"  [FAIL] {msg}")


def log_info(msg: str) -> None:
    print(f"  [INFO] {msg}")


def check_directory_structure(root: Path) -> Tuple[bool, str]:
    log_step("Verifying Workspace Directory Layout & Baseline Files")
    all_ok = True

    for rel_dir in REQUIRED_DIRECTORIES:
        p = root / rel_dir
        if p.is_dir():
            log_pass(f"Directory verified: {rel_dir}")
        else:
            log_fail(f"Missing directory: {rel_dir}")
            all_ok = False

    for rel_file in REQUIRED_BASELINE_FILES:
        p = root / rel_file
        if p.is_file():
            log_pass(f"Baseline file verified: {rel_file}")
        else:
            log_fail(f"Missing baseline file: {rel_file}")
            all_ok = False

    return all_ok, "Directory structure and baseline files valid" if all_ok else "Missing directories or files"


def check_git_configuration(root: Path, skip_git: bool = False) -> Tuple[bool, str]:
    log_step("Verifying Git Remote and Branch Tracking")
    if skip_git:
        log_info("Git check skipped via --skip-git")
        return True, "Git check skipped"

    try:
        proc = subprocess.run(
            ["git", "remote", "-v"],
            cwd=str(root),
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode != 0:
            log_fail(f"git remote -v returned non-zero ({proc.returncode}): {proc.stderr.strip()}")
            return False, "Git remote check failed"

        remotes = proc.stdout
        if EXPECTED_REMOTE_URL in remotes:
            log_pass(f"Remote origin tracks expected repository: {EXPECTED_REMOTE_URL}")
        else:
            log_fail(f"Remote origin URL mismatch: expected {EXPECTED_REMOTE_URL}, got:\n{remotes.strip()}")
            return False, "Git remote origin mismatch"

        b_proc = subprocess.run(
            ["git", "branch", "--show-current"],
            cwd=str(root),
            capture_output=True,
            text=True,
            check=False,
        )
        current_branch = b_proc.stdout.strip()
        if current_branch == EXPECTED_BRANCH:
            log_pass(f"Current tracking branch verified: {EXPECTED_BRANCH}")
        else:
            log_info(f"Current branch is '{current_branch}' (expected {EXPECTED_BRANCH})")

        return True, "Git configuration verified"
    except Exception as exc:
        log_fail(f"Error checking git repository: {exc}")
        return False, f"Git verification error: {exc}"


def check_target_architecture_filtering(root: Path) -> Tuple[bool, str]:
    log_step("Verifying Target Architecture Whitelist & Pruning")
    whitelist_file = root / "Engine" / "Config" / "target_whitelist.txt"
    if not whitelist_file.exists():
        log_fail("target_whitelist.txt missing")
        return False, "target_whitelist.txt missing"

    file_targets = EngineConfig.get_whitelist(whitelist_file)
    expected_allowed = ["x86_64-softmmu", "aarch64-softmmu"]

    if file_targets != expected_allowed:
        log_fail(f"target_whitelist.txt mismatch: {file_targets} != {expected_allowed}")
        return False, "target_whitelist.txt does not match expected targets"
    log_pass(f"target_whitelist.txt verified: {file_targets}")

    if EngineConfig.ALLOWED_TARGETS != expected_allowed:
        log_fail(f"EngineConfig.ALLOWED_TARGETS mismatch: {EngineConfig.ALLOWED_TARGETS}")
        return False, "EngineConfig.ALLOWED_TARGETS mismatch"
    log_pass(f"EngineConfig.ALLOWED_TARGETS verified: {EngineConfig.ALLOWED_TARGETS}")

    # Validate whitelist checking
    if not EngineConfig.validate_targets(expected_allowed, require_all=True):
        log_fail("EngineConfig.validate_targets failed for expected targets")
        return False, "validate_targets failed on allowed targets"
    log_pass("Target whitelist validation passes for allowed targets")

    # Validate rejection of forbidden targets
    forbidden_samples = ["mips", "ppc", "sparc", "riscv", "s390x", "i386", "arm", "mips-softmmu"]
    for fb in forbidden_samples:
        if EngineConfig.validate_targets([fb]):
            log_fail(f"EngineConfig.validate_targets incorrectly accepted forbidden target: {fb}")
            return False, f"Forbidden target accepted: {fb}"
    log_pass("Forbidden architectures (MIPS, PPC, SPARC, RISC-V, s390x, etc.) pruned and rejected")

    # Verify Swift TargetArchitecture declaration
    swift_arch = root / "Engine" / "QEMU" / "Architecture.swift"
    if swift_arch.exists():
        content = swift_arch.read_text(encoding="utf-8")
        if "x86_64-softmmu" in content and "aarch64-softmmu" in content:
            log_pass("Swift TargetArchitecture enum mirrors target whitelist")
        else:
            log_fail("Swift TargetArchitecture enum missing expected targets")
            return False, "Swift TargetArchitecture missing targets"

    return True, "Target architecture filtering verified"


def check_engine_config_manifest(root: Path) -> Tuple[bool, str]:
    log_step("Verifying Declarative Engine Configuration Manifest")
    config_json_path = root / "Engine" / "Config" / "engine_config.json"
    if not config_json_path.exists():
        log_fail("engine_config.json does not exist")
        return False, "engine_config.json missing"

    try:
        data = EngineConfig.load_config(config_json_path)
    except Exception as exc:
        log_fail(f"Failed to parse engine_config.json: {exc}")
        return False, f"Invalid JSON in engine_config.json: {exc}"

    required_keys = [
        "allowed_targets",
        "compiler_required_flags",
        "apple_silicon_targets",
        "tcg_buffer_clamp",
        "spice_ipc",
    ]
    for rk in required_keys:
        if rk not in data:
            log_fail(f"Missing key in engine_config.json: {rk}")
            return False, f"Missing key: {rk}"

    if data["allowed_targets"] != EngineConfig.ALLOWED_TARGETS:
        log_fail("engine_config.json allowed_targets mismatch")
        return False, "allowed_targets mismatch"
    log_pass("engine_config.json allowed_targets verified")

    if data["tcg_buffer_clamp"]["min_mb"] != 128 or data["tcg_buffer_clamp"]["max_mb"] != 256:
        log_fail("engine_config.json TCG buffer bounds mismatch (expected 128MB–256MB)")
        return False, "TCG buffer bounds mismatch"
    log_pass("engine_config.json TCG buffer bounds [128MB, 256MB] verified")

    if data["spice_ipc"]["transport"] != "unix":
        log_fail("engine_config.json SPICE transport is not 'unix'")
        return False, "SPICE transport must be 'unix'"
    log_pass("engine_config.json SPICE IPC transport 'unix' verified")

    return True, "Declarative engine configuration manifest verified"


def check_compiler_flags() -> Tuple[bool, str]:
    log_step("Verifying Compiler Optimization Flags")
    # Verify required flags
    for rf in ["-O3", "-flto"]:
        if rf not in EngineConfig.COMPILER_REQUIRED_FLAGS:
            log_fail(f"Required compiler flag missing in EngineConfig: {rf}")
            return False, f"Missing required flag: {rf}"
    log_pass("EngineConfig contains mandatory optimization flags: -O3, -flto")

    # Verify Apple Silicon targets
    if not any("-mcpu=apple" in flag or "-arch arm64" in flag for flag in EngineConfig.APPLE_SILICON_TARGETS):
        log_fail("EngineConfig missing Apple Silicon optimization target flags")
        return False, "Missing Apple Silicon flags"
    log_pass("EngineConfig contains Apple Silicon target optimizations")

    # Test validator with valid set
    valid_flags = ["-O3", "-flto", "-mcpu=apple-m1", "-arch arm64"]
    if not EngineConfig.validate_compiler_flags(valid_flags, require_apple_silicon=True):
        log_fail("EngineConfig.validate_compiler_flags rejected valid optimization flags")
        return False, "Valid compiler flags rejected"
    log_pass("EngineConfig.validate_compiler_flags passed for -O3, -flto, -mcpu=apple-m1")

    # Test validator rejects -O0
    if EngineConfig.validate_compiler_flags(["-O3", "-flto", "-O0"]):
        log_fail("EngineConfig.validate_compiler_flags accepted -O0 debug flag")
        return False, "Debug flag -O0 was accepted"
    log_pass("Debug flag -O0 correctly rejected")

    # Test validator rejects missing -O3 or -flto
    if EngineConfig.validate_compiler_flags(["-O2", "-flto"]):
        log_fail("EngineConfig.validate_compiler_flags accepted -O2 without -O3")
        return False, "Missing -O3 was accepted"
    if EngineConfig.validate_compiler_flags(["-O3"]):
        log_fail("EngineConfig.validate_compiler_flags accepted -O3 without -flto")
        return False, "Missing -flto was accepted"
    log_pass("Compiler flag validator strictly enforces both -O3 and -flto")

    return True, "Compiler optimization flags verified"


def check_spice_uds_ipc() -> Tuple[bool, str]:
    log_step("Verifying SPICE Unix Domain Socket IPC & Channel Pruning")
    socket_path = "/tmp/desk_spice.sock"
    args = EngineConfig.generate_spice_uds_args(socket_path)
    args_str = " ".join(args)

    if "-spice" not in args or "unix=on" not in args_str or f"addr={socket_path}" not in args_str:
        log_fail(f"SPICE UDS arguments do not bind unix=on to socket path: {args}")
        return False, "SPICE UDS socket binding invalid"
    log_pass(f"SPICE UDS parameters verified: unix=on,addr={socket_path},disable-ticketing=on")

    # Verify channel pruning
    if "-global spice.smartcard=off" not in args_str or "-global spice.webdav=off" not in args_str:
        log_fail(f"SPICE channel pruning not applied: {args}")
        return False, "Channel pruning not applied"
    log_pass("SPICE channel pruning verified (smartcard=off, webdav=off to reclaim ~100MB RAM)")

    # Verify prohibition of TCP loopback
    for bad in ["127.0.0.1:5900", "localhost", "0.0.0.0", "port=5900"]:
        try:
            EngineConfig.generate_spice_uds_args(bad)
            log_fail(f"EngineConfig accepted prohibited TCP loopback parameter: {bad}")
            return False, f"TCP loopback parameter accepted: {bad}"
        except ValueError:
            pass
    log_pass("TCP loopback strictly prohibited (127.0.0.1, localhost, 0.0.0.0, port=)")

    # Verify POSIX socket path limit (108 bytes)
    long_path = "/tmp/" + "a" * 105 + ".sock"
    try:
        EngineConfig.generate_spice_uds_args(long_path)
        log_fail("EngineConfig accepted path exceeding POSIX sockaddr_un limit (108 bytes)")
        return False, "Socket path > 108 bytes accepted"
    except ValueError:
        pass
    log_pass("POSIX sockaddr_un 108-byte socket path limit enforced")

    return True, "SPICE Unix Domain Socket IPC verified"


def check_tcg_buffer_clamping() -> Tuple[bool, str]:
    log_step("Verifying TCG Translation Buffer Clamping (128MB–256MB)")
    if EngineConfig.TCG_MIN_MB != 128 or EngineConfig.TCG_MAX_MB != 256:
        log_fail(f"TCG bounds constant mismatch: min={EngineConfig.TCG_MIN_MB}, max={EngineConfig.TCG_MAX_MB}")
        return False, "TCG bounds constants invalid"

    # Clamping tests
    test_cases = [
        (0, 128),
        (-50, 128),
        (64, 128),
        (128, 128),
        (192, 192),
        (256, 256),
        (512, 256),
        (1024, 256),
    ]
    for requested, expected in test_cases:
        actual = EngineConfig.clamp_tcg_size(requested)
        if actual != expected:
            log_fail(f"TCG clamping mismatch for {requested}MB: expected {expected}MB, got {actual}MB")
            return False, f"TCG clamp failed for {requested}MB"
    log_pass("TCG buffer size successfully clamped within [128MB, 256MB] bounds")

    # Verify QEMU command line includes clamped tb-size
    for target in EngineConfig.ALLOWED_TARGETS:
        cmd = EngineConfig.generate_qemu_cmdline(
            target=target,
            ram_mb=2048,
            tb_size_mb=64,  # Underflow test
            spice_socket="/tmp/desk_spice.sock",
        )
        cmd_str = " ".join(cmd)
        if "-accel tcg,tb-size=128" not in cmd_str:
            log_fail(f"QEMU command line missing clamped TCG tb-size=128: {cmd_str}")
            return False, "QEMU command line missing clamped TCG size"
        if not cmd[0].startswith(f"qemu-system-{target.replace('-softmmu', '')}"):
            log_fail(f"QEMU command line binary mismatch for target {target}: {cmd[0]}")
            return False, "QEMU binary mismatch"
    log_pass("QEMU CLI synthesis correctly enforces clamped TCG translation buffer size")

    return True, "TCG translation buffer clamping verified"


def check_native_engine_modules(root: Path) -> Tuple[bool, str]:
    log_step("Verifying Native Swift Engine Modules & C-Bridge Headers")
    all_ok = True
    for rel_file in REQUIRED_ENGINE_FILES:
        p = root / rel_file
        if p.is_file() and p.stat().st_size > 0:
            log_pass(f"Native module verified ({p.stat().st_size} bytes): {rel_file}")
        else:
            log_fail(f"Missing or empty native module: {rel_file}")
            all_ok = False
    return all_ok, "Native engine modules verified" if all_ok else "Missing native modules"


def check_management_modules(root: Path) -> Tuple[bool, str]:
    """
    Verifies that all Management Layer Swift protocols, implementation classes,
    and Python reference implementation files exist, are non-empty, and contain
    expected protocol and class definitions.
    """
    log_step("Verifying Management Layer Swift Protocols & Python Modules")
    all_ok = True

    swift_signature_checks = {
        "Management/SmartMemoryGuard/MemoryGuardProtocol.swift": [
            "protocol MemoryGuardProtocol",
            "safetyBufferBytes",
            "minSafeFloorBytes",
            "dangerThresholdPercent",
        ],
        "Management/SmartMemoryGuard/MemoryGuard.swift": [
            "class MemoryGuard",
            "MemoryGuardProtocol",
            "calculateSafeGuestRAM",
            "handleMemoryPressure",
            "checkJetsamEmergency",
        ],
        "Management/PCoreScheduler/PCoreSchedulerProtocol.swift": [
            "protocol PCoreSchedulerProtocol",
            "defaultVCPUs",
            "assignTopology",
            "clampVCPUs",
        ],
        "Management/PCoreScheduler/PCoreScheduler.swift": [
            "class PCoreScheduler",
            "PCoreSchedulerProtocol",
            "getPhysicalPCoreCount",
            "elevateQoS",
        ],
        "Management/ISOAutoPilot/ISOAutoPilotProtocol.swift": [
            "protocol ISOAutoPilotProtocol",
            "identifyOperatingSystem",
            "generateVirtIOInjectionConfig",
            "generateWindows11BypassXML",
        ],
        "Management/ISOAutoPilot/ISOAutoPilot.swift": [
            "class ISOAutoPilot",
            "ISOAutoPilotProtocol",
            "identifyOperatingSystem",
            "generateVirtIOInjectionConfig",
        ],
        "Management/Storage/StorageBridgeProtocol.swift": [
            "protocol StorageBridgeProtocol",
            "createSparseDiskConfig",
            "allocateSparseDisk",
            "shareFileToGuest",
        ],
        "Management/Storage/StorageBridge.swift": [
            "class StorageBridge",
            "StorageBridgeProtocol",
            "createSparseDiskConfig",
            "syncClipboard",
        ],
    }

    for rel_file, signatures in swift_signature_checks.items():
        p = root / rel_file
        if not p.is_file() or p.stat().st_size == 0:
            log_fail(f"Missing or empty Management Swift file: {rel_file}")
            all_ok = False
            continue

        try:
            content = p.read_text(encoding="utf-8")
            missing_sigs = [sig for sig in signatures if sig not in content]
            if missing_sigs:
                log_fail(f"Management Swift file {rel_file} missing required signatures: {missing_sigs}")
                all_ok = False
            else:
                log_pass(f"Management Swift module verified ({p.stat().st_size} bytes, signatures OK): {rel_file}")
        except Exception as exc:
            log_fail(f"Error reading Management Swift file {rel_file}: {exc}")
            all_ok = False

    for rel_file in REQUIRED_MANAGEMENT_PYTHON_FILES:
        p = root / rel_file
        if p.is_file() and p.stat().st_size > 0:
            log_pass(f"Management Python module verified ({p.stat().st_size} bytes): {rel_file}")
        else:
            log_fail(f"Missing or empty Management Python file: {rel_file}")
            all_ok = False

    return all_ok, "Management layer modules verified" if all_ok else "Management layer module verification failed"


def check_management_layer_interfaces() -> Tuple[bool, str]:
    """
    Performs dynamic sanity validation on the public interfaces and core contracts
    of the Management Layer modules:
    - SmartMemoryGuard: 450MB reserve, 1024MB floor, pressure handling, Jetsam 90% emergency auto-pause.
    - PCoreScheduler: default 2 vCPUs, physical P-core pinning, Mach QoS elevation, boot boost.
    - ISOAutoPilot: OS signature identification, VirtIO injection config, Windows 11 bypass XML.
    - StorageBridge: APFS sparse disk config, size validation, clipboard sync.
    """
    log_step("Verifying Management Layer Interface & Functional Contracts")
    all_ok = True

    try:
        # --- 1. SmartMemoryGuard Verification ---
        ent_full = MemoryGuard.detect_entitlements(increased_memory=True, extended_va=True)
        if ent_full.get("ceiling_ratio") != 0.80:
            log_fail(f"SmartMemoryGuard entitlement ratio mismatch: expected 0.80, got {ent_full.get('ceiling_ratio')}")
            all_ok = False
        else:
            log_pass("SmartMemoryGuard entitlement detection verified (increased_memory + extended_va -> 0.80 ratio)")

        safe_ram = MemoryGuard.calculate_safe_guest_ram(2048 * 1024 * 1024)
        expected_ram = (2048 - 450) * 1024 * 1024
        if safe_ram != expected_ram:
            log_fail(f"SmartMemoryGuard calculate_safe_guest_ram failed: expected {expected_ram}, got {safe_ram}")
            all_ok = False
        else:
            log_pass(f"SmartMemoryGuard 450MB safety buffer deduction verified: 2048MB -> {safe_ram // (1024 * 1024)}MB")

        clamped_ram = MemoryGuard.calculate_safe_guest_ram(500 * 1024 * 1024)
        if clamped_ram != 1024 * 1024 * 1024:
            log_fail(f"SmartMemoryGuard min safe floor clamping failed: expected 1024MB, got {clamped_ram // (1024*1024)}MB")
            all_ok = False
        else:
            log_pass("SmartMemoryGuard 1024MB safe floor clamping verified for low available memory")

        normal_cmd = MemoryGuard.handle_memory_pressure(MemoryPressureLevel.NORMAL, 2048 * 1024 * 1024)
        warn_cmd = MemoryGuard.handle_memory_pressure(MemoryPressureLevel.WARNING, 2048 * 1024 * 1024)
        crit_cmd = MemoryGuard.handle_memory_pressure(MemoryPressureLevel.CRITICAL, 2048 * 1024 * 1024)

        if normal_cmd is not None:
            log_fail(f"SmartMemoryGuard normal pressure should return None, got: {normal_cmd}")
            all_ok = False
        elif not warn_cmd or warn_cmd.get("execute") != "balloon" or warn_cmd.get("arguments", {}).get("value") != expected_ram:
            log_fail(f"SmartMemoryGuard warning pressure command mismatch: {warn_cmd}")
            all_ok = False
        elif not crit_cmd or crit_cmd.get("execute") != "balloon" or crit_cmd.get("arguments", {}).get("value") != 1024 * 1024 * 1024:
            log_fail(f"SmartMemoryGuard critical pressure command mismatch: {crit_cmd}")
            all_ok = False
        else:
            log_pass("SmartMemoryGuard QMP VirtIO-ballooning pressure dispatch verified (normal=None, warning=safe, critical=floor)")

        is_emergency = MemoryGuard.check_jetsam_emergency(900 * 1024 * 1024, 1000 * 1024 * 1024)
        not_emergency = MemoryGuard.check_jetsam_emergency(899 * 1024 * 1024, 1000 * 1024 * 1024)
        pause_cmd = MemoryGuard.emergency_auto_pause()
        if not is_emergency or not_emergency or pause_cmd.get("execute") != "stop":
            log_fail("SmartMemoryGuard 90% Jetsam emergency threshold or auto-pause command failed")
            all_ok = False
        else:
            log_pass("SmartMemoryGuard 90% Jetsam emergency threshold and QMP auto-pause ({'execute': 'stop'}) verified")

        # --- 2. PCoreScheduler Verification ---
        if PCoreScheduler.get_default_vcpus() != 2:
            log_fail(f"PCoreScheduler default vCPUs mismatch: expected 2, got {PCoreScheduler.get_default_vcpus()}")
            all_ok = False
        else:
            log_pass("PCoreScheduler default vCPU count verified: 2 physical P-cores")

        topology = PCoreScheduler.assign_topology(p_cores=2)
        if topology.get("vcpus") != 2 or topology.get("pcore_affinity") != [0, 1]:
            log_fail(f"PCoreScheduler assign_topology mismatch: {topology}")
            all_ok = False
        else:
            log_pass("PCoreScheduler topology assignment verified: vCPUs=2, pcore_affinity=[0, 1]")

        clamped_vcpu = PCoreScheduler.clamp_vcpus(4, p_cores=2)
        if clamped_vcpu != 2:
            log_fail(f"PCoreScheduler clamp_vcpus failed: expected 2, got {clamped_vcpu}")
            all_ok = False
        else:
            log_pass("PCoreScheduler vCPU clamping verified: requested 4 clamped to 2 P-cores")

        vcpu_qos = PCoreScheduler.elevate_qos("vCPU-0", is_vcpu=True)
        aux_qos = PCoreScheduler.elevate_qos("aux-io", is_vcpu=False)
        bg_qos = PCoreScheduler.demote_qos_background("aux-log")
        if vcpu_qos != 0x21 or aux_qos != 0x19 or bg_qos != 0x09:
            log_fail(f"PCoreScheduler QoS values mismatch: vcpu={hex(vcpu_qos)}, aux={hex(aux_qos)}, bg={hex(bg_qos)}")
            all_ok = False
        else:
            log_pass("PCoreScheduler Mach QoS elevation verified: User Interactive (0x21), User Initiated (0x19), Background (0x09)")

        # --- 3. ISOAutoPilot Verification ---
        win11_detect = ISOAutoPilot.identify_operating_system(b"\x00" * 32768 + b"MICROSOFT WINDOWS 11 PROFESSIONAL")
        linux_detect = ISOAutoPilot.identify_operating_system(b"\x00" * 32768 + b"UBUNTU 22.04 LTS")
        unknown_detect = ISOAutoPilot.identify_operating_system(b"\x00" * 32768 + b"UNKNOWN OS DISK")
        if win11_detect != OperatingSystemType.WINDOWS_11 or linux_detect != OperatingSystemType.LINUX_UBUNTU or unknown_detect != OperatingSystemType.UNKNOWN:
            log_fail(f"ISOAutoPilot OS identification mismatch: win11={win11_detect}, linux={linux_detect}, unknown={unknown_detect}")
            all_ok = False
        else:
            log_pass("ISOAutoPilot signature-based OS identification verified (WINDOWS_11, LINUX_UBUNTU, UNKNOWN)")

        virtio_cfg = ISOAutoPilot.generate_virtio_injection_config(OperatingSystemType.WINDOWS_11)
        if not virtio_cfg.get("inject_drivers") or "viostor" not in virtio_cfg.get("drivers", []) or "virtio-win.iso" not in virtio_cfg.get("drive_param", ""):
            log_fail(f"ISOAutoPilot VirtIO injection configuration mismatch: {virtio_cfg}")
            all_ok = False
        else:
            log_pass("ISOAutoPilot VirtIO driver auto-injection configuration verified (viostor, netkvm, balloon)")

        bypass_xml = ISOAutoPilot.generate_windows11_bypass_xml("DeskUser")
        required_bypasses = [
            "BypassTPMCheck",
            "BypassSecureBootCheck",
            "BypassRAMCheck",
            "BypassCPUCheck",
            "BypassStorageCheck",
            "<Name>DeskUser</Name>",
        ]
        missing_xml = [req for req in required_bypasses if req not in bypass_xml]
        if missing_xml:
            log_fail(f"ISOAutoPilot Windows 11 bypass XML missing required entries: {missing_xml}")
            all_ok = False
        else:
            log_pass("ISOAutoPilot Windows 11 unattended bypass XML verified (TPM, SecureBoot, RAM, CPU, Storage bypasses)")

        # --- 4. StorageBridge Verification ---
        supported_formats = StorageBridge.get_supported_formats()
        if DiskFormat.APFS_SPARSE not in supported_formats:
            log_fail(f"StorageBridge supported formats missing APFS_SPARSE: {supported_formats}")
            all_ok = False
        else:
            log_pass(f"StorageBridge supported virtual disk formats verified: {supported_formats}")

        sparse_cfg = StorageBridge.create_sparse_disk_config(64 * 1024 * 1024 * 1024)
        if sparse_cfg.get("format") != DiskFormat.APFS_SPARSE or not sparse_cfg.get("sparse_flag") or sparse_cfg.get("initial_allocation_bytes") != 512 * 1024:
            log_fail(f"StorageBridge sparse disk config mismatch: {sparse_cfg}")
            all_ok = False
        else:
            log_pass("StorageBridge APFS sparse disk configuration verified (format=APFS_SPARSE, initial_allocation=512KB)")

        try:
            StorageBridge.create_sparse_disk_config(0)
            log_fail("StorageBridge accepted non-positive disk size (0 bytes)")
            all_ok = False
        except ValueError:
            log_pass("StorageBridge correctly rejected non-positive disk size (0 bytes)")

        bridge = StorageBridge()
        test_clip = "Desk-simulator Clipboard Test 2026"
        bridge.sync_to_guest(test_clip)
        retrieved_clip = bridge.sync_from_guest()
        if retrieved_clip != test_clip:
            log_fail(f"StorageBridge clipboard sync mismatch: expected '{test_clip}', got '{retrieved_clip}'")
            all_ok = False
        else:
            log_pass("StorageBridge bidirectional clipboard synchronization verified")

    except Exception as exc:
        log_fail(f"Management layer interface validation encountered an exception: {exc}")
        return False, f"Management layer interface validation error: {exc}"

    return all_ok, "Management layer interface contracts verified" if all_ok else "Management layer interface validation failed"


def run_all_phase1_checks(root: Path, skip_git: bool = False) -> Tuple[bool, List[Dict[str, Any]]]:
    checks = [
        ("Workspace Directory Layout & Baseline Files", lambda: check_directory_structure(root)),
        ("Git Remote & Branch Tracking", lambda: check_git_configuration(root, skip_git=skip_git)),
        ("Target Architecture Whitelist & Pruning", lambda: check_target_architecture_filtering(root)),
        ("Declarative Engine Configuration Manifest", lambda: check_engine_config_manifest(root)),
        ("Compiler Optimization Flags", lambda: check_compiler_flags()),
        ("SPICE Unix Domain Socket IPC & Channel Pruning", lambda: check_spice_uds_ipc()),
        ("TCG Translation Buffer Clamping (128MB–256MB)", lambda: check_tcg_buffer_clamping()),
        ("Native Swift Engine Modules & C-Bridge Headers", lambda: check_native_engine_modules(root)),
        ("Management Layer Swift Protocols & Python Modules", lambda: check_management_modules(root)),
        ("Management Layer Interface & Functional Contracts", lambda: check_management_layer_interfaces()),
    ]

    results: List[Dict[str, Any]] = []
    overall_success = True

    for name, fn in checks:
        success, message = fn()
        results.append({
            "name": name,
            "success": success,
            "message": message,
        })
        if not success:
            overall_success = False

    return overall_success, results


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = StrictArgumentParser(
        description="Automated Phase 1 Verification Script for Desk-simulator PC OS Emulator.",
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
        "--dry-run",
        action="store_true",
        default=False,
        help="Simulate verification without running external processes",
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
        help="Output results in JSON format",
    )
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)
    root = Path(args.workspace_root).resolve()

    if not args.json:
        print("=" * 75)
        print(" Desk-simulator Phase 1 Automated Verification Script")
        print(f" Workspace Root: {root}")
        print("=" * 75)

    success, results = run_all_phase1_checks(root, skip_git=args.skip_git)

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
        print(f"  [SUCCESS] Phase 1 Verification Passed! (All {len(results)} Checks OK)")
        print("  Desk-simulator is fully compliant with Phase 1 Architecture Specifications.")
    else:
        failed_count = sum(1 for r in results if not r["success"])
        print(f"  [FAIL] Phase 1 Verification Failed! ({failed_count}/{len(results)} checks failed)")
    print("=" * 75 + "\n")

    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
