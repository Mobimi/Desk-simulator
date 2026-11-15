#!/usr/bin/env python3
"""
Unit and Mock Tests for P-Core Scheduler (PCoreScheduler).
Verifies:
- Physical P-core topology discovery and vCPU core affinity pinning (eliminating E-core stutter)
- vCPU bounds clamping within [1, p_cores]
- Darwin Mach thread QoS elevation (User Interactive 0x21, User Initiated 0x19, Background 0x09)
- Dynamic Boot Boost state machine transitions and 120-second timeout de-escalation
"""

import sys
import time
import unittest
from pathlib import Path

# Workspace root resolution
WORKSPACE_ROOT = Path(__file__).resolve().parent.parent.parent
if str(WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_ROOT))

from Management.PCoreScheduler.pcore_scheduler import BootBoostState, PCoreScheduler


class TestPCoreSchedulerTopology(unittest.TestCase):
    """Unit tests for physical P-core discovery and topology pinning."""

    def test_default_vcpus_matches_physical_pcores(self):
        """Default vCPUs matches physical P-core count on modern Apple Silicon (2 cores)."""
        self.assertEqual(PCoreScheduler.get_default_vcpus(), 2)
        self.assertEqual(PCoreScheduler.get_physical_pcore_count(), 2)
        self.assertEqual(PCoreScheduler.DEFAULT_VCPUS, 2)

    def test_assign_topology_default(self):
        """Default assignment creates 2 vCPUs pinned to physical P-cores 0 and 1."""
        topology = PCoreScheduler.assign_topology(2)
        self.assertEqual(topology["vcpus"], 2)
        self.assertEqual(topology["pcore_affinity"], [0, 1])

    def test_assign_topology_single_core(self):
        """Requesting 1 physical core creates 1 vCPU with affinity [0]."""
        topology = PCoreScheduler.assign_topology(1)
        self.assertEqual(topology["vcpus"], 1)
        self.assertEqual(topology["pcore_affinity"], [0])

    def test_assign_topology_clamped_to_max_pcores(self):
        """Requesting 8 cores clamps to maximum mobile P-core default (2 cores)."""
        topology = PCoreScheduler.assign_topology(8)
        self.assertEqual(topology["vcpus"], 2)
        self.assertEqual(topology["pcore_affinity"], [0, 1])

    def test_assign_topology_zero_pcores(self):
        """Zero cores safely clamps to minimum 1 vCPU."""
        topology = PCoreScheduler.assign_topology(0)
        self.assertEqual(topology["vcpus"], 1)
        self.assertEqual(topology["pcore_affinity"], [0])

    def test_clamp_vcpus_excessive_request(self):
        """clamp_vcpus caps requested vCPUs at physical P-core count."""
        self.assertEqual(PCoreScheduler.clamp_vcpus(requested=8, p_cores=2), 2)
        self.assertEqual(PCoreScheduler.clamp_vcpus(requested=16, p_cores=2), 2)

    def test_clamp_vcpus_negative_and_zero(self):
        """clamp_vcpus floors 0 or negative requested vCPUs at minimum 1."""
        self.assertEqual(PCoreScheduler.clamp_vcpus(requested=0, p_cores=2), 1)
        self.assertEqual(PCoreScheduler.clamp_vcpus(requested=-4, p_cores=2), 1)

    def test_clamp_vcpus_custom_pcores(self):
        """clamp_vcpus respects higher physical P-core limits when specified."""
        self.assertEqual(PCoreScheduler.clamp_vcpus(requested=3, p_cores=4), 3)
        self.assertEqual(PCoreScheduler.clamp_vcpus(requested=6, p_cores=4), 4)

    def test_instance_initialization_defaults(self):
        """PCoreScheduler instance initializes with expected attributes."""
        scheduler = PCoreScheduler(physical_p_cores=2)
        self.assertEqual(scheduler.p_cores, 2)
        self.assertEqual(scheduler.state, BootBoostState.IDLE)
        self.assertIsNone(scheduler.boot_start_time)


