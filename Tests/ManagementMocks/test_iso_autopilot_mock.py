#!/usr/bin/env python3
"""
Unit and Mock Tests for ISO Auto-Pilot (ISOAutoPilot).
Verifies:
- ISO boot header inspection and guest OS identification (Windows 11, Windows 10, Linux Ubuntu)
- VirtIO driver auto-injection configuration generation
- Windows 11 hardware check bypass XML (autounattend.xml) synthesis and XML injection immunity
"""

import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

# Workspace root resolution
WORKSPACE_ROOT = Path(__file__).resolve().parent.parent.parent
if str(WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_ROOT))

from Management.ISOAutoPilot.iso_autopilot import ISOAutoPilot, OperatingSystemType


class TestISOAutoPilotOSDetection(unittest.TestCase):
    """Unit tests for guest operating system identification from ISO header bytes."""

    def test_detect_windows_11_signature(self):
        """Standard ISO 9660 primary volume descriptor with Windows 11 signature."""
        header1 = b"\x00" * 32768 + b"CD001 MICROSOFT WINDOWS 11 PROFESSIONAL INSTALLATION MEDIA"
        self.assertEqual(
            ISOAutoPilot.identify_operating_system(header1),
            OperatingSystemType.WINDOWS_11,
        )

        header2 = b"\x00" * 2048 + b"WIN11_X64_EN-US"
        self.assertEqual(
            ISOAutoPilot.identify_operating_system(header2),
            OperatingSystemType.WINDOWS_11,
        )

    def test_detect_windows_10_signature(self):
        """Standard ISO 9660 primary volume descriptor with Windows 10 signature."""
        header1 = b"\x00" * 32768 + b"CD001 MICROSOFT WINDOWS 10 HOME INSTALLATION MEDIA"
        self.assertEqual(
            ISOAutoPilot.identify_operating_system(header1),
            OperatingSystemType.WINDOWS_10,
        )

        header2 = b"\x00" * 2048 + b"WIN10_PRO_X64"
        self.assertEqual(
            ISOAutoPilot.identify_operating_system(header2),
            OperatingSystemType.WINDOWS_10,
        )

    def test_detect_linux_ubuntu_signature(self):
        """Standard ISO 9660 primary volume descriptor with Ubuntu/Linux signature."""
        header1 = b"\x00" * 32768 + b"CD001 UBUNTU 22.04 LTS DESKTOP LIVE"
        self.assertEqual(
            ISOAutoPilot.identify_operating_system(header1),
            OperatingSystemType.LINUX_UBUNTU,
        )

        header2 = b"\x00" * 2048 + b"ARCH_LINUX_2024"
        self.assertEqual(
            ISOAutoPilot.identify_operating_system(header2),
            OperatingSystemType.LINUX_UBUNTU,
        )

    def test_detect_utf16_null_interleaved_win11(self):
        """Joliet/UDF UTF-16 volume descriptor containing null-interleaved characters."""
        utf16_bytes = "MICROSOFT WINDOWS 11".encode("utf-16le")
        self.assertEqual(
            ISOAutoPilot.identify_operating_system(utf16_bytes),
            OperatingSystemType.WINDOWS_11,
        )

        utf16_short = "CD001 WIN11".encode("utf-16le")
        self.assertEqual(
            ISOAutoPilot.identify_operating_system(utf16_short),
            OperatingSystemType.WINDOWS_11,
        )

    def test_detect_utf16_null_interleaved_win10(self):
        """Joliet/UDF UTF-16 volume descriptor for Windows 10."""
        utf16_bytes = "MICROSOFT WINDOWS 10".encode("utf-16le")
        self.assertEqual(
            ISOAutoPilot.identify_operating_system(utf16_bytes),
            OperatingSystemType.WINDOWS_10,
        )

    def test_detect_empty_header_returns_unknown(self):
        """Empty buffer returns OperatingSystemType.UNKNOWN."""
        self.assertEqual(ISOAutoPilot.identify_operating_system(b""), OperatingSystemType.UNKNOWN)

    def test_detect_short_header_returns_unknown(self):
        """Header shorter than 16 bytes returns OperatingSystemType.UNKNOWN."""
        self.assertEqual(ISOAutoPilot.identify_operating_system(b"SHORT_DATA"), OperatingSystemType.UNKNOWN)

    def test_detect_random_noise_returns_unknown(self):
        """Random binary stream without OS signature returns OperatingSystemType.UNKNOWN."""
        noise = bytes([i % 256 for i in range(1024)])
        self.assertEqual(ISOAutoPilot.identify_operating_system(noise), OperatingSystemType.UNKNOWN)

    def test_inspect_file_missing_returns_unknown(self):
        """Non-existent ISO file path returns UNKNOWN without raising unhandled exception."""
        pilot = ISOAutoPilot()
        res = pilot.inspect_file("/non/existent/path/virtual.iso")
        self.assertEqual(res, OperatingSystemType.UNKNOWN)
        self.assertEqual(pilot.last_detected_os, OperatingSystemType.UNKNOWN)

    def test_inspect_file_real_temporary(self):
        """inspect_file reads sample bytes from actual disk file."""
        pilot = ISOAutoPilot()
        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            tmp.write(b"\x00" * 32768 + b"CD001 MICROSOFT WINDOWS 11 PRO")
            tmp_path = tmp.name

        try:
            detected = pilot.inspect_file(tmp_path)
            self.assertEqual(detected, OperatingSystemType.WINDOWS_11)
            self.assertEqual(pilot.last_detected_os, OperatingSystemType.WINDOWS_11)
        finally:
            Path(tmp_path).unlink(missing_ok=True)


