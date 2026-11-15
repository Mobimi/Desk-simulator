//
//  Architecture.swift
//  Desk-simulator Engine Layer
//
//  Target architecture definitions and strict whitelist enforcement.
//

import Foundation

public enum TargetArchitecture: String, CaseIterable, Codable {
    case x86_64 = "x86_64"
    case aarch64 = "aarch64"

    /// Canonical target triple representation in QEMU configuration
    public var targetTriple: String {
        switch self {
        case .x86_64:
            return "x86_64-softmmu"
        case .aarch64:
            return "aarch64-softmmu"
        }
    }

    /// Executable binary name corresponding to architecture
    public var binaryName: String {
        switch self {
        case .x86_64:
            return "qemu-system-x86_64"
        case .aarch64:
            return "qemu-system-aarch64"
        }
    }

    /// Human-readable display label
    public var displayName: String {
        switch self {
        case .x86_64:
            return "x86_64 (Intel/AMD 64-bit)"
        case .aarch64:
            return "ARM64 / AArch64 (Apple Silicon / ARM v8+)"
        }
    }

    /// Allowed target strings whitelist
    public static let allowedTargetTriples: Set<String> = [
        "x86_64-softmmu",
        "aarch64-softmmu"
    ]

    /// Forbidden stripped architectures
    public static let forbiddenArchitectures: Set<String> = [
        "mips", "mipsel", "mips64", "mips64el",
        "ppc", "ppc64", "sparc", "sparc64",
        "riscv32", "riscv64", "s390x", "arm",
        "i386", "m68k", "sh4", "xtensa", "cris", "alpha"
    ]

    /// Initializes target architecture from a target triple or binary name
    public init?(identifier: String) {
        let clean = identifier.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        if clean == "x86_64" || clean == "x86_64-softmmu" || clean == "qemu-system-x86_64" {
            self = .x86_64
        } else if clean == "aarch64" || clean == "arm64" || clean == "aarch64-softmmu" || clean == "qemu-system-aarch64" {
            self = .aarch64
        } else {
            return nil
        }
    }

    /// Validates whether an architecture string is within the strict whitelist
    public static func isWhitelisted(target: String) -> Bool {
        let clean = target.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        return allowedTargetTriples.contains(clean) || clean == "x86_64" || clean == "aarch64"
    }

    /// Validates an array of target architectures
    public static func validate(targets: [String]) -> Bool {
        guard !targets.isEmpty else { return false }
        for target in targets {
            guard isWhitelisted(target: target) else {
                return false
            }
        }
        return true
    }
}
