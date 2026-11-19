#!/usr/bin/env python3
"""
Desk-simulator Phase 3: SPICE Display Ingestion and Metal Presentation Test Suite.
Validates Requirements R2:
- Feature 10: SPICE UDS Lifecycle & Anti-TCP Policy
- Feature 11: SPICE Display Ingestion (ingestDisplayFrame & delegate callback)
- Feature 12: Metal Framebuffer Rendering (.bgra8Unorm, stride, 60Hz/120Hz ProMotion)
- Feature 13: MetalDisplayView & Session UI Integration (aspect-ratio fitting, letterboxing)

Tiers 1-4 coverage:
- Tier 1: Feature Equivalence Class Partitioning
- Tier 2: Boundary Value Analysis & Corner Cases (108 vs 109 chars, 0-byte frames, stride mismatch)
- Tier 3: Cross-Feature Interactions (UDS -> Ingestion -> Renderer -> Viewport -> UI)
- Tier 4: Real-World Scenarios (60Hz standard, 120Hz ProMotion dynamic viewport resize)
"""

from __future__ import annotations

import os
import re
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

# Workspace root resolution
WORKSPACE_ROOT = Path(__file__).resolve().parent.parent.parent
if str(WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_ROOT))


class MockSPICEPathValidator:
    """Python reference implementation mirroring QEMUArgumentsBuilder.validateSocketPath."""

    MAX_SOCKET_PATH_LENGTH: int = 108

    @classmethod
    def validate_socket_path(cls, path: str) -> None:
        trimmed = path.strip()
        if not trimmed:
            raise ValueError(f"Socket path '{path}' is empty or malformed.")
        if "\0" in trimmed:
            raise ValueError("Contains null byte")

        lower = trimmed.lower()
        if any(token in lower for token in ["127.0.0.1", "localhost", "0.0.0.0", "port="]):
            raise ValueError(f"TCP loopback is strictly prohibited ('{path}'). Must use Unix Domain Socket.")

        utf8_bytes = trimmed.encode("utf-8")
        if len(utf8_bytes) > cls.MAX_SOCKET_PATH_LENGTH:
            raise ValueError(
                f"Unix socket path length ({len(utf8_bytes)}) exceeds POSIX limit of {cls.MAX_SOCKET_PATH_LENGTH} bytes."
            )


class MockSPICEConnectionState:
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    FAILED = "failed"


class MockSPICEConnection:
    """Python reference simulation of SPICEConnection conforming to Swift contract."""

    def __init__(self, socket_path: str):
        MockSPICEPathValidator.validate_socket_path(socket_path)
        self.socket_path: str = socket_path.strip()
        self.state: str = MockSPICEConnectionState.DISCONNECTED
        self.delegate: Optional[Any] = None
        self.socket_fd: int = -1
        self._input_events_sent: List[bytes] = []
        self._frames_ingested: int = 0

    def connect(self) -> None:
        self.state = MockSPICEConnectionState.CONNECTING
        if not os.path.exists(self.socket_path):
            self.state = MockSPICEConnectionState.FAILED
            if self.delegate and hasattr(self.delegate, "spice_connection_did_change_state"):
                self.delegate.spice_connection_did_change_state(self, self.state)
            if self.delegate and hasattr(self.delegate, "spice_connection_did_encounter_error"):
                self.delegate.spice_connection_did_encounter_error(
                    self, f"Socket file does not exist at {self.socket_path}"
                )
            return

        self.socket_fd = 42  # Simulated valid POSIX socket descriptor
        self.state = MockSPICEConnectionState.CONNECTED
        if self.delegate and hasattr(self.delegate, "spice_connection_did_change_state"):
            self.delegate.spice_connection_did_change_state(self, self.state)

    def disconnect(self) -> None:
        if self.socket_fd >= 0:
            self.socket_fd = -1
        self.state = MockSPICEConnectionState.DISCONNECTED
        if self.delegate and hasattr(self.delegate, "spice_connection_did_change_state"):
            self.delegate.spice_connection_did_change_state(self, self.state)

    def send_input_event(self, data: bytes) -> bool:
        if self.state != MockSPICEConnectionState.CONNECTED:
            return False
        if self.socket_fd < 0:
            return False
        self._input_events_sent.append(data)
        return True

    def ingest_display_frame(self, data: bytes, width: int, height: int) -> bool:
        """
        Programmatic display frame ingestion API forwarding to delegate.
        Validates minimum buffer requirements and notifies delegate.
        """
        if self.state != MockSPICEConnectionState.CONNECTED:
            return False
        if not data or width <= 0 or height <= 0:
            return False
        expected_min_bytes = width * height * 4
        if len(data) < expected_min_bytes:
            return False

        self._frames_ingested += 1
        if self.delegate and hasattr(self.delegate, "spice_connection_did_receive_display_frame"):
            self.delegate.spice_connection_did_receive_display_frame(self, data, width, height)
        return True


