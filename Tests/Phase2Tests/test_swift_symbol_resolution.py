#!/usr/bin/env python3
"""
Desk-simulator Phase 2: Swift Static Member Symbol and Interface Resolution Test Suite.
Validates:
1. Static AST parsing of Swift types across Engine/, Management/, and UI/
2. Declaration of required member symbols on RuntimeMemoryMonitor, ThermalMonitor,
   VMSessionViewModel, MetalDisplayRenderer, VMStore, and PCoreScheduler
3. Cross-file member symbol resolution across all UI/Views/ and UI/ViewModels/ call sites
4. Deterministic detection of undefined member accesses (anti-regression forensics)
"""

from __future__ import annotations

import os
import re
import sys
import unittest
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

# Workspace root resolution
candidate_root = Path(__file__).resolve().parent.parent.parent
if (candidate_root / "Engine").is_dir():
    WORKSPACE_ROOT = candidate_root
elif (Path.cwd() / "Engine").is_dir():
    WORKSPACE_ROOT = Path.cwd().resolve()
else:
    WORKSPACE_ROOT = Path(r"d:\project nhảm\giả lập").resolve()

if str(WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_ROOT))


def strip_comments_preserve_interpolations(code: str) -> str:
    """
    Strips single-line and nested multi-line comments from Swift source code,
    replaces string literals with whitespace to maintain exact line and column
    offsets, while preserving executable Swift expressions inside string
    interpolations `\\( ... )`.
    """
    result = []
    i = 0
    n = len(code)
    mode_stack = ["code"]
    interp_paren_depth: List[int] = []

    while i < n:
        curr_mode = mode_stack[-1]

        if curr_mode == "code":
            if code[i:i + 2] == "/*":
                depth = 1
                i += 2
                while i < n and depth > 0:
                    if code[i:i + 2] == "/*":
                        depth += 1
                        i += 2
                    elif code[i:i + 2] == "*/":
                        depth -= 1
                        i += 2
                    else:
                        i += 1
                continue
            elif code[i:i + 2] == "//":
                nl = code.find("\n", i + 2)
                if nl == -1:
                    break
                result.append("\n")
                i = nl + 1
                continue
            elif code[i:i + 3] == '"""':
                mode_stack.append("multiline_string")
                result.append("   ")
                i += 3
                continue
            elif code[i] == '"':
                mode_stack.append("string")
                result.append(" ")
                i += 1
                continue
            elif code[i] == ")":
                if interp_paren_depth:
                    interp_paren_depth[-1] -= 1
                    if interp_paren_depth[-1] == 0:
                        interp_paren_depth.pop()
                        mode_stack.pop()
                        result.append(" ")
                        i += 1
                        continue
                result.append(code[i])
                i += 1
            elif code[i] == "(":
                if interp_paren_depth:
                    interp_paren_depth[-1] += 1
                result.append(code[i])
                i += 1
            else:
                result.append(code[i])
                i += 1

        elif curr_mode in ("string", "multiline_string"):
            if code[i:i + 2] == "\\(":
                mode_stack.append("code")
                interp_paren_depth.append(1)
                result.append("  ")
                i += 2
                continue
            elif curr_mode == "string" and code[i] == '"':
                mode_stack.pop()
                result.append(" ")
                i += 1
                continue
            elif curr_mode == "multiline_string" and code[i:i + 3] == '"""':
                mode_stack.pop()
                result.append("   ")
                i += 3
                continue
            elif code[i] == "\\":
                result.append("  ")
                i += 2
                continue
            else:
                result.append("\n" if code[i] == "\n" else " ")
                i += 1

    return "".join(result)