class TestISOAutoPilotVirtIOInjection(unittest.TestCase):
    """Unit tests for VirtIO driver auto-injection configuration generation."""

    def test_virtio_config_win11_drivers_included(self):
        """Windows 11 guest configuration includes all required storage, network, and balloon drivers."""
        cfg = ISOAutoPilot.generate_virtio_injection_config(OperatingSystemType.WINDOWS_11)
        self.assertTrue(cfg["inject_drivers"])
        self.assertFalse(cfg["native_drivers"])
        self.assertEqual(cfg["target_os"], "WINDOWS_11")

        required_drivers = ["viostor", "netkvm", "balloon", "vioscsi", "qxl"]
        for drv in required_drivers:
            self.assertIn(drv, cfg["drivers"])

    def test_virtio_config_win11_drive_parameter(self):
        """Windows 11 configuration defines CD-ROM drive parameter for virtio-win.iso."""
        cfg = ISOAutoPilot.generate_virtio_injection_config(OperatingSystemType.WINDOWS_11)
        expected_drive = "-drive file=virtio-win.iso,media=cdrom,readonly=on"
        self.assertEqual(cfg["drive_param"], expected_drive)

    def test_virtio_config_win10_parity(self):
        """Windows 10 guest receives identical VirtIO driver configuration as Windows 11."""
        cfg = ISOAutoPilot.generate_virtio_injection_config(OperatingSystemType.WINDOWS_10)
        self.assertTrue(cfg["inject_drivers"])
        self.assertIn("viostor", cfg["drivers"])
        self.assertEqual(cfg["drive_param"], "-drive file=virtio-win.iso,media=cdrom,readonly=on")

    def test_virtio_config_linux_native_kernel(self):
        """Linux guests use in-kernel drivers and do not require injected driver CD-ROM."""
        cfg = ISOAutoPilot.generate_virtio_injection_config(OperatingSystemType.LINUX_UBUNTU)
        self.assertFalse(cfg["inject_drivers"])
        self.assertTrue(cfg["native_drivers"])
        self.assertEqual(cfg["drive_param"], "")
        self.assertIn("virtio_pci", cfg["drivers"])
        self.assertIn("virtio_blk", cfg["drivers"])
        self.assertIn("virtio_net", cfg["drivers"])

    def test_virtio_config_unknown_empty(self):
        """Unknown OS disables driver injection with empty driver list."""
        cfg = ISOAutoPilot.generate_virtio_injection_config(OperatingSystemType.UNKNOWN)
        self.assertFalse(cfg["inject_drivers"])
        self.assertFalse(cfg["native_drivers"])
        self.assertEqual(cfg["drivers"], [])
        self.assertEqual(cfg["drive_param"], "")

    def test_virtio_config_string_and_enum_compatibility(self):
        """generate_virtio_injection_config accepts enum, uppercase string, and alias strings."""
        cfg_enum = ISOAutoPilot.generate_virtio_injection_config(OperatingSystemType.WINDOWS_11)
        cfg_str = ISOAutoPilot.generate_virtio_injection_config("WINDOWS_11")
        cfg_alias = ISOAutoPilot.generate_virtio_injection_config("WIN11")
        self.assertEqual(cfg_enum["drivers"], cfg_str["drivers"])
        self.assertEqual(cfg_str["drivers"], cfg_alias["drivers"])