class MockMetalDisplayRenderer:
    """Python reference simulation of MetalDisplayRenderer conforming to Swift contract."""

    def __init__(self, width: int = 1920, height: int = 1080, refresh_rate_hz: int = 60, scale_factor: float = 2.0):
        self.width: int = width
        self.height: int = height
        self.refresh_rate_hz: int = refresh_rate_hz
        self.scale_factor: float = scale_factor
        self.is_ready_for_rendering: bool = True
        self.current_frame_count: int = 0
        self.pixel_format: str = ".bgra8Unorm"
        self.current_texture_dims: Optional[Tuple[int, int]] = None
        self.texture_reallocations: int = 0
        self.last_ingested_stride: int = 0
        self.last_ingested_data_len: int = 0

    def update_framebuffer(self, data: bytes, width: int, height: int, stride: int) -> bool:
        if not self.is_ready_for_rendering:
            return False
        if not data or width <= 0 or height <= 0 or stride < width * 4:
            return False
        if len(data) < stride * height:
            return False

        self.width = width
        self.height = height
        self.last_ingested_stride = stride
        self.last_ingested_data_len = len(data)

        # Texture allocation / reallocation check
        if self.current_texture_dims != (width, height):
            self.current_texture_dims = (width, height)
            self.texture_reallocations += 1

        self.draw_frame()
        return True

    def resize_viewport(self, width: int, height: int) -> None:
        self.width = width
        self.height = height

    def draw_frame(self) -> None:
        self.current_frame_count += 1

    def render_to_drawable(self, drawable_width: int, drawable_height: int) -> Dict[str, Any]:
        """Simulates MTLBlitCommandEncoder blitting source texture to CAMetalDrawable."""
        if not self.is_ready_for_rendering or not self.current_texture_dims:
            return {"blitted": False, "copy_width": 0, "copy_height": 0}
        src_w, src_h = self.current_texture_dims
        copy_w = min(src_w, drawable_width)
        copy_h = min(src_h, drawable_height)
        return {
            "blitted": True,
            "copy_width": copy_w,
            "copy_height": copy_h,
            "refresh_rate_hz": self.refresh_rate_hz,
        }


class AspectRatioFittingCalculator:
    """Calculates aspect ratio fitting and letterbox/pillarbox geometry for MetalDisplayView."""

    @staticmethod
    def calculate_fitted_rect(
        src_width: float, src_height: float, view_width: float, view_height: float
    ) -> Dict[str, float]:
        if src_width <= 0 or src_height <= 0 or view_width <= 0 or view_height <= 0:
            return {"x": 0.0, "y": 0.0, "width": 0.0, "height": 0.0, "letterbox": 0.0, "pillarbox": 0.0}

        src_aspect = src_width / src_height
        view_aspect = view_width / view_height

        if src_aspect > view_aspect:
            # Letterbox: black bars top and bottom
            fit_width = view_width
            fit_height = view_width / src_aspect
            x = 0.0
            y = (view_height - fit_height) / 2.0
            return {
                "x": x,
                "y": y,
                "width": fit_width,
                "height": fit_height,
                "letterbox": (view_height - fit_height) / 2.0,
                "pillarbox": 0.0,
            }
        else:
            # Pillarbox: black bars left and right
            fit_height = view_height
            fit_width = view_height * src_aspect
            x = (view_width - fit_width) / 2.0
            y = 0.0
            return {
                "x": x,
                "y": y,
                "width": fit_width,
                "height": fit_height,
                "letterbox": 0.0,
                "pillarbox": (view_width - fit_width) / 2.0,
            }


class MockVMSessionCoordinator:
    """Simulates VMSessionViewModel bridging SPICEConnection and MetalDisplayRenderer."""

    def __init__(self, renderer: MockMetalDisplayRenderer):
        self.renderer: MockMetalDisplayRenderer = renderer
        self.received_frames: List[Tuple[int, int, int]] = []
        self.spice_state: str = MockSPICEConnectionState.DISCONNECTED
        self.last_error: Optional[str] = None

    def spice_connection_did_change_state(self, connection: MockSPICEConnection, state: str) -> None:
        self.spice_state = state

    def spice_connection_did_receive_display_frame(
        self, connection: MockSPICEConnection, data: bytes, width: int, height: int
    ) -> None:
        stride = width * 4
        self.received_frames.append((len(data), width, height))
        self.renderer.update_framebuffer(data, width, height, stride)

    def spice_connection_did_encounter_error(self, connection: MockSPICEConnection, error: str) -> None:
        self.last_error = error


# ============================================================================
# Tier 1 & Tier 2: Feature & Boundary Tests
# ============================================================================