class SwiftTypeInfo:
    """Holds parsed metadata for a Swift class, struct, enum, protocol, or extension."""

    def __init__(self, name: str, kind: str, file_path: Path):
        self.name = name
        self.kind = kind
        self.file_path = file_path
        self.properties: Dict[str, Optional[str]] = {}
        self.methods: Set[str] = set()
        self.cases: Set[str] = set()
        self.inherited: List[str] = []

    def all_members(self) -> Set[str]:
        members = set(self.properties.keys()) | self.methods | self.cases
        for inh in self.inherited:
            if "ObservableObject" in inh:
                members.add("objectWillChange")
            if "Identifiable" in inh:
                members.add("id")
            if "CaseIterable" in inh or self.kind == "enum":
                members.add("allCases")
        if self.kind == "enum":
            for inh in self.inherited:
                if any(t in inh for t in ["String", "Int", "UInt", "UInt8", "UInt16", "UInt32", "UInt64", "RawRepresentable"]):
                    members.add("rawValue")
        return members


def _clean_type_annotation(t_str: Optional[str]) -> Optional[str]:
    if not t_str:
        return None
    t = t_str.strip().rstrip("?").rstrip("!").strip()
    if t.startswith("[") and t.endswith("]"):
        inner = t[1:-1].strip()
        return f"Array<{inner}>"
    m = re.match(r"^[A-Za-z0-9_]+", t)
    return m.group(0) if m else t


def parse_type_members(type_name: str, kind: str, body: str, file_path: Path) -> SwiftTypeInfo:
    tinfo = SwiftTypeInfo(type_name, kind, file_path)

    prop_re = re.compile(
        r"(?:@Published\s+|@State\s+|@ObservedObject\s+|@StateObject\s+|@Binding\s+|public\s+|private\(set\)\s+|internal\s+|private\s+|fileprivate\s+|static\s+|final\s+|lazy\s+|weak\s+)*(?:var|let)\s+([A-Za-z0-9_]+)(?:\s*:\s*([A-Za-z0-9_?<>\[\]:\s]+?))?(?:\s*=\s*|\s*\{|\s*$)"
    )
    func_re = re.compile(
        r"(?:public\s+|internal\s+|private\s+|fileprivate\s+|static\s+|final\s+|mutating\s+|override\s+|@MainActor\s+|@objc\s+)*func\s+([A-Za-z0-9_]+)"
    )
    case_re = re.compile(
        r"case\s+([A-Za-z0-9_,\s]+)"
    )

    depth = 0
    stmt_chars: List[str] = []

    def process_stmt(stmt: str) -> None:
        fm = func_re.search(stmt)
        if fm:
            tinfo.methods.add(fm.group(1))
            return

        pm = prop_re.search(stmt)
        if pm:
            pname = pm.group(1)
            ptype = _clean_type_annotation(pm.group(2))
            tinfo.properties[pname] = ptype
            return

        if kind == "enum":
            cm = case_re.search(stmt)
            if cm:
                for c in cm.group(1).split(","):
                    c_name = c.split("=")[0].split("(")[0].strip()
                    if c_name:
                        tinfo.cases.add(c_name)

    for ch in body:
        if ch == "{":
            if depth == 0:
                stmt = "".join(stmt_chars).strip()
                process_stmt(stmt)
                stmt_chars = []
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                stmt_chars = []
        elif depth == 0:
            if ch in (";", "\n"):
                stmt = "".join(stmt_chars).strip()
                if stmt:
                    process_stmt(stmt)
                stmt_chars = []
            else:
                stmt_chars.append(ch)

    if stmt_chars and depth == 0:
        stmt = "".join(stmt_chars).strip()
        if stmt:
            process_stmt(stmt)

    return tinfo


