#!/usr/bin/env python3
"""
Unit tests for Engine Core Configuration (EngineConfig).
Verifies:
- Strict target whitelist enforcement and pruning of extraneous architectures
- Compiler optimization flags validation (-O3, -flto, Apple Silicon tuning)
- SPICE Unix Domain Socket IPC and channel pruning
- TCG translation buffer size clamping within [128MB, 256MB]
- QEMU command line synthesis and argument validation
- Declarative engine_config.json loading and schema consistency
"""

import sys
import unittest
from pathlib import Path

# Workspace root resolution
WORKSPACE_ROOT = Path(__file__).resolve().parent.parent.parent
if str(WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_ROOT))

from Engine.Config.engine_config import EngineConfig


class TestTargetWhitelist(unittest.TestCase):
    """Unit tests for EngineConfig target architecture filtering and whitelist pruning."""

    def test_allowed_targets_constant(self):
        """Verifies ALLOWED_TARGETS contains exclusively x86_64-softmmu and aarch64-softmmu."""
        expected = ["x86_64-softmmu", "aarch64-softmmu"]
        self.assertEqual(EngineConfig.ALLOWED_TARGETS, expected)

    def test_forbidden_targets_contains_all_non_essential(self):
        """Verifies FORBIDDEN_TARGETS contains MIPS, PPC, SPARC, RISC-V, s390x, i386, ARM."""
        essential_pruned = ["mips", "ppc", "sparc", "riscv", "s390x", "i386", "arm"]
        for target in essential_pruned:
            self.assertTrue(
                any(target in forbidden for forbidden in EngineConfig.FORBIDDEN_TARGETS),
                f"Expected forbidden architecture prefix '{target}' in FORBIDDEN_TARGETS",
            )

    def test_validate_targets_valid_single(self):
        """Single allowed target passes when require_all=False."""
        self.assertTrue(EngineConfig.validate_targets(["x86_64-softmmu"], require_all=False))
        self.assertTrue(EngineConfig.validate_targets(["aarch64-softmmu"], require_all=False))

    def test_validate_targets_valid_both(self):
        """Both allowed targets pass whether require_all is True or False."""
        targets = ["x86_64-softmmu", "aarch64-softmmu"]
        self.assertTrue(EngineConfig.validate_targets(targets, require_all=False))
        self.assertTrue(EngineConfig.validate_targets(targets, require_all=True))

    def test_validate_targets_require_all(self):
        """Single allowed target fails when require_all=True."""
        self.assertFalse(EngineConfig.validate_targets(["x86_64-softmmu"], require_all=True))
        self.assertFalse(EngineConfig.validate_targets(["aarch64-softmmu"], require_all=True))

    def test_validate_targets_forbidden_individually_rejected(self):
        """Every forbidden architecture is strictly rejected."""
        forbidden_samples = [
            "mips-softmmu",
            "ppc64-softmmu",
            "sparc-softmmu",
            "riscv64-softmmu",
            "s390x-softmmu",
            "i386-softmmu",
            "arm-softmmu",
            "m68k-softmmu",
            "sh4-softmmu",
        ]
        for fb in forbidden_samples:
            self.assertFalse(
                EngineConfig.validate_targets([fb]),
                f"Forbidden architecture {fb} was not rejected",
            )

    def test_validate_targets_forbidden_mixed_with_allowed(self):
        """Mixing forbidden targets with allowed targets invalidates the entire list."""
        mixed = ["x86_64-softmmu", "mips-softmmu"]
        self.assertFalse(EngineConfig.validate_targets(mixed))

    def test_validate_targets_empty_list(self):
        """Empty target list is rejected."""
        self.assertFalse(EngineConfig.validate_targets([]))

    def test_validate_targets_non_string(self):
        """Non-string elements in target list are rejected safely without crashing."""
        self.assertFalse(EngineConfig.validate_targets([123, "x86_64-softmmu"]))  # type: ignore
        self.assertFalse(EngineConfig.validate_targets([None]))  # type: ignore
        self.assertFalse(EngineConfig.validate_targets([True]))  # type: ignore

    def test_validate_targets_whitespace_and_casing(self):
        """Targets with leading/trailing whitespace or uppercase characters are rejected."""
        self.assertFalse(EngineConfig.validate_targets(["x86_64-softmmu "]))
        self.assertFalse(EngineConfig.validate_targets([" x86_64-softmmu"]))
        self.assertFalse(EngineConfig.validate_targets(["X86_64-SOFTMMU"]))
        self.assertFalse(EngineConfig.validate_targets(["AARCH64-SOFTMMU"]))

    def test_get_whitelist_loads_file(self):
        """EngineConfig.get_whitelist() correctly reads target_whitelist.txt."""
        whitelist = EngineConfig.get_whitelist()
        self.assertEqual(whitelist, ["x86_64-softmmu", "aarch64-softmmu"])

    def test_get_whitelist_missing_file_raises_error(self):
        """Non-existent whitelist file raises FileNotFoundError."""
        with self.assertRaises(FileNotFoundError):
            EngineConfig.get_whitelist("/non/existent/path/to/whitelist.txt")