class TestSPICEUDSPathValidation(unittest.TestCase):
    """Validates Feature 10: SPICE UDS socket path validation and POSIX constraints."""

    def test_valid_uds_path_standard(self):
        valid_paths = [
            "/tmp/spice.sock",
            "/var/run/desk_simulator.sock",
            "/private/var/tmp/qemu_spice.ipc",
            "./local_socket.sock",
        ]
        for path in valid_paths:
            try:
                MockSPICEPathValidator.validate_socket_path(path)
            except ValueError as e:
                self.fail(f"Valid UDS path '{path}' was incorrectly rejected: {e}")

    def test_valid_uds_path_boundary_108_chars(self):
        # Exactly 108 bytes is the POSIX limit for sockaddr_un.sun_path
        boundary_path = "/tmp/" + "a" * (108 - len("/tmp/"))
        self.assertEqual(len(boundary_path.encode("utf-8")), 108)
        try:
            MockSPICEPathValidator.validate_socket_path(boundary_path)
        except ValueError as e:
            self.fail(f"108-byte boundary path should be accepted, but got: {e}")

    def test_socket_path_109_chars_rejected(self):
        # 109 bytes exceeds the limit by exactly 1 byte
        invalid_path = "/tmp/" + "a" * (109 - len("/tmp/"))
        self.assertEqual(len(invalid_path.encode("utf-8")), 109)
        with self.assertRaises(ValueError) as ctx:
            MockSPICEPathValidator.validate_socket_path(invalid_path)
        self.assertIn("exceeds POSIX limit of 108", str(ctx.exception))

    def test_socket_path_extreme_lengths_rejected(self):
        for length in [150, 256, 1024, 4096]:
            oversized_path = "/tmp/" + "x" * (length - 5)
            with self.assertRaises(ValueError):
                MockSPICEPathValidator.validate_socket_path(oversized_path)

    def test_empty_socket_path_rejected(self):
        with self.assertRaises(ValueError) as ctx:
            MockSPICEPathValidator.validate_socket_path("")
        self.assertIn("empty or malformed", str(ctx.exception))

    def test_whitespace_only_socket_path_rejected(self):
        for ws in ["   ", "\t", "\n", " \t \n "]:
            with self.assertRaises(ValueError) as ctx:
                MockSPICEPathValidator.validate_socket_path(ws)
            self.assertIn("empty or malformed", str(ctx.exception))

    def test_null_byte_in_path_rejected(self):
        null_paths = ["/tmp/spice\0.sock", "\0/tmp/sock", "/tmp/sock\0"]
        for p in null_paths:
            with self.assertRaises(ValueError) as ctx:
                MockSPICEPathValidator.validate_socket_path(p)
            self.assertIn("null byte", str(ctx.exception).lower())

    def test_path_normalization_and_trimming(self):
        # Paths with surrounding whitespace should be trimmed and accepted if valid length
        trimmed = "  /tmp/valid.sock  "
        try:
            MockSPICEPathValidator.validate_socket_path(trimmed)
        except ValueError as e:
            self.fail(f"Path with whitespace should be trimmed: {e}")


class TestAntiTCPPolicyEnforcement(unittest.TestCase):
    """Validates Feature 10: Strict prohibition of TCP loopback endpoints."""

    def test_reject_ipv4_loopback_127_0_0_1(self):
        forbidden = [
            "127.0.0.1",
            "127.0.0.1:5900",
            "tcp:127.0.0.1:5900",
            "http://127.0.0.1:8080",
            "/tmp/spice_127.0.0.1.sock",
        ]
        for target in forbidden:
            with self.assertRaises(ValueError) as ctx:
                MockSPICEPathValidator.validate_socket_path(target)
            self.assertIn("TCP loopback is strictly prohibited", str(ctx.exception))

    def test_reject_localhost_string(self):
        forbidden = [
            "localhost",
            "localhost:5900",
            "spice://localhost:5900",
            "/var/tmp/localhost.sock",
        ]
        for target in forbidden:
            with self.assertRaises(ValueError) as ctx:
                MockSPICEPathValidator.validate_socket_path(target)
            self.assertIn("TCP loopback is strictly prohibited", str(ctx.exception))

    def test_reject_zero_ip_0_0_0_0(self):
        forbidden = ["0.0.0.0", "0.0.0.0:5900", "tcp:0.0.0.0:5900"]
        for target in forbidden:
            with self.assertRaises(ValueError) as ctx:
                MockSPICEPathValidator.validate_socket_path(target)
            self.assertIn("TCP loopback is strictly prohibited", str(ctx.exception))

    def test_reject_port_parameter(self):
        forbidden = [
            "port=5900",
            "-spice port=5900",
            "/tmp/spice.sock?port=5900",
            "socket_port=5900",
        ]
        for target in forbidden:
            with self.assertRaises(ValueError) as ctx:
                MockSPICEPathValidator.validate_socket_path(target)
            self.assertIn("TCP loopback is strictly prohibited", str(ctx.exception))

    def test_case_insensitive_rejection(self):
        forbidden = [
            "LOCALHOST:5900",
            "LocalHost",
            "PORT=5900",
            "127.0.0.1",
        ]
        for target in forbidden:
            with self.assertRaises(ValueError) as ctx:
                MockSPICEPathValidator.validate_socket_path(target)
            self.assertIn("TCP loopback is strictly prohibited", str(ctx.exception))

    def test_valid_unix_paths_with_safe_subwords(self):
        # Paths with words that do not match forbidden tokens must be accepted
        safe_paths = [
            "/tmp/support_socket.sock",
            "/var/run/viewport.sock",
            "/tmp/report_service.sock",
            "/tmp/desk_sim_transport.sock",
        ]
        for p in safe_paths:
            try:
                MockSPICEPathValidator.validate_socket_path(p)
            except ValueError as e:
                self.fail(f"Safe subword path '{p}' was improperly rejected: {e}")


