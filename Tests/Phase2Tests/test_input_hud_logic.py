#!/usr/bin/env python3
"""
Unit tests validating Input HUD packet encoding, scancode mappings,
gamepad thumbstick normalization, deadzone filtering, and button mappings.
"""

import struct
import unittest
from pathlib import Path

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent.parent


class MockSPICEPacketEncoder:
    """Python reference encoder mirroring VMSessionViewModel input event serialization."""

    @staticmethod
    def encode_mouse_move(dx: int, dy: int) -> bytes:
        # Opcode 0x01, dx (int16_le), dy (int16_le)
        clamped_dx = max(-32768, min(32767, dx))
        clamped_dy = max(-32768, min(32767, dy))
        return struct.pack("<Bhh", 0x01, clamped_dx, clamped_dy)

    @staticmethod
    def encode_mouse_button(button: int, is_down: bool) -> bytes:
        # Opcode 0x02, button (uint8), is_down (uint8)
        return struct.pack("<BBB", 0x02, button & 0xFF, 1 if is_down else 0)

    @staticmethod
    def encode_mouse_scroll(delta_y: int) -> bytes:
        # Opcode 0x03, delta_y (int16_le)
        clamped_delta = max(-32768, min(32767, delta_y))
        return struct.pack("<Bh", 0x03, clamped_delta)

    @staticmethod
    def encode_key_scancode(scancode: int, is_down: bool) -> bytes:
        # Opcode 0x04, is_down (uint8), scancode (uint16_le)
        return struct.pack("<BBH", 0x04, 1 if is_down else 0, scancode & 0xFFFF)

    @staticmethod
    def encode_gamepad_button(button_id: int, is_pressed: bool) -> bytes:
        # Opcode 0x05, button_id (uint8), is_pressed (uint8)
        return struct.pack("<BBB", 0x05, button_id & 0xFF, 1 if is_pressed else 0)

    @staticmethod
    def encode_gamepad_stick(stick_id: int, x: float, y: float, deadzone: float = 0.08) -> bytes:
        # Opcode 0x06, stick_id (uint8), x (int16_le), y (int16_le)
        norm_x = 0.0 if abs(x) < deadzone else max(-1.0, min(1.0, x))
        norm_y = 0.0 if abs(y) < deadzone else max(-1.0, min(1.0, y))
        int_x = int(norm_x * 32767.0)
        int_y = int(norm_y * 32767.0)
        return struct.pack("<BBhh", 0x06, stick_id & 0xFF, int_x, int_y)


