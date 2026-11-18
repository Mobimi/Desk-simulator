#!/usr/bin/env python3
"""
Unit tests validating Runtime Memory Monitor Jetsam threshold logic,
ceiling calculations, and Thermal Monitor boost state transitions.
"""

import unittest
from pathlib import Path

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent.parent


class MockJetsamEvaluator:
    """Python reference logic mirroring RuntimeMemoryMonitor.swift."""

    @staticmethod
    def calculate_safe_ceiling(physical_mem_mb: int, has_increased_memory: bool, has_extended_va: bool) -> int:
        ratio = 0.80 if (has_increased_memory and has_extended_va) else 0.50
        raw_limit = int(physical_mem_mb * ratio)
        safe_ceiling = max(1024, raw_limit - 450)
        return safe_ceiling

    @staticmethod
    def evaluate_danger_zone(current_usage_mb: int, ceiling_mb: int) -> str:
        if ceiling_mb <= 0:
            return "danger"
        ratio = current_usage_mb / ceiling_mb
        if ratio < 0.75:
            return "safe"
        elif ratio < 0.90:
            return "caution"
        else:
            return "danger"


class MockThermalBoostCoordinator:
    """Python reference logic mirroring ThermalMonitor.swift."""

    def __init__(self):
        self.is_boost_active = False
        self.boost_settled = False

    def begin_boot_boost(self, enabled: bool):
        if enabled:
            self.is_boost_active = True
            self.boost_settled = False
        else:
            self.is_boost_active = False
            self.boost_settled = True

    def on_thermal_state_change(self, state: str):
        # state in ["nominal", "fair", "serious", "critical"]
        if state in ["serious", "critical"]:
            self.is_boost_active = False
            self.boost_settled = True


class TestRuntimeMonitorsLogic(unittest.TestCase):
    """Validates Jetsam thresholds, memory calculations, and thermal coordinator."""

    def test_trollstore_unrestricted_memory_ceiling(self):
        # 6GB device (iPhone 13 Pro / 14 / 15)
        # 6144 * 0.80 = 4915MB, minus 450MB buffer = 4465MB
        ceiling = MockJetsamEvaluator.calculate_safe_ceiling(6144, has_increased_memory=True, has_extended_va=True)
        self.assertEqual(ceiling, 4465)

    def test_sideload_sandboxed_memory_ceiling(self):
        # 6GB device without increased-memory entitlement
        # 6144 * 0.50 = 3072MB, minus 450MB buffer = 2622MB
        ceiling = MockJetsamEvaluator.calculate_safe_ceiling(6144, has_increased_memory=False, has_extended_va=False)
        self.assertEqual(ceiling, 2622)

    def test_safe_floor_clamping(self):
        # Low RAM device (e.g. 2GB)
        # 2048 * 0.50 = 1024, minus 450 = 574 -> clamped to 1024 floor
        ceiling = MockJetsamEvaluator.calculate_safe_ceiling(2048, has_increased_memory=False, has_extended_va=False)
        self.assertEqual(ceiling, 1024)

    def test_jetsam_danger_zone_evaluations(self):
        ceiling = 4000

        # Safe: < 75% (e.g., 2800 / 4000 = 70%)
        self.assertEqual(MockJetsamEvaluator.evaluate_danger_zone(2800, ceiling), "safe")

        # Caution: 75% - 90% (e.g., 3200 / 4000 = 80%)
        self.assertEqual(MockJetsamEvaluator.evaluate_danger_zone(3200, ceiling), "caution")

        # Danger: >= 90% (e.g., 3600 / 4000 = 90%) -> triggers QMP auto-pause
        self.assertEqual(MockJetsamEvaluator.evaluate_danger_zone(3600, ceiling), "danger")
        self.assertEqual(MockJetsamEvaluator.evaluate_danger_zone(3950, ceiling), "danger")

    def test_thermal_boost_settling_on_high_thermal_strain(self):
        coordinator = MockThermalBoostCoordinator()
        coordinator.begin_boot_boost(enabled=True)
        self.assertTrue(coordinator.is_boost_active)
        self.assertFalse(coordinator.boost_settled)

        # Thermal state elevates to 'fair' - boost remains active
        coordinator.on_thermal_state_change("fair")
        self.assertTrue(coordinator.is_boost_active)

        # Thermal state elevates to 'serious' - boost settles immediately
        coordinator.on_thermal_state_change("serious")
        self.assertFalse(coordinator.is_boost_active)
        self.assertTrue(coordinator.boost_settled)

    def test_runtime_memory_monitor_swift_declarations(self):
        """Asserts that currentUsageMB is declared in RuntimeMemoryMonitor.swift."""
        rmm_path = WORKSPACE_ROOT / "Management" / "Runtime" / "RuntimeMemoryMonitor.swift"
        self.assertTrue(rmm_path.is_file(), "RuntimeMemoryMonitor.swift not found")
        content = rmm_path.read_text(encoding="utf-8")
        self.assertIn("currentUsageMB", content, "RuntimeMemoryMonitor.swift must declare currentUsageMB")
        self.assertIn("var currentUsageMB: Int", content, "currentUsageMB must be an Int property")

    def test_thermal_monitor_swift_declarations(self):
        """Asserts that thermalLevel and level are declared in ThermalMonitor.swift."""
        tm_path = WORKSPACE_ROOT / "Management" / "Runtime" / "ThermalMonitor.swift"
        self.assertTrue(tm_path.is_file(), "ThermalMonitor.swift not found")
        content = tm_path.read_text(encoding="utf-8")
        self.assertIn("thermalLevel", content, "ThermalMonitor.swift must declare thermalLevel")
        self.assertIn("var thermalLevel: ThermalAlertLevel", content, "thermalLevel must return ThermalAlertLevel")
        self.assertIn("var level: ThermalAlertLevel", content, "level must be declared")

    def test_pcore_scheduler_protocol_swift_declarations(self):
        """Asserts that transitionState(to:) is declared in PCoreSchedulerProtocol.swift."""
        proto_path = WORKSPACE_ROOT / "Management" / "PCoreScheduler" / "PCoreSchedulerProtocol.swift"
        self.assertTrue(proto_path.is_file(), "PCoreSchedulerProtocol.swift not found")
        content = proto_path.read_text(encoding="utf-8")
        self.assertIn("transitionState(to newState: BootBoostState)", content, "PCoreSchedulerProtocol must declare transitionState(to:)")


if __name__ == "__main__":
    unittest.main()