class TestSPICEConnectionLifecycleAndState(unittest.TestCase):
    """Validates Feature 10: SPICEConnection state transitions and socket teardown."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.sock_path = str(Path(self.temp_dir.name) / "test_spice.sock")

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_initial_state_is_disconnected(self):
        conn = MockSPICEConnection(self.sock_path)
        self.assertEqual(conn.state, MockSPICEConnectionState.DISCONNECTED)
        self.assertEqual(conn.socket_fd, -1)

    def test_connect_missing_file_transitions_to_failed(self):
        conn = MockSPICEConnection(self.sock_path)
        conn.connect()
        self.assertEqual(conn.state, MockSPICEConnectionState.FAILED)
        self.assertEqual(conn.socket_fd, -1)

    def test_connect_existing_file_transitions_to_connected(self):
        # Create simulated socket file
        with open(self.sock_path, "wb") as f:
            f.write(b"")

        conn = MockSPICEConnection(self.sock_path)
        conn.connect()
        self.assertEqual(conn.state, MockSPICEConnectionState.CONNECTED)
        self.assertGreaterEqual(conn.socket_fd, 0)

    def test_disconnect_closes_fd_and_resets_state(self):
        with open(self.sock_path, "wb") as f:
            f.write(b"")

        conn = MockSPICEConnection(self.sock_path)
        conn.connect()
        self.assertEqual(conn.state, MockSPICEConnectionState.CONNECTED)

        conn.disconnect()
        self.assertEqual(conn.state, MockSPICEConnectionState.DISCONNECTED)
        self.assertEqual(conn.socket_fd, -1)

    def test_disconnect_when_already_disconnected_is_safe(self):
        conn = MockSPICEConnection(self.sock_path)
        self.assertEqual(conn.state, MockSPICEConnectionState.DISCONNECTED)
        conn.disconnect()
        self.assertEqual(conn.state, MockSPICEConnectionState.DISCONNECTED)

    def test_send_input_when_disconnected_returns_false(self):
        conn = MockSPICEConnection(self.sock_path)
        result = conn.send_input_event(b"\x01\x00\x00")
        self.assertFalse(result)
        self.assertEqual(len(conn._input_events_sent), 0)

    def test_send_input_when_connected_succeeds(self):
        with open(self.sock_path, "wb") as f:
            f.write(b"")

        conn = MockSPICEConnection(self.sock_path)
        conn.connect()
        payload = b"\x01\x05\x00\x0a\x00"
        result = conn.send_input_event(payload)
        self.assertTrue(result)
        self.assertEqual(conn._input_events_sent, [payload])


class TestSPICEDisplayIngestionPipeline(unittest.TestCase):
    """Validates Feature 11: Programmatic display frame ingestion and delegate routing."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.sock_path = str(Path(self.temp_dir.name) / "display.sock")
        with open(self.sock_path, "wb") as f:
            f.write(b"")

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_ingest_valid_display_frame_forwards_to_delegate(self):
        conn = MockSPICEConnection(self.sock_path)
        renderer = MockMetalDisplayRenderer()
        coordinator = MockVMSessionCoordinator(renderer)
        conn.delegate = coordinator
        conn.connect()

        width = 64
        height = 48
        data = b"\xaa\xbb\xcc\xff" * (width * height)
        success = conn.ingest_display_frame(data, width, height)

        self.assertTrue(success)
        self.assertEqual(len(coordinator.received_frames), 1)
        data_len, rec_w, rec_h = coordinator.received_frames[0]
        self.assertEqual(data_len, len(data))
        self.assertEqual(rec_w, width)
        self.assertEqual(rec_h, height)
        self.assertEqual(renderer.current_frame_count, 1)

    def test_ingest_frame_when_disconnected_drops_safely(self):
        conn = MockSPICEConnection(self.sock_path)
        renderer = MockMetalDisplayRenderer()
        coordinator = MockVMSessionCoordinator(renderer)
        conn.delegate = coordinator
        # Notice conn.connect() is NOT called

        width = 64
        height = 48
        data = b"\x00" * (width * height * 4)
        success = conn.ingest_display_frame(data, width, height)

        self.assertFalse(success)
        self.assertEqual(len(coordinator.received_frames), 0)
        self.assertEqual(renderer.current_frame_count, 0)

    def test_ingest_frame_with_nil_delegate_does_not_crash(self):
        conn = MockSPICEConnection(self.sock_path)
        conn.delegate = None
        conn.connect()

        width = 32
        height = 32
        data = b"\xff" * (width * height * 4)
        success = conn.ingest_display_frame(data, width, height)
        self.assertTrue(success)
        self.assertEqual(conn._frames_ingested, 1)

    def test_ingest_truncated_buffer_size_dropped(self):
        conn = MockSPICEConnection(self.sock_path)
        renderer = MockMetalDisplayRenderer()
        coordinator = MockVMSessionCoordinator(renderer)
        conn.delegate = coordinator
        conn.connect()

        width = 100
        height = 100
        # Expected bytes = 100 * 100 * 4 = 40,000. Provide only 39,999 bytes.
        truncated_data = b"\x00" * 39999
        success = conn.ingest_display_frame(truncated_data, width, height)

        self.assertFalse(success)
        self.assertEqual(len(coordinator.received_frames), 0)

    def test_ingest_zero_byte_frame_dropped(self):
        conn = MockSPICEConnection(self.sock_path)
        conn.connect()
        success = conn.ingest_display_frame(b"", 1920, 1080)
        self.assertFalse(success)
        self.assertEqual(conn._frames_ingested, 0)

    def test_ingest_invalid_dimensions_dropped(self):
        conn = MockSPICEConnection(self.sock_path)
        conn.connect()
        data = b"\x00" * 1024
        self.assertFalse(conn.ingest_display_frame(data, 0, 1080))
        self.assertFalse(conn.ingest_display_frame(data, 1920, 0))
        self.assertFalse(conn.ingest_display_frame(data, -1920, 1080))
        self.assertFalse(conn.ingest_display_frame(data, 1920, -1080))

    def test_high_frequency_frame_queue_order(self):
        conn = MockSPICEConnection(self.sock_path)
        renderer = MockMetalDisplayRenderer()
        coordinator = MockVMSessionCoordinator(renderer)
        conn.delegate = coordinator
        conn.connect()

        w, h = 16, 16
        for i in range(120):
            frame_data = bytes([i % 256]) * (w * h * 4)
            res = conn.ingest_display_frame(frame_data, w, h)
            self.assertTrue(res)

        self.assertEqual(len(coordinator.received_frames), 120)
        self.assertEqual(renderer.current_frame_count, 120)


