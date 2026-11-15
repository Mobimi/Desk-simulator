#!/usr/bin/env python3
"""
Unit and Mock Tests for Smart Memory Guard (MemoryGuard).
Verifies:
- Entitlement detection and dynamic memory ceiling ratios (0.80, 0.75, 0.50)
- 450MB safety reserve deduction and 1024MB safe floor clamping
- Memory pressure handling with VirtIO ballooning commands (normal, warning, critical)
- 90% Jetsam emergency danger threshold detection and auto-pause/resume lifecycle
"""

import sys
import unittest
from pathlib import Path

# Workspace root resolution
WORKSPACE_ROOT = Path(__file__).resolve().parent.parent.parent
if str(WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_ROOT))

from Management.SmartMemoryGuard.memory_guard import (
    MemoryEntitlements,
    MemoryGuard,
    MemoryPressureLevel,
    QMPCommand,
)


class TestMemoryGuardEntitlements(unittest.TestCase):
    """Unit tests for iOS memory entitlement detection and ceiling calculation."""

    def test_entitlements_both_enabled(self):
        """When both increased-memory-limit and extended-va are enabled, ratio is 0.80."""
        res = MemoryGuard.detect_entitlements(increased_memory=True, extended_va=True)
        self.assertTrue(res["increased_memory_limit"])
        self.assertTrue(res["extended_virtual_addressing"])
        self.assertAlmostEqual(res["ceiling_ratio"], 0.80)

    def test_entitlements_increased_memory_only(self):
        """When only increased-memory-limit is enabled, ratio is 0.75."""
        res = MemoryGuard.detect_entitlements(increased_memory=True, extended_va=False)
        self.assertTrue(res["increased_memory_limit"])
        self.assertFalse(res["extended_virtual_addressing"])
        self.assertAlmostEqual(res["ceiling_ratio"], 0.75)

    def test_entitlements_extended_va_only(self):
        """Extended virtual addressing alone does not raise memory ceiling; ratio remains 0.50."""
        res = MemoryGuard.detect_entitlements(increased_memory=False, extended_va=True)
        self.assertFalse(res["increased_memory_limit"])
        self.assertTrue(res["extended_virtual_addressing"])
        self.assertAlmostEqual(res["ceiling_ratio"], 0.50)

    def test_entitlements_neither_enabled(self):
        """When neither entitlement is present, standard iOS ceiling ratio is 0.50."""
        res = MemoryGuard.detect_entitlements(increased_memory=False, extended_va=False)
        self.assertFalse(res["increased_memory_limit"])
        self.assertFalse(res["extended_virtual_addressing"])
        self.assertAlmostEqual(res["ceiling_ratio"], 0.50)

    def test_entitlements_dictionary_keys(self):
        """detect_entitlements returns dictionary with all expected keys."""
        res = MemoryGuard.detect_entitlements()
        for key in ["increased_memory_limit", "extended_virtual_addressing", "ceiling_ratio"]:
            self.assertIn(key, res)

    def test_entitlements_dataclass_conversion(self):
        """MemoryEntitlements dataclass properly initializes and converts to dictionary."""
        ent = MemoryEntitlements(
            increased_memory_limit=True,
            extended_virtual_addressing=True,
            ceiling_ratio=0.80,
        )
        d = ent.to_dict()
        self.assertEqual(d["ceiling_ratio"], 0.80)
        self.assertTrue(d["increased_memory_limit"])