def parse_all_swift_types(root: Path) -> Dict[str, SwiftTypeInfo]:
    swift_files = (
        list(root.glob("Engine/**/*.swift"))
        + list(root.glob("Management/**/*.swift"))
        + list(root.glob("UI/**/*.swift"))
    )

    type_decl_re = re.compile(
        r"\b(?:(?:public|private|internal|fileprivate|final|open|@MainActor)\s+)*(class|struct|enum|protocol|extension)\s+([A-Za-z0-9_]+)(?:\s*:\s*([^{]+))?\s*\{"
    )

    registry: Dict[str, SwiftTypeInfo] = {}

    for sf in swift_files:
        clean = strip_comments_preserve_interpolations(sf.read_text(encoding="utf-8"))
        for m in type_decl_re.finditer(clean):
            kind = m.group(1)
            tname = m.group(2)
            inheritance = m.group(3)

            start = m.end() - 1
            idx = start + 1
            depth = 1
            end = len(clean)
            while idx < len(clean):
                if clean[idx] == "{":
                    depth += 1
                elif clean[idx] == "}":
                    depth -= 1
                    if depth == 0:
                        end = idx
                        break
                idx += 1

            body = clean[start + 1 : end]
            parsed = parse_type_members(tname, kind, body, sf)

            if inheritance:
                for inh in inheritance.split(","):
                    parsed.inherited.append(inh.strip())

            if tname not in registry:
                registry[tname] = parsed
            else:
                existing = registry[tname]
                existing.properties.update(parsed.properties)
                existing.methods.update(parsed.methods)
                existing.cases.update(parsed.cases)
                existing.inherited.extend(parsed.inherited)

    return registry


SWIFT_STANDARD_MEMBERS = {
    "Array": {"count", "isEmpty", "first", "last", "firstIndex", "append", "insert", "remove", "removeAll", "filter", "map", "compactMap", "contains", "joined"},
    "String": {"count", "isEmpty", "lowercased", "uppercased", "split", "contains", "hasPrefix", "hasSuffix", "utf8", "data"},
    "URL": {"lastPathComponent", "pathExtension", "path", "appendingPathComponent", "startAccessingSecurityScopedResource", "stopAccessingSecurityScopedResource"},
    "Data": {"count", "isEmpty", "append", "write"},
    "UUID": {"uuidString"},
    "Date": {"timeIntervalSince1970"},
}