class TestCompilerFlags(unittest.TestCase):
    """Unit tests for compiler optimization flags (-O3, -flto, Apple Silicon tuning)."""

    def test_required_flags_constant(self):
        """Verifies COMPILER_REQUIRED_FLAGS contains -O3 and -flto."""
        self.assertIn("-O3", EngineConfig.COMPILER_REQUIRED_FLAGS)
        self.assertIn("-flto", EngineConfig.COMPILER_REQUIRED_FLAGS)

    def test_apple_silicon_targets_constant(self):
        """Verifies APPLE_SILICON_TARGETS includes -mcpu=apple-m1, -mcpu=apple-a15, -arch arm64."""
        self.assertIn("-mcpu=apple-m1", EngineConfig.APPLE_SILICON_TARGETS)
        self.assertIn("-mcpu=apple-a15", EngineConfig.APPLE_SILICON_TARGETS)
        self.assertIn("-arch arm64", EngineConfig.APPLE_SILICON_TARGETS)

    def test_validate_compiler_flags_success(self):
        """Valid compiler flags list passes validation."""
        flags = ["-O3", "-flto", "-Wall"]
        self.assertTrue(EngineConfig.validate_compiler_flags(flags, require_apple_silicon=False))

    def test_validate_compiler_flags_space_delimited(self):
        """Tokens inside space-delimited string arguments are properly recognized."""
        flags = ["-O3 -flto -mcpu=apple-m1"]
        self.assertTrue(EngineConfig.validate_compiler_flags(flags, require_apple_silicon=True))

    def test_validate_compiler_flags_missing_o3(self):
        """Missing -O3 (e.g. -O2) fails compiler flag validation."""
        flags = ["-O2", "-flto"]
        self.assertFalse(EngineConfig.validate_compiler_flags(flags))

    def test_validate_compiler_flags_missing_flto(self):
        """Missing -flto fails compiler flag validation."""
        flags = ["-O3", "-Wall"]
        self.assertFalse(EngineConfig.validate_compiler_flags(flags))

    def test_validate_compiler_flags_rejects_debug_o0(self):
        """Presence of -O0 debug optimization flag causes validation to fail."""
        flags = ["-O3", "-flto", "-O0"]
        self.assertFalse(EngineConfig.validate_compiler_flags(flags))

    def test_validate_compiler_flags_apple_silicon_required(self):
        """When require_apple_silicon=True, missing Apple Silicon flags causes validation to fail."""
        flags_without_apple = ["-O3", "-flto"]
        self.assertFalse(EngineConfig.validate_compiler_flags(flags_without_apple, require_apple_silicon=True))

        flags_with_apple_m1 = ["-O3", "-flto", "-mcpu=apple-m1"]
        self.assertTrue(EngineConfig.validate_compiler_flags(flags_with_apple_m1, require_apple_silicon=True))

        flags_with_apple_arch = ["-O3", "-flto", "-arch", "arm64"]
        self.assertTrue(EngineConfig.validate_compiler_flags(flags_with_apple_arch, require_apple_silicon=True))

    def test_validate_compiler_flags_empty_or_whitespace(self):
        """Empty flags list, non-strings, or whitespace-only elements fail validation."""
        self.assertFalse(EngineConfig.validate_compiler_flags([]))
        self.assertFalse(EngineConfig.validate_compiler_flags([""]))
        self.assertFalse(EngineConfig.validate_compiler_flags(["   "]))
        self.assertFalse(EngineConfig.validate_compiler_flags([123]))  # type: ignore