class TestMemoryGuardSafeRAM(unittest.TestCase):
    """Unit tests for safe guest RAM calculation with 450MB reserve and 1024MB safe floor."""

    def test_safe_ram_constants_values(self):
        """Verifies exact byte values for safety buffer and minimum safe floor."""
        self.assertEqual(MemoryGuard.SAFETY_BUFFER_BYTES, 450 * 1024 * 1024)
        self.assertEqual(MemoryGuard.MIN_SAFE_FLOOR_BYTES, 1024 * 1024 * 1024)
        self.assertAlmostEqual(MemoryGuard.DANGER_THRESHOLD_PERCENT, 0.90)

    def test_safe_ram_standard_calculation(self):
        """Available 3000MB minus 450MB safety reserve yields 2550MB."""
        available = 3000 * 1024 * 1024
        expected = (3000 - 450) * 1024 * 1024
        self.assertEqual(MemoryGuard.calculate_safe_guest_ram(available), expected)

    def test_safe_ram_floor_applied_on_low_memory(self):
        """Available 400MB is clamped to 1024MB safe floor preventing underflow."""
        available = 400 * 1024 * 1024
        self.assertEqual(MemoryGuard.calculate_safe_guest_ram(available), MemoryGuard.MIN_SAFE_FLOOR_BYTES)

    def test_safe_ram_exact_safety_buffer_boundary(self):
        """Available exactly equal to 450MB safety buffer returns 1024MB safe floor."""
        available = MemoryGuard.SAFETY_BUFFER_BYTES
        self.assertEqual(MemoryGuard.calculate_safe_guest_ram(available), MemoryGuard.MIN_SAFE_FLOOR_BYTES)

    def test_safe_ram_zero_and_negative_available(self):
        """Available 0 or negative bytes safely clamped to 1024MB floor."""
        self.assertEqual(MemoryGuard.calculate_safe_guest_ram(0), MemoryGuard.MIN_SAFE_FLOOR_BYTES)
        self.assertEqual(MemoryGuard.calculate_safe_guest_ram(-500 * 1024 * 1024), MemoryGuard.MIN_SAFE_FLOOR_BYTES)

    def test_safe_ram_near_floor_boundary(self):
        """Available 1474MB (1474MB - 450MB = 1024MB) returns exactly 1024MB."""
        available = 1474 * 1024 * 1024
        self.assertEqual(MemoryGuard.calculate_safe_guest_ram(available), MemoryGuard.MIN_SAFE_FLOOR_BYTES)

    def test_safe_ram_high_spec_64gb(self):
        """High-memory devices (e.g. 64GB host) allocate (64GB - 450MB)."""
        available = 64 * 1024 * 1024 * 1024
        expected = available - MemoryGuard.SAFETY_BUFFER_BYTES
        self.assertEqual(MemoryGuard.calculate_safe_guest_ram(available), expected)


class TestMemoryGuardMemoryPressure(unittest.TestCase):
    """Unit and mock tests for Darwin memory pressure events and QMP VirtIO ballooning."""

    def test_pressure_normal_returns_none(self):
        """Normal memory pressure returns None (no QMP ballooning command needed)."""
        res_str = MemoryGuard.handle_memory_pressure("normal", 4000 * 1024 * 1024)
        self.assertIsNone(res_str)

        res_enum = MemoryGuard.handle_memory_pressure(MemoryPressureLevel.NORMAL, 4000 * 1024 * 1024)
        self.assertIsNone(res_enum)

    def test_pressure_warning_triggers_balloon(self):
        """Warning pressure dispatches QMP balloon command with safe guest RAM value."""
        available = 3000 * 1024 * 1024
        expected_ram = (3000 - 450) * 1024 * 1024
        cmd = MemoryGuard.handle_memory_pressure("warning", available)
        self.assertIsNotNone(cmd)
        self.assertEqual(cmd["execute"], "balloon")
        self.assertEqual(cmd["arguments"]["value"], expected_ram)

    def test_pressure_critical_triggers_emergency_balloon(self):
        """Critical pressure aggressively deflates guest RAM to safe RAM // 2, clamped to safe floor."""
        # Case 1: 4000MB available -> safe 3550MB -> critical half = 1775MB (> 1024MB floor)
        available = 4000 * 1024 * 1024
        safe_ram = (4000 - 450) * 1024 * 1024
        expected_critical = safe_ram // 2
        cmd = MemoryGuard.handle_memory_pressure("critical", available)
        self.assertIsNotNone(cmd)
        self.assertEqual(cmd["execute"], "balloon")
        self.assertEqual(cmd["arguments"]["value"], expected_critical)

        # Case 2: 1500MB available -> safe 1050MB -> half = 525MB -> clamped to 1024MB floor
        cmd_low = MemoryGuard.handle_memory_pressure("critical", 1500 * 1024 * 1024)
        self.assertEqual(cmd_low["arguments"]["value"], MemoryGuard.MIN_SAFE_FLOOR_BYTES)

    def test_pressure_enum_and_case_insensitivity(self):
        """Pressure level parsing handles uppercase, lowercase, and Enum instances."""
        cmd1 = MemoryGuard.handle_memory_pressure(MemoryPressureLevel.WARNING, 3000 * 1024 * 1024)
        cmd2 = MemoryGuard.handle_memory_pressure("WARNING", 3000 * 1024 * 1024)
        cmd3 = MemoryGuard.handle_memory_pressure("Warning", 3000 * 1024 * 1024)
        self.assertEqual(cmd1, cmd2)
        self.assertEqual(cmd2, cmd3)

    def test_pressure_unknown_level_raises_value_error(self):
        """Unknown memory pressure level raises ValueError."""
        with self.assertRaises(ValueError):
            MemoryGuard.handle_memory_pressure("catastrophic", 3000 * 1024 * 1024)
        with self.assertRaises(ValueError):
            MemoryGuard.handle_memory_pressure("extreme", 3000 * 1024 * 1024)

    def test_pressure_stateful_history_recording(self):
        """Stateful instance records on_pressure_event in pressure_history."""
        guard = MemoryGuard()
        self.assertEqual(len(guard.pressure_history), 0)

        guard.on_pressure_event("warning", 3000 * 1024 * 1024)
        self.assertEqual(len(guard.pressure_history), 1)
        self.assertEqual(guard.pressure_history[0]["level"], "warning")
        self.assertEqual(guard.last_available_bytes, 3000 * 1024 * 1024)

        guard.on_pressure_event("normal", 3500 * 1024 * 1024)
        self.assertEqual(len(guard.pressure_history), 2)
        self.assertIsNone(guard.pressure_history[1]["command"])


