//
//  MemoryGuardProtocol.swift
//  Management/SmartMemoryGuard
//
//  Created for Desk-simulator Management Layer.
//

import Foundation

/// Standard entitlement keys for increased memory ceiling on iOS.
public enum MemoryEntitlementKeys {
    public static let increasedMemoryLimit = "com.apple.developer.kernel.increased-memory-limit"
    public static let extendedVirtualAddressing = "extended-virtual-addressing"
    public static let extendedVirtualAddressingKernel = "com.apple.developer.kernel.extended-virtual-addressing"
}

/// Memory pressure notification levels mapped to Darwin dispatch sources.
public enum MemoryPressureLevel: String, Codable {
    case normal = "normal"
    case warning = "warning"
    case critical = "critical"
}

/// Represents the process memory entitlements and calculated device ceiling ratio.
public struct MemoryEntitlements: Codable, Equatable {
    public let increasedMemoryLimit: Bool
    public let extendedVirtualAddressing: Bool
    public let ceilingRatio: Double

    public init(increasedMemoryLimit: Bool, extendedVirtualAddressing: Bool, ceilingRatio: Double) {
        self.increasedMemoryLimit = increasedMemoryLimit
        self.extendedVirtualAddressing = extendedVirtualAddressing
        self.ceilingRatio = ceilingRatio
    }
}

/// QMP command representation for memory ballooning and VM lifecycle.
public struct QMPCommand: Codable, Equatable {
    public let execute: String
    public let arguments: [String: Int64]

    public init(execute: String, arguments: [String: Int64] = [:]) {
        self.execute = execute
        self.arguments = arguments
    }
}

/// Protocol defining Smart Memory Guard contracts and thresholds.
public protocol MemoryGuardProtocol {
    /// Safety buffer reserved for host iOS, Metal shaders, and TCG code cache (450 MB).
    var safetyBufferBytes: UInt64 { get }

    /// Minimum safe floor allocated to guest OS (1024 MB).
    var minSafeFloorBytes: UInt64 { get }

    /// Danger threshold percentage triggering emergency auto-pause (90%).
    var dangerThresholdPercent: Double { get }

    /// Probes runtime memory entitlements and returns active ceiling ratio.
    func detectEntitlements() -> MemoryEntitlements

    /// Calculates safe guest RAM adhering to the 450MB safety reserve and safe floor.
    func calculateSafeGuestRAM(availableMemoryBytes: UInt64) -> UInt64

    /// Generates VirtIO-Balloon QMP command based on memory pressure level.
    func handleMemoryPressure(level: MemoryPressureLevel, availableMemoryBytes: UInt64) -> QMPCommand?

    /// Checks if current memory consumption exceeds 90% of Jetsam limit.
    func checkJetsamEmergency(currentUsageBytes: UInt64, memoryCeilingBytes: UInt64) -> Bool

    /// Generates emergency QMP auto-pause command to prevent Jetsam SIGKILL.
    func emergencyAutoPause() -> QMPCommand
}