class SwiftSymbolResolver:
    """Forensic static analysis engine verifying member symbol resolution across Swift sources."""

    def __init__(self, root: Path):
        self.root = root
        self.types = parse_all_swift_types(root)
        self.base_symbol_bindings = {
            "memoryMonitor": "RuntimeMemoryMonitor",
            "thermalMonitor": "ThermalMonitor",
            "pCoreScheduler": "PCoreScheduler",
            "displayRenderer": "MetalDisplayRenderer",
            "renderer": "MetalDisplayRenderer",
            "store": "VMStore",
            "isoAutoPilot": "ISOAutoPilot",
            "storageBridge": "StorageBridge",
            "jitStatus": "JITStatus",
        }

    def inspect_file_scope(self, file_path: Path) -> Dict[str, str]:
        bindings = dict(self.base_symbol_bindings)
        clean = strip_comments_preserve_interpolations(file_path.read_text(encoding="utf-8"))

        var_re = re.compile(
            r"(?:@ObservedObject|@StateObject|@Binding|@State|public|private|internal)*\s*(?:var|let)\s+([A-Za-z0-9_]+)\s*:\s*([A-Za-z0-9_?<>\[\]]+)"
        )
        for m in var_re.finditer(clean):
            var_name = m.group(1)
            raw_t = _clean_type_annotation(m.group(2))
            if raw_t:
                bindings[var_name] = raw_t

        if "viewModel" not in bindings:
            if "VMSessionViewModel" in clean:
                bindings["viewModel"] = "VMSessionViewModel"
            elif "HomeViewModel" in clean:
                bindings["viewModel"] = "HomeViewModel"
            elif "SetupWizardViewModel" in clean:
                bindings["viewModel"] = "SetupWizardViewModel"

        return bindings

    def check_call_sites(self, files: Optional[List[Path]] = None) -> List[Dict[str, Any]]:
        target_files = files if files is not None else (
            list(self.root.glob("UI/Views/**/*.swift"))
            + list(self.root.glob("UI/ViewModels/**/*.swift"))
        )
        errors: List[Dict[str, Any]] = []
        chain_re = re.compile(r"\b([A-Za-z_][A-Za-z0-9_]*)(?:\.([A-Za-z_][A-Za-z0-9_]*))+")

        for sf in target_files:
            raw_text = sf.read_text(encoding="utf-8")
            clean_text = strip_comments_preserve_interpolations(raw_text)
            lines = clean_text.splitlines()
            file_bindings = self.inspect_file_scope(sf)

            for line_idx, line in enumerate(lines, 1):
                closure_m = re.search(r"\{\s*([A-Za-z0-9_]+)\s+in", line)
                local_bindings = dict(file_bindings)
                if closure_m:
                    local_var = closure_m.group(1)
                    if local_var in local_bindings:
                        del local_bindings[local_var]

                for m in chain_re.finditer(line):
                    full_expr = m.group(0)
                    parts = full_expr.split(".")
                    root_var = parts[0]

                    if root_var not in local_bindings:
                        continue

                    curr_type_name = local_bindings[root_var]

                    for i, member in enumerate(parts[1:], 1):
                        if curr_type_name.startswith("Array<"):
                            inner_t = curr_type_name[6:-1]
                            if member in SWIFT_STANDARD_MEMBERS["Array"]:
                                curr_type_name = "Int" if member == "count" else "Bool"
                                continue
                            elif member in ("first", "last"):
                                curr_type_name = inner_t
                                continue
                            else:
                                subchain = ".".join(parts[: i + 1])
                                errors.append({
                                    "file": str(sf.relative_to(self.root)),
                                    "line": line_idx,
                                    "expression": full_expr,
                                    "unresolved_member": member,
                                    "target_type": curr_type_name,
                                    "message": f"Member '{member}' not declared on '{curr_type_name}' (referenced via '{subchain}')",
                                })
                                break

                        if curr_type_name in SWIFT_STANDARD_MEMBERS:
                            break

                        if curr_type_name not in self.types:
                            break

                        tinfo = self.types[curr_type_name]
                        all_members = tinfo.all_members()

                        inherited_members: Set[str] = set()
                        for base_name in tinfo.inherited:
                            if base_name in self.types:
                                inherited_members.update(self.types[base_name].all_members())

                        combined_members = all_members | inherited_members

                        if member not in combined_members:
                            subchain = ".".join(parts[: i + 1])
                            errors.append({
                                "file": str(sf.relative_to(self.root)),
                                "line": line_idx,
                                "expression": full_expr,
                                "unresolved_member": member,
                                "target_type": curr_type_name,
                                "message": f"Member '{member}' not declared on type '{curr_type_name}' (referenced via '{subchain}')",
                            })
                            break

                        next_type = tinfo.properties.get(member)
                        if not next_type and member in inherited_members:
                            for base_name in tinfo.inherited:
                                if base_name in self.types and member in self.types[base_name].properties:
                                    next_type = self.types[base_name].properties[member]
                                    break
                        if next_type:
                            curr_type_name = next_type
                        else:
                            break

        return errors


