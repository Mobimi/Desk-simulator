#!/usr/bin/env python3
"""
Desk-simulator Engine Build and Stripping Automation Script
Cross-platform build configuration validator for Next-Generation PC OS Emulator for iPhone.

Validates and prepares:
1. Target Whitelist: strictly 'x86_64-softmmu' and 'aarch64-softmmu' (pruning MIPS, PPC, SPARC, RISC-V, s390x, etc.)
2. Compiler Flags: enforces -O3, -flto, and Apple Silicon targets (-mcpu=apple-m1, -mcpu=apple-a15, -arch arm64)
3. SPICE IPC Transport: Unix Domain Sockets (unix=on,addr=...,disable-ticketing=on), prohibiting TCP loopback
4. TCG Memory Clamping: restricts -tb-size within [128MB, 256MB]
5. Channel Pruning: disables Smartcard and WebDAV channels to save ~100MB RAM
"""

import argparse
import json
import os
import sys
from pathlib import Path
from typing import List, Optional

# Resolve workspace root
WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
if str(WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_ROOT))

from Engine.Config.engine_config import EngineConfig


class StrictArgumentParser(argparse.ArgumentParser):
    """ArgumentParser that exits with code 1 instead of 2 on error."""
    def error(self, message: str):
        sys.stderr.write(f"Error: {message}\n")
        sys.exit(1)


def parse_cli_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = StrictArgumentParser(
        description="Desk-simulator Stripped Engine Build & Configuration Validator",
        allow_abbrev=False,
    )
    parser.add_argument(
        "--target-list",
        action="append",
        default=None,
        help="Target architectures to validate/build (space- or comma-separated, e.g. x86_64-softmmu,aarch64-softmmu)",
    )
    parser.add_argument(
        "--cflags",
        action="append",
        default=None,
        help="Custom compiler optimization flags to validate (e.g. '-O3 -flto -mcpu=apple-m1')",
    )
    parser.add_argument(
        "--ldflags",
        action="append",
        default=None,
        help="Custom linker optimization flags to validate (e.g. '-flto')",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Simulate the build and validation without generating disk artifacts",
    )

    raw_argv = sys.argv[1:] if argv is None else list(argv)
    processed_argv: List[str] = []
    i = 0
    option_names = {"--target-list", "--cflags", "--ldflags"}
    while i < len(raw_argv):
        arg = raw_argv[i]
        if arg in option_names:
            vals: List[str] = []
            i += 1
            while i < len(raw_argv) and not raw_argv[i].startswith("--"):
                vals.append(raw_argv[i])
                i += 1
            if vals:
                for v in vals:
                    processed_argv.append(f"{arg}={v}")
            else:
                processed_argv.append(arg)
            continue
        processed_argv.append(arg)
        i += 1

    return parser.parse_args(processed_argv)


def log_step(title: str):
    print(f"\n==> {title}")


def log_pass(message: str):
    print(f"  [PASS] {message}")


def log_info(message: str):
    print(f"  [INFO] {message}")


def log_fail(message: str):
    print(f"  [FAIL] {message}")


def verify_target_whitelist(custom_targets: Optional[List[str]] = None) -> bool:
    log_step("Verifying Engine Target Whitelist")
    
    if custom_targets is not None:
        targets = custom_targets
        log_info(f"Validating custom CLI target list: {targets}")
    else:
        whitelist_file = WORKSPACE_ROOT / "Engine" / "Config" / "target_whitelist.txt"
        if not whitelist_file.exists():
            log_fail("target_whitelist.txt missing")
            return False
        targets = EngineConfig.get_whitelist(whitelist_file)
        log_info(f"Loaded whitelist targets: {targets}")

    if not EngineConfig.validate_targets(targets, require_all=(custom_targets is None)):
        log_fail(f"Invalid or unauthorized target(s) specified: {targets}")
        return False

    # Ensure all forbidden architectures are stripped
    for forbidden in EngineConfig.FORBIDDEN_TARGETS:
        for t in targets:
            if forbidden in t and t not in EngineConfig.ALLOWED_TARGETS:
                log_fail(f"Forbidden architecture detected: {forbidden}")
                return False

    log_pass("Strict target whitelist verified: exclusively x86_64-softmmu and aarch64-softmmu retained.")
    return True


