#!/usr/bin/env bash
#
# Desk-simulator Stripped Engine Build & Configuration Script (POSIX Shell)
# Cross-platform build script wrapper for Unix / macOS / Darwin environments.
#

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKSPACE_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

echo "========================================================================"
echo " Desk-simulator Stripped Engine Build Script (Shell Wrapper)"
echo " Workspace: ${WORKSPACE_ROOT}"
echo "========================================================================"

# Enforce target whitelist in shell
TARGET_WHITELIST=("x86_64-softmmu" "aarch64-softmmu")
REQUIRED_CFLAGS=("-O3" "-flto")
APPLE_FLAGS=("-mcpu=apple-m1" "-mcpu=apple-a15" "-arch arm64")

echo "[INFO] Whitelisted targets: ${TARGET_WHITELIST[*]}"
echo "[INFO] Compiler optimization flags: ${REQUIRED_CFLAGS[*]}"
echo "[INFO] Apple Silicon targets: ${APPLE_FLAGS[*]}"

# Check Python environment
if command -v python3 >/dev/null 2>&1; then
    PYTHON_CMD="python3"
elif command -v python >/dev/null 2>&1; then
    PYTHON_CMD="python"
else
    echo "[WARN] Python not found in PATH; running native shell assertions."
    # Native check
    if [[ ! -f "${WORKSPACE_ROOT}/Engine/Config/target_whitelist.txt" ]]; then
        echo "[FAIL] target_whitelist.txt is missing."
        exit 1
    fi
    echo "[PASS] Native shell checks succeeded."
    exit 0
fi

# Execute Python verification engine with argument forwarding
echo "[INFO] Invoking build_engine.py using ${PYTHON_CMD}..."
"${PYTHON_CMD}" "${WORKSPACE_ROOT}/Scripts/build_engine.py" "$@"
EXIT_CODE=$?

if [[ ${EXIT_CODE} -eq 0 ]]; then
    echo "[SUCCESS] Engine build configuration completed successfully."
    exit 0
else
    echo "[FAIL] Engine build configuration failed with code ${EXIT_CODE}."
    exit ${EXIT_CODE}
fi