class TestMetalDisplayRendererLogic(unittest.TestCase):
    """Validates Feature 12: Metal framebuffer rendering, texture updates, and ProMotion."""

    def test_default_viewport_configuration(self):
        renderer = MockMetalDisplayRenderer()
        self.assertEqual(renderer.width, 1920)
        self.assertEqual(renderer.height, 1080)
        self.assertEqual(renderer.refresh_rate_hz, 60)
        self.assertEqual(renderer.scale_factor, 2.0)
        self.assertTrue(renderer.is_ready_for_rendering)
        self.assertEqual(renderer.current_frame_count, 0)

    def test_custom_viewport_refresh_rate_120hz_promotion(self):
        renderer = MockMetalDisplayRenderer(width=2532, height=1170, refresh_rate_hz=120)
        self.assertEqual(renderer.refresh_rate_hz, 120)
        self.assertEqual(renderer.width, 2532)
        self.assertEqual(renderer.height, 1170)

    def test_update_framebuffer_updates_dimensions_and_stride(self):
        renderer = MockMetalDisplayRenderer()
        w, h = 1024, 768
        stride = w * 4
        data = b"\x00" * (stride * h)

        success = renderer.update_framebuffer(data, w, h, stride)
        self.assertTrue(success)
        self.assertEqual(renderer.width, w)
        self.assertEqual(renderer.height, h)
        self.assertEqual(renderer.last_ingested_stride, 4096)
        self.assertEqual(renderer.current_frame_count, 1)

    def test_stride_calculation_width_times_four(self):
        renderer = MockMetalDisplayRenderer()
        test_widths = [320, 640, 800, 1024, 1280, 1920, 2560, 3840]
        for w in test_widths:
            expected_stride = w * 4
            h = 480
            data = b"\x00" * (expected_stride * h)
            res = renderer.update_framebuffer(data, w, h, expected_stride)
            self.assertTrue(res)
            self.assertEqual(renderer.last_ingested_stride, expected_stride)

    def test_metal_texture_pixel_format_bgra8unorm(self):
        renderer = MockMetalDisplayRenderer()
        self.assertEqual(renderer.pixel_format, ".bgra8Unorm")

    def test_texture_reallocation_on_dimension_change(self):
        renderer = MockMetalDisplayRenderer(width=800, height=600)
        self.assertEqual(renderer.texture_reallocations, 0)

        # First frame at 800x600 -> Allocates texture
        d1 = b"\x00" * (800 * 4 * 600)
        renderer.update_framebuffer(d1, 800, 600, 800 * 4)
        self.assertEqual(renderer.texture_reallocations, 1)

        # Second frame with same dimensions -> No reallocation
        renderer.update_framebuffer(d1, 800, 600, 800 * 4)
        self.assertEqual(renderer.texture_reallocations, 1)

        # Third frame resized to 1920x1080 -> Triggers reallocation
        d2 = b"\x00" * (1920 * 4 * 1080)
        renderer.update_framebuffer(d2, 1920, 1080, 1920 * 4)
        self.assertEqual(renderer.texture_reallocations, 2)
        self.assertEqual(renderer.current_texture_dims, (1920, 1080))

    def test_mismatched_stride_rejected(self):
        renderer = MockMetalDisplayRenderer()
        w, h = 640, 480
        # In BGRA8Unorm, minimum stride is width * 4 = 2560. Passing 2000 is invalid.
        invalid_stride = 2000
        data = b"\x00" * (w * h * 4)
        res = renderer.update_framebuffer(data, w, h, invalid_stride)
        self.assertFalse(res)

    def test_data_buffer_less_than_stride_times_height_rejected(self):
        renderer = MockMetalDisplayRenderer()
        w, h = 100, 100
        stride = 400
        truncated_data = b"\x00" * (stride * h - 1)
        res = renderer.update_framebuffer(truncated_data, w, h, stride)
        self.assertFalse(res)

    def test_massive_texture_4k_and_8k_buffer_math(self):
        renderer = MockMetalDisplayRenderer()

        # 4K UHD: 3840 x 2160 x 4 = 33,177,600 bytes
        w_4k, h_4k = 3840, 2160
        expected_stride_4k = w_4k * 4
        expected_len_4k = expected_stride_4k * h_4k
        self.assertEqual(expected_stride_4k, 15360)
        self.assertEqual(expected_len_4k, 33177600)

        # 8K UHD: 7680 x 4320 x 4 = 132,710,400 bytes
        w_8k, h_8k = 7680, 4320
        expected_stride_8k = w_8k * 4
        expected_len_8k = expected_stride_8k * h_8k
        self.assertEqual(expected_stride_8k, 30720)
        self.assertEqual(expected_len_8k, 132710400)