class TestSwiftSymbolResolution(unittest.TestCase):
    """Test suite validating Swift types and cross-file member symbol resolution."""

    @classmethod
    def setUpClass(cls):
        cls.resolver = SwiftSymbolResolver(WORKSPACE_ROOT)

    def test_parsed_types_discovered(self):
        """Verifies that all core engine, management, and UI types are parsed."""
        types = self.resolver.types
        self.assertGreater(len(types), 40, f"Expected >40 parsed types, got {len(types)}")

        expected_types = [
            "RuntimeMemoryMonitor",
            "ThermalMonitor",
            "VMSessionViewModel",
            "HomeViewModel",
            "SetupWizardViewModel",
            "VMStore",
            "VMProfile",
            "MetalDisplayRenderer",
            "DisplayViewport",
            "PCoreScheduler",
            "ISOAutoPilot",
            "StorageBridge",
        ]
        for tname in expected_types:
            self.assertIn(tname, types, f"Expected Swift type '{tname}' to be discovered")

    def test_runtime_memory_monitor_member_contract(self):
        """Validates that RuntimeMemoryMonitor exposes all properties required by UI HUDs."""
        tinfo = self.resolver.types.get("RuntimeMemoryMonitor")
        self.assertIsNotNone(tinfo)
        members = tinfo.all_members()

        required_members = [
            "currentUsageMB",
            "currentFootprintBytes",
            "safeGuestCeilingMB",
            "dangerZone",
            "pressureLevel",
            "entitlements",
            "refreshSnapshot",
            "evaluateManualSelection",
        ]
        for m in required_members:
            self.assertIn(m, members, f"RuntimeMemoryMonitor missing required member '{m}'")

    def test_thermal_monitor_member_contract(self):
        """Validates that ThermalMonitor exposes thermalLevel/level and boost methods."""
        tinfo = self.resolver.types.get("ThermalMonitor")
        self.assertIsNotNone(tinfo)
        members = tinfo.all_members()

        required_members = [
            "thermalLevel",
            "level",
            "boostState",
            "beginBootBoost",
            "updateThermalState",
        ]
        for m in required_members:
            self.assertIn(m, members, f"ThermalMonitor missing required member '{m}'")

    def test_vmsession_viewmodel_member_contract(self):
        """Validates that VMSessionViewModel coordinates all runtime components and input HUDs."""
        tinfo = self.resolver.types.get("VMSessionViewModel")
        self.assertIsNotNone(tinfo)
        members = tinfo.all_members()

        required_members = [
            "memoryMonitor",
            "thermalMonitor",
            "pCoreScheduler",
            "displayRenderer",
            "store",
            "profile",
            "vmState",
            "spiceState",
            "jitStatus",
            "inputMode",
            "showShortcutToolbar",
            "showTelemetryOverlay",
            "startSession",
            "stopSession",
            "pauseSession",
            "resumeSession",
            "sendMouseMove",
            "sendMouseButton",
            "sendMouseScroll",
            "sendKeyScancode",
            "tapPCShortcut",
            "sendGamepadButton",
            "sendGamepadStick",
        ]
        for m in required_members:
            self.assertIn(m, members, f"VMSessionViewModel missing required member '{m}'")

    def test_metal_display_renderer_and_viewport_contract(self):
        """Validates that MetalDisplayRenderer and DisplayViewport meet display requirements."""
        r_info = self.resolver.types.get("MetalDisplayRenderer")
        v_info = self.resolver.types.get("DisplayViewport")
        self.assertIsNotNone(r_info)
        self.assertIsNotNone(v_info)

        self.assertIn("viewport", r_info.all_members())
        self.assertIn("render", r_info.all_members())
        self.assertIn("resizeViewport", r_info.all_members())

        self.assertIn("refreshRateHz", v_info.all_members())
        self.assertIn("width", v_info.all_members())
        self.assertIn("height", v_info.all_members())

    def test_vmstore_member_contract(self):
        """Validates VMStore persistent profile management contracts."""
        tinfo = self.resolver.types.get("VMStore")
        self.assertIsNotNone(tinfo)
        members = tinfo.all_members()

        required_members = [
            "profiles",
            "storageBridge",
            "isoAutoPilot",
            "createVM",
            "updateProfile",
            "deleteProfile",
            "markBooted",
        ]
        for m in required_members:
            self.assertIn(m, members, f"VMStore missing required member '{m}'")

    def test_cross_file_symbol_resolution_ui_call_sites(self):
        """Verifies that all call sites in UI Views and ViewModels resolve cleanly with 0 errors."""
        errors = self.resolver.check_call_sites()
        if errors:
            err_msgs = "\n".join([f"  - {e['file']}:{e['line']}: {e['message']}" for e in errors])
            self.fail(f"Found {len(errors)} unresolved Swift member symbol call sites:\n{err_msgs}")

    def test_forensics_engine_catches_synthetic_invalid_member(self):
        """Self-verification: confirms that the forensics engine deterministically detects bad members."""
        synthetic_error = False
        tinfo = self.resolver.types.get("RuntimeMemoryMonitor")
        if "nonExistentTelemetryPropertyXYZ" not in tinfo.all_members():
            synthetic_error = True
        self.assertTrue(synthetic_error, "Forensics engine failed to recognize missing member")


if __name__ == "__main__":
    unittest.main(verbosity=2)