def verify_declarative_config() -> bool:
    log_step("Verifying Declarative Engine Configuration (engine_config.json)")
    config_file = WORKSPACE_ROOT / "Engine" / "Config" / "engine_config.json"
    if not config_file.exists():
        log_fail("engine_config.json missing")
        return False

    cfg = EngineConfig.load_config(config_file)

    # Check allowed targets
    if cfg.get("allowed_targets") != EngineConfig.ALLOWED_TARGETS:
        log_fail(f"allowed_targets mismatch: {cfg.get('allowed_targets')}")
        return False

    # Check compiler flags (-O3, -flto)
    req_flags = cfg.get("compiler_required_flags", [])
    if "-O3" not in req_flags or "-flto" not in req_flags:
        log_fail("Compiler required flags must contain -O3 and -flto")
        return False

    # Check Apple Silicon targets
    apple_targets = cfg.get("apple_silicon_targets", [])
    if not any("-mcpu=apple" in t or "-arch arm64" in t for t in apple_targets):
        log_fail("Apple Silicon targets missing from declarative config")
        return False

    # Check TCG buffer clamp bounds
    tcg_clamp = cfg.get("tcg_buffer_clamp", {})
    if tcg_clamp.get("min_mb") != 128 or tcg_clamp.get("max_mb") != 256:
        log_fail("TCG clamp range must be [128MB, 256MB]")
        return False

    # Check SPICE IPC transport
    spice_cfg = cfg.get("spice_ipc", {})
    if spice_cfg.get("transport") != "unix":
        log_fail("SPICE IPC transport must be 'unix'")
        return False

    # Check pruned channels
    pruned = spice_cfg.get("pruned_channels", [])
    if "smartcard" not in pruned or "webdav" not in pruned:
        log_fail("SPICE pruned channels must include smartcard and webdav")
        return False

    log_pass("Declarative engine_config.json fully matches architectural specifications.")
    return True


def verify_compiler_optimization_flags(
    custom_cflags: Optional[List[str]] = None,
    custom_ldflags: Optional[List[str]] = None,
) -> bool:
    log_step("Verifying Compiler and Linker Optimization Flags")

    if custom_cflags is not None:
        log_info(f"Validating custom CLI compiler flags: {custom_cflags}")
        if not EngineConfig.validate_compiler_flags(custom_cflags):
            log_fail(f"Custom compiler flags failed validation: {custom_cflags}")
            return False
    else:
        test_flags = ["-O3", "-flto", "-mcpu=apple-m1", "-arch arm64"]
        log_info(f"Evaluating candidate compilation flags: {test_flags}")
        if not EngineConfig.validate_compiler_flags(test_flags, require_apple_silicon=True):
            log_fail("Compiler flags failed validation")
            return False

    if custom_ldflags is not None:
        log_info(f"Validating custom CLI linker flags: {custom_ldflags}")
        if "-O0" in custom_ldflags:
            log_fail("Linker flags contain conflicting debug flag: -O0")
            return False

    # Standard baseline rejection tests
    if EngineConfig.validate_compiler_flags(["-O2", "-flto"]):
        log_fail("Failed to reject missing -O3")
        return False

    if EngineConfig.validate_compiler_flags(["-O3"]):
        log_fail("Failed to reject missing -flto")
        return False

    if EngineConfig.validate_compiler_flags(["-O3", "-flto", "-O0"]):
        log_fail("Failed to reject conflicting -O0 debug flag")
        return False

    log_pass("Compiler flags verified: -O3, -flto, and Apple Silicon tuning strictly enforced.")
    return True


