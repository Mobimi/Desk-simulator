#!/usr/bin/env python3
"""
Desk-simulator Engine Configuration and Target Whitelist Module
Defines target architecture restrictions, compiler flags, SPICE IPC configuration,
and TCG cache memory clamping parameters for the stripped iOS PC emulator engine.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, List, Optional


class EngineConfig:
    """
    Declarative and programmatic configuration for stripped QEMU and SPICE engine.
    Enforces x86_64 and aarch64 exclusive targets, -O3 -flto optimization,
    Unix Domain Socket IPC, and 128MB-256MB TCG translation buffer clamping.
    """

    ALLOWED_TARGETS: List[str] = [
        "x86_64-softmmu",
        "aarch64-softmmu",
    ]

    FORBIDDEN_TARGETS: List[str] = [
        "mips",
        "ppc",
        "sparc",
        "riscv",
        "s390x",
        "i386",
        "arm",
        "mips-softmmu",
        "mipsel-softmmu",
        "mips64-softmmu",
        "mips64el-softmmu",
        "ppc-softmmu",
        "ppc64-softmmu",
        "sparc-softmmu",
        "sparc64-softmmu",
        "riscv32-softmmu",
        "riscv64-softmmu",
        "s390x-softmmu",
        "arm-softmmu",
        "i386-softmmu",
        "m68k-softmmu",
        "sh4-softmmu",
    ]

    COMPILER_REQUIRED_FLAGS: List[str] = [
        "-O3",
        "-flto",
    ]

    APPLE_SILICON_TARGETS: List[str] = [
        "-mcpu=apple-m1",
        "-mcpu=apple-a15",
        "-arch arm64",
    ]

    PRUNED_CHANNELS: List[str] = [
        "smartcard",
        "webdav",
    ]

    ESSENTIAL_CHANNELS: List[str] = [
        "main",
        "display",
        "inputs",
        "cursor",
        "playback",
        "record",
    ]

    TCG_MIN_MB: int = 128
    TCG_MAX_MB: int = 256
    DEFAULT_TCG_MB: int = 128

    @classmethod
    def load_config(cls, config_path: Optional[Path | str] = None) -> dict[str, Any]:
        """Loads declarative engine configuration from JSON manifest."""
        if config_path is None:
            config_path = Path(__file__).resolve().parent / "engine_config.json"
        else:
            config_path = Path(config_path)

        with open(config_path, "r", encoding="utf-8") as f:
            return json.load(f)

    @classmethod
    def get_whitelist(cls, whitelist_path: Optional[Path | str] = None) -> List[str]:
        """Reads target whitelist from target_whitelist.txt."""
        if whitelist_path is None:
            whitelist_path = Path(__file__).resolve().parent / "target_whitelist.txt"
        else:
            whitelist_path = Path(whitelist_path)

        with open(whitelist_path, "r", encoding="utf-8") as f:
            lines = [line.strip() for line in f if line.strip() and not line.startswith("#")]
        return lines

    @classmethod
    def is_channel_pruned(cls, channel_name: str) -> bool:
        """Returns True if the specified SPICE channel is pruned to save RAM."""
        if not isinstance(channel_name, str):
            return False
        return channel_name.strip().lower() in cls.PRUNED_CHANNELS

    @classmethod
    def validate_targets(cls, targets: List[str], require_all: bool = False) -> bool:
        """
        Validates candidate target list against the whitelist.
        - Default (require_all=False): Validates that targets is non-empty and every target is in ALLOWED_TARGETS.
        - If require_all=True: Additionally validates that all ALLOWED_TARGETS are present.
        """
        if not isinstance(targets, list) or len(targets) == 0:
            return False

        for t in targets:
            if not isinstance(t, str):
                return False
            # Check exact string formatting (no trailing/leading whitespace or case divergence)
            if t != t.strip() or t != t.lower():
                return False
            if t not in cls.ALLOWED_TARGETS:
                return False
            for forbidden in cls.FORBIDDEN_TARGETS:
                if forbidden in t and t not in cls.ALLOWED_TARGETS:
                    return False

        if require_all:
            if not set(cls.ALLOWED_TARGETS).issubset(set(targets)):
                return False

        return True

    @classmethod
    def validate_compiler_flags(cls, flags: List[str], require_apple_silicon: bool = False) -> bool:
        """
        Validates compiler flags using exact token-based matching.
        Ensures -O3 and -flto are present as discrete tokens, and rejects -O0 debug flags.
        If require_apple_silicon=True, requires at least one Apple Silicon optimization flag.
        """
        if not isinstance(flags, list) or len(flags) == 0:
            return False

        tokens: set[str] = set()
        for f in flags:
            if not isinstance(f, str) or not f.strip():
                return False
            for part in f.split():
                tokens.add(part)

        # Debug flags invalidate aggressive performance
        if "-O0" in tokens:
            return False

        # Exact token matching for required flags
        for req in cls.COMPILER_REQUIRED_FLAGS:
            if req not in tokens:
                return False

        if require_apple_silicon:
            has_apple_target = (
                any("-mcpu=apple" in tok for tok in tokens) or
                ("-arch" in tokens and "arm64" in tokens) or
                any(af in flags for af in cls.APPLE_SILICON_TARGETS)
            )
            if not has_apple_target:
                return False

        return True

    @classmethod
    def clamp_tcg_size(cls, requested_mb: int) -> int:
        """
        Clamps TCG translation cache buffer size between 128MB and 256MB.
        Safeguards against runaway memory growth and iOS Jetsam termination.
        """
        if not isinstance(requested_mb, int) or isinstance(requested_mb, bool):
            raise TypeError(f"TCG size must be an integer, got {type(requested_mb).__name__}")

        if requested_mb < cls.TCG_MIN_MB:
            return cls.TCG_MIN_MB
        if requested_mb > cls.TCG_MAX_MB:
            return cls.TCG_MAX_MB
        return requested_mb

    @classmethod
    def generate_spice_uds_args(
        cls,
        socket_path: str,
        disable_smartcard: bool = True,
        disable_webdav: bool = True,
    ) -> List[str]:
        """
        Generates SPICE launch arguments binding to a Unix Domain Socket.
        Disallows comma delimiters to prevent QEMU parameter injection.
        Strictly prohibits TCP loopback (127.0.0.1 / localhost / port=).
        Disables Smartcard and WebDAV channels to save ~100MB RAM.
        """
        if not isinstance(socket_path, str) or not socket_path.strip():
            raise ValueError("Socket path must be a non-empty string.")

        stripped_path = socket_path.strip()

        if "\x00" in stripped_path:
            raise ValueError("Socket path cannot contain null bytes.")

        if "," in stripped_path:
            raise ValueError(f"Socket path cannot contain comma delimiters: {socket_path}")

        lowered = stripped_path.lower()
        if any(bad in lowered for bad in ["127.0.0.1", "localhost", "0.0.0.0", "port="]):
            raise ValueError(f"TCP loopback is strictly prohibited: {socket_path}")

        byte_len = len(stripped_path.encode("utf-8"))
        if byte_len > 108:
            raise ValueError(f"Socket path exceeds POSIX limit of 108 bytes: {byte_len}")

        args = [
            "-spice",
            f"unix=on,addr={stripped_path},disable-ticketing=on",
        ]
        if disable_smartcard:
            args.extend(["-global", "spice.smartcard=off"])
        if disable_webdav:
            args.extend(["-global", "spice.webdav=off"])
        return args

    @classmethod
    def generate_qemu_cmdline(
        cls,
        target: str,
        ram_mb: int,
        tb_size_mb: int,
        spice_socket: str,
        vcpus: int = 2,
        additional_args: Optional[List[str]] = None,
        disable_smartcard: bool = True,
        disable_webdav: bool = True,
    ) -> List[str]:
        """
        Generates full QEMU CLI invocation enforcing target whitelist,
        clamped TCG cache buffer, memory safety, and SPICE UDS IPC.
        """
        if target not in cls.ALLOWED_TARGETS:
            raise ValueError(f"Forbidden target: {target}")

        if not isinstance(ram_mb, int) or isinstance(ram_mb, bool) or ram_mb <= 0:
            raise ValueError(f"RAM size must be a positive integer in MB, got: {ram_mb}")

        if not isinstance(vcpus, int) or isinstance(vcpus, bool) or vcpus <= 0:
            raise ValueError(f"vCPUs must be a positive integer, got: {vcpus}")

        clamped_tb = cls.clamp_tcg_size(tb_size_mb)
        binary_name = f"qemu-system-{target.replace('-softmmu', '')}"
        spice_args = cls.generate_spice_uds_args(
            spice_socket,
            disable_smartcard=disable_smartcard,
            disable_webdav=disable_webdav,
        )

        cmd = [
            binary_name,
            "-m",
            str(ram_mb),
            "-smp",
            f"cpus={vcpus},cores={vcpus}",
            "-accel",
            f"tcg,tb-size={clamped_tb}",
        ]
        cmd.extend(spice_args)

        if additional_args is not None:
            if not isinstance(additional_args, list):
                raise TypeError(f"additional_args must be a list of strings, got: {type(additional_args).__name__}")
            for arg in additional_args:
                if not isinstance(arg, str):
                    raise TypeError(f"additional_args element must be a string, got: {type(arg).__name__}")
                arg_lower = arg.lower()
                if any(bad in arg_lower for bad in ["127.0.0.1", "localhost", "0.0.0.0", "port="]):
                    raise ValueError(f"TCP loopback is strictly prohibited in additional_args: {arg}")
                cmd.append(arg)

        return cmd