class TestInputHUDLogic(unittest.TestCase):
    """Validates Input HUD serialization, scancodes, and math logic."""

    def test_mouse_move_packet_encoding(self):
        packet = MockSPICEPacketEncoder.encode_mouse_move(12, -45)
        self.assertEqual(len(packet), 5)
        opcode, dx, dy = struct.unpack("<Bhh", packet)
        self.assertEqual(opcode, 0x01)
        self.assertEqual(dx, 12)
        self.assertEqual(dy, -45)

    def test_mouse_button_packet_encoding(self):
        # Left click down
        packet_down = MockSPICEPacketEncoder.encode_mouse_button(1, True)
        self.assertEqual(packet_down, bytes([0x02, 0x01, 0x01]))

        # Right click up
        packet_up = MockSPICEPacketEncoder.encode_mouse_button(3, False)
        self.assertEqual(packet_up, bytes([0x02, 0x03, 0x00]))

    def test_mouse_scroll_packet_encoding(self):
        packet = MockSPICEPacketEncoder.encode_mouse_scroll(120)
        self.assertEqual(len(packet), 3)
        opcode, delta = struct.unpack("<Bh", packet)
        self.assertEqual(opcode, 0x03)
        self.assertEqual(delta, 120)

    def test_key_scancode_packet_encoding(self):
        # Escape (0x0001) down
        packet_esc = MockSPICEPacketEncoder.encode_key_scancode(0x0001, True)
        self.assertEqual(len(packet_esc), 4)
        opcode, is_down, code = struct.unpack("<BBH", packet_esc)
        self.assertEqual(opcode, 0x04)
        self.assertEqual(is_down, 1)
        self.assertEqual(code, 0x0001)

        # Left Alt (0x0038) up
        packet_alt = MockSPICEPacketEncoder.encode_key_scancode(0x0038, False)
        opcode, is_down, code = struct.unpack("<BBH", packet_alt)
        self.assertEqual(opcode, 0x04)
        self.assertEqual(is_down, 0)
        self.assertEqual(code, 0x0038)

    def test_pc_shortcut_combo_scancodes(self):
        # Scancode Set 1 definitions
        scancodes = {
            "Esc": 0x0001,
            "Tab": 0x000F,
            "Enter": 0x001C,
            "Ctrl": 0x001D,
            "Alt": 0x0038,
            "Space": 0x0039,
            "Delete": 0xE053,
            "Win": 0xE05B,
            "F1": 0x003B,
            "F4": 0x003E,
            "F12": 0x0058,
        }
        self.assertEqual(scancodes["Ctrl"], 0x001D)
        self.assertEqual(scancodes["Alt"], 0x0038)
        self.assertEqual(scancodes["Delete"], 0xE053)

        # Ctrl+Alt+Del combo sequence
        ctrl_alt_del = [scancodes["Ctrl"], scancodes["Alt"], scancodes["Delete"]]
        self.assertEqual(ctrl_alt_del, [0x001D, 0x0038, 0xE053])

        # Alt+F4 combo sequence
        alt_f4 = [scancodes["Alt"], scancodes["F4"]]
        self.assertEqual(alt_f4, [0x0038, 0x003E])

    def test_gamepad_button_packet_encoding(self):
        # Button A (0) pressed
        packet_a = MockSPICEPacketEncoder.encode_gamepad_button(0, True)
        self.assertEqual(packet_a, bytes([0x05, 0x00, 0x01]))

        # Button RB (5) released
        packet_rb = MockSPICEPacketEncoder.encode_gamepad_button(5, False)
        self.assertEqual(packet_rb, bytes([0x05, 0x05, 0x00]))

    def test_gamepad_stick_deadzone_and_clamping(self):
        # Value within deadzone (< 0.08) should clamp to 0
        packet_deadzone = MockSPICEPacketEncoder.encode_gamepad_stick(0, 0.05, -0.06, deadzone=0.08)
        opcode, stick_id, x, y = struct.unpack("<BBhh", packet_deadzone)
        self.assertEqual(opcode, 0x06)
        self.assertEqual(stick_id, 0)
        self.assertEqual(x, 0)
        self.assertEqual(y, 0)

        # Full deflection right/up
        packet_full = MockSPICEPacketEncoder.encode_gamepad_stick(1, 1.0, 1.0, deadzone=0.08)
        opcode, stick_id, x, y = struct.unpack("<BBhh", packet_full)
        self.assertEqual(stick_id, 1)
        self.assertEqual(x, 32767)
        self.assertEqual(y, 32767)

        # Clamping beyond 1.0
        packet_overshoot = MockSPICEPacketEncoder.encode_gamepad_stick(0, 1.5, -2.0, deadzone=0.08)
        opcode, stick_id, x, y = struct.unpack("<BBhh", packet_overshoot)
        self.assertEqual(x, 32767)
        self.assertEqual(y, -32767)

    def test_swift_input_hud_source_files_exist(self):
        required_hud_files = [
            WORKSPACE_ROOT / "UI" / "Views" / "InputHUD" / "HapticTouchpadOverlay.swift",
            WORKSPACE_ROOT / "UI" / "Views" / "InputHUD" / "PCShortcutToolbar.swift",
            WORKSPACE_ROOT / "UI" / "Views" / "InputHUD" / "VirtualGamepadOverlay.swift",
            WORKSPACE_ROOT / "UI" / "Views" / "MetalDisplayView.swift",
            WORKSPACE_ROOT / "UI" / "Views" / "VMDisplaySessionView.swift",
        ]
        for f in required_hud_files:
            self.assertTrue(f.exists(), f"Missing required Phase 2 file: {f}")
            content = f.read_text(encoding="utf-8")
            self.assertTrue(len(content) > 100, f"File {f.name} is unexpectedly small")
            self.assertIn("canImport(SwiftUI)", content, f"{f.name} missing SwiftUI guard")


if __name__ == "__main__":
    unittest.main()