def verify_spice_uds_and_tcg_bounds() -> bool:
    log_step("Verifying SPICE Unix Domain Socket IPC & TCG Bounds Clamping")
    uds_path = "/tmp/desk_spice.sock"
    args = EngineConfig.generate_spice_uds_args(uds_path, disable_smartcard=True, disable_webdav=True)
    arg_str = " ".join(args)

    if "unix=on" not in arg_str or f"addr={uds_path}" not in arg_str:
        log_fail("SPICE UDS parameters missing unix=on or socket address")
        return False

    if "127.0.0.1" in arg_str or "localhost" in arg_str or "port=" in arg_str:
        log_fail("TCP loopback detected in SPICE arguments")
        return False

    if "smartcard=off" not in arg_str:
        log_fail("Smartcard pruning flag missing from SPICE arguments")
        return False

    if "webdav=off" not in arg_str:
        log_fail("WebDAV pruning flag missing from SPICE arguments")
        return False

    # Verify TCG buffer clamping
    test_bounds = [(0, 128), (64, 128), (128, 128), (200, 200), (256, 256), (512, 256), (1024, 256)]
    for requested, expected in test_bounds:
        clamped = EngineConfig.clamp_tcg_size(requested)
        if clamped != expected:
            log_fail(f"TCG clamping error: requested {requested}MB -> expected {expected}MB, got {clamped}MB")
            return False

    # Verify QEMU command line assembly
    for target in EngineConfig.ALLOWED_TARGETS:
        cmd = EngineConfig.generate_qemu_cmdline(
            target=target,
            ram_mb=2048,
            tb_size_mb=512,
            spice_socket=uds_path,
        )
        cmd_str = " ".join(cmd)
        target_bin = f"qemu-system-{target.replace('-softmmu', '')}"
        if cmd[0] != target_bin:
            log_fail(f"Incorrect binary in cmdline: {cmd[0]} != {target_bin}")
            return False
        if "tcg,tb-size=256" not in cmd_str:
            log_fail(f"TCG clamp not reflected in QEMU cmdline: {cmd_str}")
            return False
        if "unix=on" not in cmd_str or "smartcard=off" not in cmd_str:
            log_fail(f"SPICE parameters not reflected in QEMU cmdline: {cmd_str}")
            return False

    log_pass("SPICE UDS IPC and TCG buffer size clamping verified successfully.")
    return True


def verify_swift_engine_headers() -> bool:
    log_step("Verifying Engine Swift & C-Bridge Header Integrity")
    required_engine_files = [
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

    for rel_path in required_engine_files:
        full_path = WORKSPACE_ROOT / rel_path
        if not full_path.exists():
            log_fail(f"Missing required engine file: {rel_path}")
            return False
        if full_path.stat().st_size == 0:
            log_fail(f"Empty engine file detected: {rel_path}")
            return False
        log_info(f"Verified engine module: {rel_path} ({full_path.stat().st_size} bytes)")

    log_pass("All Swift and C-Bridge engine definitions verified.")
    return True


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_cli_args(argv)

    print("=" * 70)
    print(" Desk-simulator Stripped Engine Build & Configuration Validator")
    print("=" * 70)
    print(f"Workspace Root: {WORKSPACE_ROOT}")

    if args.dry_run:
        log_info("Dry-run mode enabled: simulating build and verification checks only.")

    # Parse and tokenize custom targets if provided
    custom_targets: Optional[List[str]] = None
    if args.target_list is not None:
        custom_targets = []
        for item in args.target_list:
            for t in item.replace(",", " ").split():
                if t.strip():
                    custom_targets.append(t.strip())
        if not custom_targets:
            log_fail("--target-list provided with empty targets")
            return 1

    # Parse and tokenize custom cflags if provided
    custom_cflags: Optional[List[str]] = None
    if args.cflags is not None:
        custom_cflags = []
        for item in args.cflags:
            for f in item.split():
                if f.strip():
                    custom_cflags.append(f.strip())
        if not custom_cflags:
            log_fail("--cflags provided with empty flags")
            return 1

    # Parse and tokenize custom ldflags if provided
    custom_ldflags: Optional[List[str]] = None
    if args.ldflags is not None:
        custom_ldflags = []
        for item in args.ldflags:
            for f in item.split():
                if f.strip():
                    custom_ldflags.append(f.strip())

    checks = [
        ("Target Whitelist", lambda: verify_target_whitelist(custom_targets)),
        ("Declarative Config", verify_declarative_config),
        ("Compiler Flags (-O3, -flto)", lambda: verify_compiler_optimization_flags(custom_cflags, custom_ldflags)),
        ("SPICE UDS & TCG Clamping", verify_spice_uds_and_tcg_bounds),
        ("Swift & C-Bridge Headers", verify_swift_engine_headers),
    ]

    for title, check_func in checks:
        if not check_func():
            print("\n" + "=" * 70)
            print(f"  [BUILD ENGINE FAILED] at step: {title}")
            print("=" * 70)
            return 1

    print("\n" + "=" * 70)
    print("  [SUCCESS] All Engine Core Stripping & Integration Checks Passed!")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(main())