class TestTCGBufferClamping(unittest.TestCase):
    """Unit tests for TCG translation buffer size clamping within [128MB, 256MB]."""

    def test_tcg_constants(self):
        """Verifies TCG buffer bounds constants: min 128MB, max 256MB, default 128MB."""
        self.assertEqual(EngineConfig.TCG_MIN_MB, 128)
        self.assertEqual(EngineConfig.TCG_MAX_MB, 256)
        self.assertEqual(EngineConfig.DEFAULT_TCG_MB, 128)

    def test_clamp_tcg_within_range(self):
        """Values between 128 and 256 inclusive return unchanged."""
        self.assertEqual(EngineConfig.clamp_tcg_size(128), 128)
        self.assertEqual(EngineConfig.clamp_tcg_size(192), 192)
        self.assertEqual(EngineConfig.clamp_tcg_size(200), 200)
        self.assertEqual(EngineConfig.clamp_tcg_size(256), 256)

    def test_clamp_tcg_below_min(self):
        """Values below 128MB (including 0 and negative values) are clamped up to 128MB."""
        self.assertEqual(EngineConfig.clamp_tcg_size(0), 128)
        self.assertEqual(EngineConfig.clamp_tcg_size(-50), 128)
        self.assertEqual(EngineConfig.clamp_tcg_size(1), 128)
        self.assertEqual(EngineConfig.clamp_tcg_size(64), 128)
        self.assertEqual(EngineConfig.clamp_tcg_size(127), 128)

    def test_clamp_tcg_above_max(self):
        """Values above 256MB are clamped down to 256MB."""
        self.assertEqual(EngineConfig.clamp_tcg_size(257), 256)
        self.assertEqual(EngineConfig.clamp_tcg_size(512), 256)
        self.assertEqual(EngineConfig.clamp_tcg_size(1024), 256)
        self.assertEqual(EngineConfig.clamp_tcg_size(9999), 256)

    def test_clamp_tcg_type_error_on_bool(self):
        """Booleans True and False raise TypeError despite isinstance(bool, int)."""
        with self.assertRaises(TypeError):
            EngineConfig.clamp_tcg_size(True)  # type: ignore
        with self.assertRaises(TypeError):
            EngineConfig.clamp_tcg_size(False)  # type: ignore

    def test_clamp_tcg_type_error_on_non_int(self):
        """Strings, floats, and None raise TypeError."""
        with self.assertRaises(TypeError):
            EngineConfig.clamp_tcg_size("128")  # type: ignore
        with self.assertRaises(TypeError):
            EngineConfig.clamp_tcg_size(128.5)  # type: ignore
        with self.assertRaises(TypeError):
            EngineConfig.clamp_tcg_size(None)  # type: ignore


