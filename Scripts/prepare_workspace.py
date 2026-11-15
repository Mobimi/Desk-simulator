#!/usr/bin/env python3
"""
Desk-simulator Workspace Preparation and Verification Script
Cross-platform workspace initializer for Next-Generation PC OS Emulator for iPhone.

Verifies and sets up:
- Git repository tracking against remote origin (https://github.com/Mobimi/Desk-simulator)
- Three-tier modular workspace directory layout (UI, Management, Engine, Scripts, Tests)
- Project baseline files (.gitignore, README.md)
"""

import sys
import os
import subprocess
from pathlib import Path

REQUIRED_REMOTE_URL = "https://github.com/Mobimi/Desk-simulator"
REQUIRED_BRANCH = "main"

REQUIRED_DIRECTORIES = [
    "UI/Views",
    "UI/ViewModels",
    "Management/SmartMemoryGuard",
    "Management/PCoreScheduler",
    "Management/ISOAutoPilot",
    "Management/Storage",
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

REQUIRED_FILES = [
    "README.md",
    ".gitignore",
]


def log_step(title: str):
    print(f"\n==> {title}")


def log_pass(message: str):
    print(f"  [PASS] {message}")


def log_info(message: str):
    print(f"  [INFO] {message}")


def log_warn(message: str):
    print(f"  [WARN] {message}")


def log_fail(message: str):
    print(f"  [FAIL] {message}")


def run_command(cmd: list[str], cwd: Path) -> tuple[int, str, str]:
    try:
        proc = subprocess.run(
            cmd,
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
        return proc.returncode, proc.stdout.strip(), proc.stderr.strip()
    except Exception as exc:
        return 1, "", str(exc)


def verify_python_version() -> bool:
    log_step("Verifying Python Environment")
    ver = sys.version_info
    log_info(f"Python version: {ver.major}.{ver.minor}.{ver.micro}")
    if ver.major < 3 or (ver.major == 3 and ver.minor < 8):
        log_fail("Python 3.8+ required")
        return False
    log_pass("Python version meets requirements (3.8+)")
    return True


def verify_and_prepare_directories(workspace_root: Path) -> bool:
    log_step("Verifying and Preparing Workspace Directory Layout")
    all_ok = True
    for rel_dir in REQUIRED_DIRECTORIES:
        dir_path = workspace_root / rel_dir
        if not dir_path.exists():
            log_info(f"Directory missing, creating: {rel_dir}")
            dir_path.mkdir(parents=True, exist_ok=True)
            # Create .gitkeep placeholder
            gitkeep = dir_path / ".gitkeep"
            if not gitkeep.exists():
                gitkeep.write_text("# Placeholder\n", encoding="utf-8")
        
        if dir_path.is_dir():
            log_pass(f"Directory verified: {rel_dir}")
        else:
            log_fail(f"Path is not a directory: {rel_dir}")
            all_ok = False
            
    for rel_file in REQUIRED_FILES:
        file_path = workspace_root / rel_file
        if file_path.exists():
            log_pass(f"Baseline file verified: {rel_file}")
        else:
            log_warn(f"Baseline file missing: {rel_file}")
    return all_ok


def verify_and_configure_git(workspace_root: Path) -> bool:
    log_step("Verifying Git Repository and Remote Tracking")

    # Check git presence
    code, stdout, _ = run_command(["git", "--version"], workspace_root)
    if code != 0:
        log_warn("Git CLI not found in PATH; skipping Git remote checks.")
        return True

    # Check if inside git repo
    code, stdout, _ = run_command(["git", "rev-parse", "--is-inside-work-tree"], workspace_root)
    if code != 0 or stdout != "true":
        log_info("Initializing Git repository...")
        init_code, _, init_err = run_command(["git", "init", "-b", REQUIRED_BRANCH], workspace_root)
        if init_code != 0:
            log_fail(f"Failed to initialize git repository: {init_err}")
            return False

    # Check or configure remote origin
    code, remotes_out, _ = run_command(["git", "remote", "-v"], workspace_root)
    has_origin = False
    origin_matches = False
    for line in remotes_out.splitlines():
        if line.startswith("origin"):
            has_origin = True
            url_part = line.split()[1] if len(line.split()) > 1 else ""
            if REQUIRED_REMOTE_URL in url_part:
                origin_matches = True
                break

    if not has_origin:
        log_info(f"Configuring remote 'origin' -> {REQUIRED_REMOTE_URL}")
        add_code, _, add_err = run_command(
            ["git", "remote", "add", "origin", REQUIRED_REMOTE_URL], workspace_root
        )
        if add_code != 0:
            log_fail(f"Failed to add git remote origin: {add_err}")
            return False
        origin_matches = True
    elif not origin_matches:
        log_info(f"Updating remote 'origin' URL -> {REQUIRED_REMOTE_URL}")
        set_code, _, set_err = run_command(
            ["git", "remote", "set-url", "origin", REQUIRED_REMOTE_URL], workspace_root
        )
        if set_code != 0:
            log_fail(f"Failed to update remote origin URL: {set_err}")
            return False
        origin_matches = True

    if origin_matches:
        log_pass(f"Git remote 'origin' points to {REQUIRED_REMOTE_URL}")

    # Check current branch
    code, branch_out, _ = run_command(["git", "branch", "--show-current"], workspace_root)
    current_branch = branch_out.strip()
    log_info(f"Current branch: {current_branch or 'detached / initial'}")

    # Verify upstream tracking if origin exists
    code, tracking_out, _ = run_command(
        ["git", "rev-parse", "--abbrev-ref", f"{REQUIRED_BRANCH}@{{upstream}}"], workspace_root
    )
    if code == 0 and "origin" in tracking_out:
        log_pass(f"Branch '{REQUIRED_BRANCH}' is tracking upstream '{tracking_out}'")
    else:
        log_info(f"Upstream tracking for '{REQUIRED_BRANCH}' not fully established or offline.")

    return True


def main() -> int:
    workspace_root = Path(__file__).resolve().parent.parent
    print("=" * 60)
    print(" Desk-simulator Workspace Initialization & Verification")
    print(f" Workspace root: {workspace_root}")
    print("=" * 60)

    py_ok = verify_python_version()
    dir_ok = verify_and_prepare_directories(workspace_root)
    git_ok = verify_and_configure_git(workspace_root)

    print("\n" + "=" * 60)
    if py_ok and dir_ok and git_ok:
        print(" [SUCCESS] Workspace preparation and verification complete!")
        print("=" * 60)
        return 0
    else:
        print(" [FAILURE] Workspace preparation encountered errors.")
        print("=" * 60)
        return 1


if __name__ == "__main__":
    sys.exit(main())