class TestPCoreSchedulerQoS(unittest.TestCase):
    """Unit tests for Darwin Mach thread QoS elevation and priority hierarchies."""

    def test_qos_constants_exact_values(self):
        """Darwin Mach QoS class hexadecimal integer constants."""
        self.assertEqual(PCoreScheduler.QOS_CLASS_USER_INTERACTIVE, 0x21)  # 33
        self.assertEqual(PCoreScheduler.QOS_CLASS_USER_INITIATED, 0x19)    # 25
        self.assertEqual(PCoreScheduler.QOS_CLASS_UTILITY, 0x11)           # 17
        self.assertEqual(PCoreScheduler.QOS_CLASS_BACKGROUND, 0x09)        # 9

    def test_qos_elevation_main_vcpu(self):
        """vCPU thread priority is elevated to USER_INTERACTIVE (0x21)."""
        qos = PCoreScheduler.elevate_qos("vcpu_0", is_vcpu=True)
        self.assertEqual(qos, 0x21)

    def test_qos_elevation_aux_thread(self):
        """Auxiliary threads (e.g. storage/network) receive USER_INITIATED (0x19)."""
        qos = PCoreScheduler.elevate_qos("disk_io", is_vcpu=False)
        self.assertEqual(qos, 0x19)

    def test_qos_demote_background(self):
        """Demoted or idle auxiliary threads receive BACKGROUND (0x09)."""
        qos = PCoreScheduler.demote_qos_background("telemetry_logger")
        self.assertEqual(qos, 0x09)

    def test_qos_priority_order(self):
        """Verifies strictly decreasing priority order across Darwin QoS classes."""
        self.assertGreater(
            PCoreScheduler.QOS_CLASS_USER_INTERACTIVE,
            PCoreScheduler.QOS_CLASS_USER_INITIATED,
        )
        self.assertGreater(
            PCoreScheduler.QOS_CLASS_USER_INITIATED,
            PCoreScheduler.QOS_CLASS_UTILITY,
        )
        self.assertGreater(
            PCoreScheduler.QOS_CLASS_UTILITY,
            PCoreScheduler.QOS_CLASS_BACKGROUND,
        )

    def test_set_thread_interactive_qos_simulation(self):
        """set_thread_interactive_qos returns True."""
        self.assertTrue(PCoreScheduler.set_thread_interactive_qos())

    def test_thread_registry_tracking(self):
        """register_thread tracks elevated threads and their QoS class in thread_registry."""
        scheduler = PCoreScheduler()
        qos_vcpu0 = scheduler.register_thread("vcpu_0", is_vcpu=True)
        qos_vcpu1 = scheduler.register_thread("vcpu_1", is_vcpu=True)
        qos_spice = scheduler.register_thread("spice_io", is_vcpu=False)

        self.assertEqual(qos_vcpu0, 0x21)
        self.assertEqual(qos_vcpu1, 0x21)
        self.assertEqual(qos_spice, 0x19)
        self.assertEqual(scheduler.thread_registry["vcpu_0"], 0x21)
        self.assertEqual(scheduler.thread_registry["spice_io"], 0x19)


class TestPCoreSchedulerBootBoost(unittest.TestCase):
    """Unit and mock tests for Dynamic Boot Boost state machine and timeout management."""

    def test_boot_boost_timeout_constant(self):
        """Boot boost timeout is configured to 120 seconds."""
        self.assertEqual(PCoreScheduler.BOOT_BOOST_TIMEOUT_SECONDS, 120)

    def test_boot_boost_initial_state(self):
        """Initial state machine state is IDLE."""
        scheduler = PCoreScheduler()
        self.assertEqual(scheduler.state, BootBoostState.IDLE)
        self.assertIsNone(scheduler.boot_start_time)

    def test_boot_boost_start_transition(self):
        """Starting boot transitions state to BOOTING and sets boot_start_time."""
        scheduler = PCoreScheduler()
        scheduler.update_boot_boost_state(is_booting=True)
        self.assertEqual(scheduler.state, BootBoostState.BOOTING)
        self.assertIsNotNone(scheduler.boot_start_time)

    def test_boot_boost_stop_transition(self):
        """Stopping boot transitions state to RUNNING and resets boot_start_time."""
        scheduler = PCoreScheduler()
        scheduler.update_boot_boost_state(is_booting=True)
        scheduler.update_boot_boost_state(is_booting=False)
        self.assertEqual(scheduler.state, BootBoostState.RUNNING)
        self.assertIsNone(scheduler.boot_start_time)

    def test_boot_boost_timeout_not_expired(self):
        """When elapsed time < 120 seconds, timeout has not expired; state remains BOOTING."""
        scheduler = PCoreScheduler()
        scheduler.update_boot_boost_state(is_booting=True)
        # Simulate 60 seconds elapsed
        scheduler.boot_start_time = time.time() - 60.0
        self.assertFalse(scheduler.check_boot_boost_timeout())
        self.assertEqual(scheduler.state, BootBoostState.BOOTING)

    def test_boot_boost_timeout_expired(self):
        """When elapsed time >= 120 seconds, timeout expires; state de-escalates to RUNNING."""
        scheduler = PCoreScheduler()
        scheduler.update_boot_boost_state(is_booting=True)
        # Simulate 121 seconds elapsed
        scheduler.boot_start_time = time.time() - 121.0
        self.assertTrue(scheduler.check_boot_boost_timeout())
        self.assertEqual(scheduler.state, BootBoostState.RUNNING)
        self.assertIsNone(scheduler.boot_start_time)

    def test_boot_boost_timeout_when_not_booting(self):
        """Checking timeout when boot_start_time is None returns False."""
        scheduler = PCoreScheduler()
        self.assertFalse(scheduler.check_boot_boost_timeout())

    def test_state_enum_and_class_mirror_compatibility(self):
        """BootBoostState enum and PCoreScheduler.State class mirror match values."""
        self.assertEqual(BootBoostState.IDLE.value, PCoreScheduler.State.IDLE)
        self.assertEqual(BootBoostState.BOOTING.value, PCoreScheduler.State.BOOTING)
        self.assertEqual(BootBoostState.BOOT_BOOST.value, PCoreScheduler.State.BOOT_BOOST)
        self.assertEqual(BootBoostState.RUNNING.value, PCoreScheduler.State.RUNNING)
        self.assertEqual(BootBoostState.STEADY_STATE.value, PCoreScheduler.State.STEADY_STATE)
        self.assertEqual(BootBoostState.STOPPED.value, PCoreScheduler.State.STOPPED)


if __name__ == "__main__":
    unittest.main()