class TestSpiceUnixDomainSockets(unittest.TestCase):
    """Unit tests for SPICE Unix Domain Socket argument generation and channel pruning."""

    def test_generate_spice_uds_args_valid(self):
        """Valid socket path generates -spice unix=on,addr=... arguments."""
        args = EngineConfig.generate_spice_uds_args("/tmp/desk_spice.sock")
        self.assertIn("-spice", args)
        self.assertIn("unix=on,addr=/tmp/desk_spice.sock,disable-ticketing=on", args)

    def test_generate_spice_uds_args_channel_pruning(self):
        """Disables smartcard and webdav by default; honors toggle arguments."""
        args_default = EngineConfig.generate_spice_uds_args("/tmp/spice.sock")
        self.assertIn("-global", args_default)
        self.assertIn("spice.smartcard=off", args_default)
        self.assertIn("spice.webdav=off", args_default)

        # Disable flags toggled
        args_no_prune = EngineConfig.generate_spice_uds_args(
            "/tmp/spice.sock",
            disable_smartcard=False,
            disable_webdav=False,
        )
        self.assertNotIn("spice.smartcard=off", args_no_prune)
        self.assertNotIn("spice.webdav=off", args_no_prune)

    def test_generate_spice_uds_prohibits_loopback(self):
        """TCP loopback keywords (127.0.0.1, localhost, 0.0.0.0, port=) raise ValueError."""
        for loopback in ["127.0.0.1", "localhost", "0.0.0.0", "port=5900", "tcp:127.0.0.1:5900"]:
            with self.assertRaises(ValueError):
                EngineConfig.generate_spice_uds_args(loopback)

    def test_generate_spice_uds_empty_or_whitespace(self):
        """Empty string or whitespace-only socket path raises ValueError."""
        with self.assertRaises(ValueError):
            EngineConfig.generate_spice_uds_args("")
        with self.assertRaises(ValueError):
            EngineConfig.generate_spice_uds_args("   ")
        with self.assertRaises(ValueError):
            EngineConfig.generate_spice_uds_args(None)  # type: ignore

    def test_generate_spice_uds_null_bytes(self):
        """Socket path containing null bytes raises ValueError."""
        with self.assertRaises(ValueError):
            EngineConfig.generate_spice_uds_args("/tmp/spice\x00.sock")

    def test_generate_spice_uds_commas(self):
        """Socket path containing commas raises ValueError to prevent QEMU CLI parameter injection."""
        with self.assertRaises(ValueError):
            EngineConfig.generate_spice_uds_args("/tmp/a,b.sock")

    def test_generate_spice_uds_posix_path_limit(self):
        """Paths exceeding POSIX sockaddr_un 108 bytes raise ValueError; 108 bytes succeeds."""
        # 108 bytes path
        base_108 = "/tmp/" + "a" * (108 - len("/tmp/"))
        self.assertEqual(len(base_108.encode("utf-8")), 108)
        args = EngineConfig.generate_spice_uds_args(base_108)
        self.assertIn(f"unix=on,addr={base_108},disable-ticketing=on", args)

        # 109 bytes path
        path_109 = base_108 + "b"
        self.assertEqual(len(path_109.encode("utf-8")), 109)
        with self.assertRaises(ValueError):
            EngineConfig.generate_spice_uds_args(path_109)

    def test_is_channel_pruned(self):
        """is_channel_pruned returns True for smartcard and webdav, False for essential channels."""
        self.assertTrue(EngineConfig.is_channel_pruned("smartcard"))
        self.assertTrue(EngineConfig.is_channel_pruned("webdav"))
        self.assertTrue(EngineConfig.is_channel_pruned("SMARTCARD"))
        self.assertFalse(EngineConfig.is_channel_pruned("display"))
        self.assertFalse(EngineConfig.is_channel_pruned("inputs"))
        self.assertFalse(EngineConfig.is_channel_pruned("cursor"))
        self.assertFalse(EngineConfig.is_channel_pruned(123))  # type: ignore