class TestMemoryGuardAutoPause(unittest.TestCase):
    """Unit and mock tests for 90% Jetsam emergency danger threshold and VM pause/resume."""

    def test_auto_pause_below_threshold(self):
        """Usage below 90% of memory ceiling does not trigger emergency pause."""
        ceiling = 1000 * 1024 * 1024
        # 85%
        self.assertFalse(MemoryGuard.check_jetsam_emergency(int(ceiling * 0.85), ceiling))
        # 89.9%
        self.assertFalse(MemoryGuard.check_jetsam_emergency(int(ceiling * 0.899), ceiling))

    def test_auto_pause_at_exact_90_percent(self):
        """Usage at exactly 90.0% triggers emergency pause."""
        ceiling = 1000 * 1024 * 1024
        self.assertTrue(MemoryGuard.check_jetsam_emergency(int(ceiling * 0.90), ceiling))

    def test_auto_pause_above_threshold(self):
        """Usage above 90% triggers emergency pause."""
        ceiling = 1000 * 1024 * 1024
        self.assertTrue(MemoryGuard.check_jetsam_emergency(int(ceiling * 0.95), ceiling))
        self.assertTrue(MemoryGuard.check_jetsam_emergency(int(ceiling * 1.10), ceiling))

    def test_auto_pause_zero_ceiling_safe(self):
        """Ceiling <= 0 returns True (emergency state) safely without ZeroDivisionError."""
        self.assertTrue(MemoryGuard.check_jetsam_emergency(100, 0))
        self.assertTrue(MemoryGuard.check_jetsam_emergency(100, -1000))

    def test_auto_pause_qmp_stop_and_resume_cont(self):
        """emergency_auto_pause generates QMP stop; resume_vm generates QMP cont."""
        stop_cmd = MemoryGuard.emergency_auto_pause()
        self.assertEqual(stop_cmd, {"execute": "stop"})

        guard = MemoryGuard()
        resume_cmd = guard.resume_vm()
        self.assertEqual(resume_cmd, {"execute": "cont"})

    def test_auto_pause_stateful_tracking(self):
        """update_usage properly sets and clears is_emergency_paused."""
        guard = MemoryGuard()
        self.assertFalse(guard.is_emergency_paused)

        # Trigger emergency
        is_emergency = guard.update_usage(950 * 1024 * 1024, 1000 * 1024 * 1024)
        self.assertTrue(is_emergency)
        self.assertTrue(guard.is_emergency_paused)

        # Resume
        res = guard.resume_vm()
        self.assertEqual(res["execute"], "cont")
        self.assertFalse(guard.is_emergency_paused)

    def test_qmp_command_dataclass(self):
        """QMPCommand dataclass serializes with or without arguments."""
        c1 = QMPCommand(execute="stop")
        self.assertEqual(c1.to_dict(), {"execute": "stop"})

        c2 = QMPCommand(execute="balloon", arguments={"value": 1024})
        self.assertEqual(c2.to_dict(), {"execute": "balloon", "arguments": {"value": 1024}})


if __name__ == "__main__":
    unittest.main()