class TestISOAutoPilotWin11Bypass(unittest.TestCase):
    """Unit and mock tests for Windows 11 autounattend.xml answer file generation."""

    def test_win11_bypass_valid_xml_structure(self):
        """Generated XML is well-formed, parses cleanly, and has the unattend root element."""
        xml_str = ISOAutoPilot.generate_windows11_bypass_xml("TestUser")
        root = ET.fromstring(xml_str)
        self.assertTrue(root.tag.endswith("unattend"))

    def test_win11_bypass_tpm_registry_present(self):
        """XML answer file contains BypassTPMCheck registry bypass."""
        xml_str = ISOAutoPilot.generate_windows11_bypass_xml()
        self.assertIn("BypassTPMCheck", xml_str)

    def test_win11_bypass_secureboot_registry_present(self):
        """XML answer file contains BypassSecureBootCheck registry bypass."""
        xml_str = ISOAutoPilot.generate_windows11_bypass_xml()
        self.assertIn("BypassSecureBootCheck", xml_str)

    def test_win11_bypass_ram_registry_present(self):
        """XML answer file contains BypassRAMCheck registry bypass."""
        xml_str = ISOAutoPilot.generate_windows11_bypass_xml()
        self.assertIn("BypassRAMCheck", xml_str)

    def test_win11_bypass_cpu_and_storage_present(self):
        """XML answer file contains BypassCPUCheck and BypassStorageCheck registry bypasses."""
        xml_str = ISOAutoPilot.generate_windows11_bypass_xml()
        self.assertIn("BypassCPUCheck", xml_str)
        self.assertIn("BypassStorageCheck", xml_str)

    def test_win11_bypass_eula_accepted(self):
        """XML answer file automatically accepts Microsoft EULA."""
        xml_str = ISOAutoPilot.generate_windows11_bypass_xml()
        self.assertIn("<AcceptEula>true</AcceptEula>", xml_str)

    def test_win11_bypass_custom_username_embedded(self):
        """Custom username is placed inside the local administrator account tag."""
        xml_str = ISOAutoPilot.generate_windows11_bypass_xml("Alice")
        root = ET.fromstring(xml_str)
        name_nodes = [elem for elem in root.iter() if elem.tag.endswith("Name")]
        self.assertTrue(any(node.text == "Alice" for node in name_nodes))

    def test_win11_bypass_default_username_fallback(self):
        """Empty, whitespace, or None username defaults to 'DeskUser'."""
        for val in ["", "   ", None]:
            xml_str = ISOAutoPilot.generate_windows11_bypass_xml(val)  # type: ignore
            root = ET.fromstring(xml_str)
            name_nodes = [elem for elem in root.iter() if elem.tag.endswith("Name")]
            self.assertTrue(any(node.text == "DeskUser" for node in name_nodes))

    def test_win11_bypass_xml_entity_escaping(self):
        """Special characters &, <, >, \", ' are escaped properly and parse cleanly without syntax errors."""
        malicious = "John&Co<Hack>\"Admin'Test"
        xml_str = ISOAutoPilot.generate_windows11_bypass_xml(malicious)

        # Confirm XML parser parses successfully without ParseError
        root = ET.fromstring(xml_str)
        name_nodes = [elem for elem in root.iter() if elem.tag.endswith("Name")]
        # In ElementTree, the parsed text contains the unescaped characters
        self.assertTrue(any(node.text == malicious for node in name_nodes))

    def test_win11_bypass_control_characters_stripped(self):
        """ASCII control characters (\x00, \r, \n, \t, \x1f, \x7f) are stripped to prevent corrupt XML."""
        tainted = "Desk\x00\r\n\tUser\x1f\x7f"
        xml_str = ISOAutoPilot.generate_windows11_bypass_xml(tainted)
        root = ET.fromstring(xml_str)
        name_nodes = [elem for elem in root.iter() if elem.tag.endswith("Name")]
        self.assertTrue(any(node.text == "DeskUser" for node in name_nodes))


if __name__ == "__main__":
    unittest.main()