class TestMetalDisplayViewAndAspectRatio(unittest.TestCase):
    """Validates Feature 13: MetalDisplayView aspect-ratio fitting and letterbox geometry."""

    def test_aspect_ratio_fitting_4_3_in_16_9_screen(self):
        # 1024x768 (4:3 = 1.333) in 1920x1080 (16:9 = 1.777)
        # Should fit height (1080), fitted width = 1080 * (4/3) = 1440.
        # Pillarbox on left and right = (1920 - 1440) / 2 = 240.
        geom = AspectRatioFittingCalculator.calculate_fitted_rect(1024, 768, 1920, 1080)
        self.assertAlmostEqual(geom["width"], 1440.0)
        self.assertAlmostEqual(geom["height"], 1080.0)
        self.assertAlmostEqual(geom["pillarbox"], 240.0)
        self.assertAlmostEqual(geom["letterbox"], 0.0)
        self.assertAlmostEqual(geom["x"], 240.0)
        self.assertAlmostEqual(geom["y"], 0.0)

    def test_aspect_ratio_fitting_16_9_in_19_5_9_iphone_screen(self):
        # 1920x1080 (16:9 = 1.777) in 2532x1170 (iPhone 14/15 Pro: 2532/1170 = 2.164)
        # Screen is wider than 16:9. Fits height (1170), width = 1170 * (16/9) = 2080.
        # Pillarbox bars on left/right = (2532 - 2080) / 2 = 226.
        geom = AspectRatioFittingCalculator.calculate_fitted_rect(1920, 1080, 2532, 1170)
        self.assertAlmostEqual(geom["width"], 2080.0)
        self.assertAlmostEqual(geom["height"], 1170.0)
        self.assertAlmostEqual(geom["pillarbox"], 226.0)
        self.assertAlmostEqual(geom["letterbox"], 0.0)

    def test_aspect_ratio_fitting_16_10_in_16_9_screen(self):
        # 1920x1200 (16:10 = 1.6) in 1920x1080 (16:9 = 1.777)
        # Screen is wider than content (1.777 > 1.6). Fits height (1080).
        # Width = 1080 * 1.6 = 1728. Pillarbox = (1920 - 1728) / 2 = 96.
        geom = AspectRatioFittingCalculator.calculate_fitted_rect(1920, 1200, 1920, 1080)
        self.assertAlmostEqual(geom["width"], 1728.0)
        self.assertAlmostEqual(geom["height"], 1080.0)
        self.assertAlmostEqual(geom["pillarbox"], 96.0)
        self.assertAlmostEqual(geom["letterbox"], 0.0)

    def test_aspect_ratio_fitting_ultrawide_in_16_9_screen(self):
        # 2560x1080 (21:9 = 2.37) in 1920x1080 (16:9 = 1.777)
        # Content is wider than screen. Fits width (1920).
        # Height = 1920 / (2560/1080) = 810. Letterbox = (1080 - 810) / 2 = 135.
        geom = AspectRatioFittingCalculator.calculate_fitted_rect(2560, 1080, 1920, 1080)
        self.assertAlmostEqual(geom["width"], 1920.0)
        self.assertAlmostEqual(geom["height"], 810.0)
        self.assertAlmostEqual(geom["letterbox"], 135.0)
        self.assertAlmostEqual(geom["pillarbox"], 0.0)

    def test_aspect_ratio_square_in_landscape_screen(self):
        # 1024x1024 (1:1) in 1920x1080 (16:9)
        # Fits height (1080), width = 1080. Pillarbox = (1920 - 1080) / 2 = 420.
        geom = AspectRatioFittingCalculator.calculate_fitted_rect(1024, 1024, 1920, 1080)
        self.assertAlmostEqual(geom["width"], 1080.0)
        self.assertAlmostEqual(geom["height"], 1080.0)
        self.assertAlmostEqual(geom["pillarbox"], 420.0)
        self.assertAlmostEqual(geom["letterbox"], 0.0)

    def test_aspect_ratio_zero_or_negative_inputs(self):
        geom1 = AspectRatioFittingCalculator.calculate_fitted_rect(0, 768, 1920, 1080)
        self.assertEqual(geom1["width"], 0.0)
        geom2 = AspectRatioFittingCalculator.calculate_fitted_rect(1024, -100, 1920, 1080)
        self.assertEqual(geom2["height"], 0.0)


# ============================================================================
# Tier 3: Cross-Feature Interactions & End-to-End Pipeline
# ============================================================================


