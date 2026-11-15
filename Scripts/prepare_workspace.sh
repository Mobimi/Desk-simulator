#!/usr/bin/env bash
# ==============================================================================
# Desk-simulator: Workspace Preparation & Verification Shell Script
# ==============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKSPACE_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

echo "============================================================"
echo "Desk-simulator Shell Workspace Preparation"
echo "Workspace root: ${WORKSPACE_ROOT}"
echo "============================================================"

# Resolve python command
PYTHON_CMD=""
if command -v python3 >/dev/null 2>&1; then
    PYTHON_CMD="python3"
elif command -v python >/dev/null 2>&1; then
    PYTHON_CMD="python"
else
    echo "[ERROR] Python 3 was not found in PATH."
    exit 1
fi

echo "[INFO] Using Python interpreter: $($PYTHON_CMD --version)"

# Invoke python prepare_workspace.py
exec "$PYTHON_CMD" "${SCRIPT_DIR}/prepare_workspace.py"