class TestQEMUCommandLineGeneration(unittest.TestCase):
    """Unit tests for full QEMU CLI command synthesis."""

    def test_generate_qemu_cmdline_x86(self):
        """Target x86_64-softmmu selects qemu-system-x86_64 binary."""
        cmd = EngineConfig.generate_qemu_cmdline(
            target="x86_64-softmmu",
            ram_mb=2048,
            tb_size_mb=128,
            spice_socket="/tmp/desk.sock",
            vcpus=2,
        )
        self.assertEqual(cmd[0], "qemu-system-x86_64")
        self.assertIn("-m", cmd)
        self.assertIn("2048", cmd)
        self.assertIn("cpus=2,cores=2", cmd)
        self.assertIn("tcg,tb-size=128", cmd)
        self.assertIn("unix=on,addr=/tmp/desk.sock,disable-ticketing=on", cmd)

    def test_generate_qemu_cmdline_aarch64(self):
        """Target aarch64-softmmu selects qemu-system-aarch64 binary."""
        cmd = EngineConfig.generate_qemu_cmdline(
            target="aarch64-softmmu",
            ram_mb=4096,
            tb_size_mb=256,
            spice_socket="/tmp/desk.sock",
            vcpus=2,
        )
        self.assertEqual(cmd[0], "qemu-system-aarch64")
        self.assertIn("4096", cmd)
        self.assertIn("tcg,tb-size=256", cmd)

    def test_generate_qemu_cmdline_forbidden_target(self):
        """Forbidden target raises ValueError."""
        with self.assertRaises(ValueError):
            EngineConfig.generate_qemu_cmdline(
                target="mips-softmmu",
                ram_mb=1024,
                tb_size_mb=128,
                spice_socket="/tmp/desk.sock",
            )

    def test_generate_qemu_cmdline_ram_vcpus_validation(self):
        """RAM or vCPUs non-positive, 0, or boolean raise ValueError."""
        with self.assertRaises(ValueError):
            EngineConfig.generate_qemu_cmdline("x86_64-softmmu", ram_mb=0, tb_size_mb=128, spice_socket="/tmp/s.sock")
        with self.assertRaises(ValueError):
            EngineConfig.generate_qemu_cmdline("x86_64-softmmu", ram_mb=-10, tb_size_mb=128, spice_socket="/tmp/s.sock")
        with self.assertRaises(ValueError):
            EngineConfig.generate_qemu_cmdline("x86_64-softmmu", ram_mb=True, tb_size_mb=128, spice_socket="/tmp/s.sock")  # type: ignore
        with self.assertRaises(ValueError):
            EngineConfig.generate_qemu_cmdline("x86_64-softmmu", ram_mb=1024, tb_size_mb=128, spice_socket="/tmp/s.sock", vcpus=0)

    def test_generate_qemu_cmdline_tcg_clamping(self):
        """TCG buffer size is automatically clamped in the synthesized command line."""
        cmd = EngineConfig.generate_qemu_cmdline(
            target="x86_64-softmmu",
            ram_mb=2048,
            tb_size_mb=64,  # Underflow: should clamp to 128
            spice_socket="/tmp/desk.sock",
        )
        self.assertIn("tcg,tb-size=128", " ".join(cmd))

        cmd_overflow = EngineConfig.generate_qemu_cmdline(
            target="x86_64-softmmu",
            ram_mb=2048,
            tb_size_mb=1024,  # Overflow: should clamp to 256
            spice_socket="/tmp/desk.sock",
        )
        self.assertIn("tcg,tb-size=256", " ".join(cmd_overflow))

    def test_generate_qemu_cmdline_additional_args_loopback(self):
        """TCP loopback in additional_args raises ValueError."""
        with self.assertRaises(ValueError):
            EngineConfig.generate_qemu_cmdline(
                target="x86_64-softmmu",
                ram_mb=2048,
                tb_size_mb=128,
                spice_socket="/tmp/desk.sock",
                additional_args=["-net", "tcp:127.0.0.1:8080"],
            )

    def test_generate_qemu_cmdline_additional_args_type_checks(self):
        """Invalid types in additional_args raise TypeError."""
        with self.assertRaises(TypeError):
            EngineConfig.generate_qemu_cmdline(
                target="x86_64-softmmu",
                ram_mb=2048,
                tb_size_mb=128,
                spice_socket="/tmp/desk.sock",
                additional_args="not-a-list",  # type: ignore
            )
        with self.assertRaises(TypeError):
            EngineConfig.generate_qemu_cmdline(
                target="x86_64-softmmu",
                ram_mb=2048,
                tb_size_mb=128,
                spice_socket="/tmp/desk.sock",
                additional_args=[123],  # type: ignore
            )


class TestDeclarativeConfig(unittest.TestCase):
    """Unit tests for declarative engine_config.json manifest."""

    def test_load_config_default(self):
        """Loads engine_config.json successfully and verifies dictionary structure."""
        data = EngineConfig.load_config()
        self.assertIsInstance(data, dict)

    def test_load_config_keys(self):
        """engine_config.json contains all required schema keys."""
        data = EngineConfig.load_config()
        required_keys = [
            "allowed_targets",
            "forbidden_targets",
            "compiler_required_flags",
            "apple_silicon_targets",
            "tcg_buffer_clamp",
            "spice_ipc",
        ]
        for key in required_keys:
            self.assertIn(key, data)

    def test_load_config_consistency(self):
        """JSON values match Python class constants."""
        data = EngineConfig.load_config()
        self.assertEqual(data["allowed_targets"], EngineConfig.ALLOWED_TARGETS)
        self.assertEqual(data["tcg_buffer_clamp"]["min_mb"], EngineConfig.TCG_MIN_MB)
        self.assertEqual(data["tcg_buffer_clamp"]["max_mb"], EngineConfig.TCG_MAX_MB)
        self.assertEqual(data["spice_ipc"]["transport"], "unix")
        self.assertEqual(data["spice_ipc"]["pruned_channels"], EngineConfig.PRUNED_CHANNELS)


if __name__ == "__main__":
    unittest.main()