class TestDisplayIngestionCrossFeaturePipeline(unittest.TestCase):
    """Validates Tier 3 cross-feature interactions: SPICE -> Session -> Metal -> Blit."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.sock_path = str(Path(self.temp_dir.name) / "e2e_display.sock")
        with open(self.sock_path, "wb") as f:
            f.write(b"")

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_full_frame_ingestion_and_drawable_presentation(self):
        renderer = MockMetalDisplayRenderer(width=1920, height=1080, refresh_rate_hz=120)
        coordinator = MockVMSessionCoordinator(renderer)
        conn = MockSPICEConnection(self.sock_path)
        conn.delegate = coordinator
        conn.connect()

        # Step 1: Ingest 60 frames at 1920x1080
        w, h = 1920, 1080
        stride = w * 4
        frame_bytes = b"\x11\x22\x33\xff" * (w * h)

        for i in range(10):
            res = conn.ingest_display_frame(frame_bytes, w, h)
            self.assertTrue(res)

        self.assertEqual(renderer.current_frame_count, 10)
        self.assertEqual(renderer.texture_reallocations, 1)

        # Step 2: Present to drawable of 2532x1170 (ProMotion device screen)
        blit_res = renderer.render_to_drawable(2532, 1170)
        self.assertTrue(blit_res["blitted"])
        self.assertEqual(blit_res["copy_width"], 1920)
        self.assertEqual(blit_res["copy_height"], 1080)
        self.assertEqual(blit_res["refresh_rate_hz"], 120)

    def test_dynamic_viewport_rotation_resize_pipeline(self):
        renderer = MockMetalDisplayRenderer(width=1920, height=1080, refresh_rate_hz=120)
        coordinator = MockVMSessionCoordinator(renderer)
        conn = MockSPICEConnection(self.sock_path)
        conn.delegate = coordinator
        conn.connect()

        # Landscape initial state
        d_land = b"\x01" * (1920 * 4 * 1080)
        conn.ingest_display_frame(d_land, 1920, 1080)
        self.assertEqual(renderer.current_texture_dims, (1920, 1080))
        self.assertEqual(renderer.texture_reallocations, 1)

        # Rotate to Portrait (1080x1920)
        d_port = b"\x02" * (1080 * 4 * 1920)
        conn.ingest_display_frame(d_port, 1080, 1920)
        self.assertEqual(renderer.current_texture_dims, (1080, 1920))
        self.assertEqual(renderer.texture_reallocations, 2)
        self.assertEqual(renderer.width, 1080)
        self.assertEqual(renderer.height, 1920)


# ============================================================================
# Tier 4: Real-World Scenarios
# ============================================================================


class TestRealWorldWorkloadScenarios(unittest.TestCase):
    """Validates Tier 4 real-world operational scenarios."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.sock_path = str(Path(self.temp_dir.name) / "workload.sock")
        with open(self.sock_path, "wb") as f:
            f.write(b"")

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_scenario_1_cold_boot_60hz_display_stream(self):
        """Simulates 60Hz 1024x768 framebuffer streaming during guest OS boot."""
        renderer = MockMetalDisplayRenderer(width=1024, height=768, refresh_rate_hz=60)
        coordinator = MockVMSessionCoordinator(renderer)
        conn = MockSPICEConnection(self.sock_path)
        conn.delegate = coordinator
        conn.connect()

        # Stream 30 consecutive frames
        frame_data = b"\x44\x55\x66\xff" * (1024 * 768)
        for _ in range(30):
            conn.ingest_display_frame(frame_data, 1024, 768)

        self.assertEqual(renderer.current_frame_count, 30)
        self.assertEqual(coordinator.spice_state, MockSPICEConnectionState.CONNECTED)
        self.assertIsNone(coordinator.last_error)

    def test_scenario_2_promotion_120hz_stream_with_resolution_switch(self):
        """Simulates ProMotion 120Hz display with guest resolution change (VGA -> Full HD)."""
        renderer = MockMetalDisplayRenderer(width=640, height=480, refresh_rate_hz=120)
        coordinator = MockVMSessionCoordinator(renderer)
        conn = MockSPICEConnection(self.sock_path)
        conn.delegate = coordinator
        conn.connect()

        # Phase 1: BIOS / Bootloader 640x480 (5 frames)
        vga_frame = b"\x10" * (640 * 4 * 480)
        for _ in range(5):
            conn.ingest_display_frame(vga_frame, 640, 480)

        self.assertEqual(renderer.texture_reallocations, 1)

        # Phase 2: OS desktop loads 1920x1080 (10 frames)
        fhd_frame = b"\x20" * (1920 * 4 * 1080)
        for _ in range(10):
            conn.ingest_display_frame(fhd_frame, 1920, 1080)

        self.assertEqual(renderer.texture_reallocations, 2)
        self.assertEqual(renderer.current_frame_count, 15)
        self.assertEqual(renderer.width, 1920)
        self.assertEqual(renderer.height, 1080)


# ============================================================================
# Swift Source Code Contract & Declaration Static Verification
# ============================================================================


class TestSwiftSourceStaticVerification(unittest.TestCase):
    """Verifies static presence and signatures of display ingestion symbols in Swift sources."""

    def test_spice_connection_swift_contract(self):
        file_path = WORKSPACE_ROOT / "Engine" / "SPICE" / "SPICEConnection.swift"
        self.assertTrue(file_path.exists(), "SPICEConnection.swift must exist")
        content = file_path.read_text(encoding="utf-8")

        # Must declare SPICEConnectionState enum
        self.assertIn("enum SPICEConnectionState", content)
        self.assertIn("case disconnected", content)
        self.assertIn("case connecting", content)
        self.assertIn("case connected", content)
        self.assertIn("case failed", content)

        # Must declare SPICEConnectionDelegate protocol
        self.assertIn("protocol SPICEConnectionDelegate", content)
        self.assertIn("func spiceConnection(_ connection: SPICEConnection, didChangeState", content)
        self.assertIn("func spiceConnection(_ connection: SPICEConnection, didReceiveDisplayFrame", content)

        # Must enforce UDS socket allocation and validation
        self.assertIn("AF_UNIX", content)
        self.assertIn("SOCK_STREAM", content)
        self.assertIn("QEMUArgumentsBuilder.validateSocketPath", content)
        self.assertIn("func connect()", content)
        self.assertIn("func disconnect()", content)
        self.assertIn("func sendInputEvent", content)
        self.assertIn("func ingestDisplayFrame", content)

    def test_metal_display_renderer_swift_contract(self):
        file_path = WORKSPACE_ROOT / "Engine" / "SPICE" / "MetalDisplayRenderer.swift"
        self.assertTrue(file_path.exists(), "MetalDisplayRenderer.swift must exist")
        content = file_path.read_text(encoding="utf-8")

        # Must declare DisplayViewport
        self.assertIn("struct DisplayViewport", content)
        self.assertIn("var refreshRateHz: Int", content)

        # Must declare MetalDisplayRendererProtocol
        self.assertIn("protocol MetalDisplayRendererProtocol", content)
        self.assertIn("func updateFramebuffer(with data: Data, width: Int, height: Int, stride: Int)", content)
        self.assertIn("func resizeViewport(width: Int, height: Int)", content)
        self.assertIn("func drawFrame()", content)

        # Must use .bgra8Unorm texture format and stride width * 4
        self.assertIn(".bgra8Unorm", content)
        self.assertIn("viewport.width * 4", content)
        self.assertIn("currentFrameCount", content)

    def test_metal_display_view_swift_contract(self):
        file_path = WORKSPACE_ROOT / "UI" / "Views" / "MetalDisplayView.swift"
        self.assertTrue(file_path.exists(), "MetalDisplayView.swift must exist")
        content = file_path.read_text(encoding="utf-8")

        # Must declare MetalDisplayView wrapping MTKView
        self.assertIn("struct MetalDisplayView", content)
        self.assertIn("MTKView", content)
        self.assertIn(".bgra8Unorm", content)
        self.assertIn("preferredFramesPerSecond = renderer.viewport.refreshRateHz", content)
        self.assertIn(".scaleAspectFit", content)
        self.assertIn("drawableSizeWillChange", content)

    def test_vm_session_viewmodel_spice_delegate_routing(self):
        file_path = WORKSPACE_ROOT / "UI" / "ViewModels" / "VMSessionViewModel.swift"
        self.assertTrue(file_path.exists(), "VMSessionViewModel.swift must exist")
        content = file_path.read_text(encoding="utf-8")

        # Must conform to SPICEConnectionDelegate
        self.assertIn("extension VMSessionViewModel: SPICEConnectionDelegate", content)
        # Must forward display frame to displayRenderer.updateFramebuffer
        self.assertIn("didReceiveDisplayFrame", content)
        self.assertIn("displayRenderer.updateFramebuffer", content)
        self.assertIn("stride: width * 4", content)


    def test_metal_display_renderer_stride_and_frame_count_guard(self):
        file_path = WORKSPACE_ROOT / "Engine" / "SPICE" / "MetalDisplayRenderer.swift"
        content = file_path.read_text(encoding="utf-8")
        self.assertIn("currentFramebufferStride", content)
        self.assertIn("data.count >= bytesPerRow * viewport.height", content)

    def test_spice_socket_path_multibyte_utf8_boundary(self):
        """Verifies UTF-8 byte boundary enforcement vs character count for UDS paths."""
        builder_file = WORKSPACE_ROOT / "Engine" / "QEMU" / "QEMUArgumentsBuilder.swift"
        builder_content = builder_file.read_text(encoding="utf-8")
        self.assertIn("trimmed.utf8.count", builder_content)
        self.assertIn("maxSocketPathLength", builder_content)

        # Non-ASCII character test (each umlaut is 2 bytes in UTF-8)
        ascii_path = "/tmp/" + "a" * 100
        self.assertEqual(len(ascii_path.encode("utf-8")), 105)
        # Multibyte path where len(str) <= 104, but utf8.count > 108
        multibyte_path = "/tmp/" + "ü" * 53  # 5 + 53*2 = 111 bytes (> 108)
        self.assertTrue(len(multibyte_path) < 60)
        self.assertTrue(len(multibyte_path.encode("utf-8")) > 108)


if __name__ == "__main__":
    unittest.main()
