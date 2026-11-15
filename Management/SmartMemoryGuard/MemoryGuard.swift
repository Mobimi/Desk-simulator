//
//  MemoryGuard.swift
//  Management/SmartMemoryGuard
//
//  Production implementation of Smart Memory Guard for iOS PC Emulation.
//

import Foundation

/// Production service implementing Smart Memory Guard.
public class MemoryGuard: MemoryGuardProtocol {
    /// 450 MB buffer reserved for iOS system, Metal display pipelines, and TCG code cache.
    public let safetyBufferBytes: UInt64 = 450 * 1024 * 1024

    /// 1024 MB absolute minimum safe guest RAM floor.
    public let minSafeFloorBytes: UInt64 = 1024 * 1024 * 1024

    /// 90% danger threshold for emergency pause.
    public let dangerThresholdPercent: Double = 0.90

    /// Current entitlements state.
    public private(set) var entitlements: MemoryEntitlements

    /// Last known available memory reported by system.
    public private(set) var lastAvailableBytes: UInt64 = 0

    /// Last known process memory usage.
    public private(set) var currentUsageBytes: UInt64 = 0

    /// Configured memory ceiling for current device/entitlement.
    public private(set) var memoryCeilingBytes: UInt64 = 0

    /// Emergency pause state.
    public private(set) var isEmergencyPaused: Bool = false

    /// Initializes MemoryGuard with explicit or detected entitlements.
    public init(increasedMemoryLimit: Bool = false, extendedVirtualAddressing: Bool = false) {
        let ratio: Double
        if increasedMemoryLimit && extendedVirtualAddressing {
            ratio = 0.80
        } else if increasedMemoryLimit {
            ratio = 0.75
        } else {
            ratio = 0.50
        }
        self.entitlements = MemoryEntitlements(
            increasedMemoryLimit: increasedMemoryLimit,
            extendedVirtualAddressing: extendedVirtualAddressing,
            ceilingRatio: ratio
        )
    }

    /// Probes runtime memory entitlements and returns active ceiling configuration.
    public func detectEntitlements() -> MemoryEntitlements {
        return self.entitlements
    }

    /// Updates active entitlements dynamically.
    public func updateEntitlements(increasedMemoryLimit: Bool, extendedVirtualAddressing: Bool) {
        let ratio: Double
        if increasedMemoryLimit && extendedVirtualAddressing {
            ratio = 0.80
        } else if increasedMemoryLimit {
            ratio = 0.75
        } else {
            ratio = 0.50
        }
        self.entitlements = MemoryEntitlements(
            increasedMemoryLimit: increasedMemoryLimit,
            extendedVirtualAddressing: extendedVirtualAddressing,
            ceilingRatio: ratio
        )
    }

    /// Calculates safe guest RAM adhering to the 450MB safety reserve and safe floor.
    /// Handles underflow gracefully when availableMemoryBytes <= safetyBufferBytes.
    public func calculateSafeGuestRAM(availableMemoryBytes: UInt64) -> UInt64 {
        self.lastAvailableBytes = availableMemoryBytes
        if availableMemoryBytes > self.safetyBufferBytes {
            let calculated = availableMemoryBytes - self.safetyBufferBytes
            return max(calculated, self.minSafeFloorBytes)
        }
        return self.minSafeFloorBytes
    }

    /// Evaluates incoming memory pressure and dispatches VirtIO-Balloon QMP command.
    public func handleMemoryPressure(level: MemoryPressureLevel, availableMemoryBytes: UInt64) -> QMPCommand? {
        self.lastAvailableBytes = availableMemoryBytes
        switch level {
        case .normal:
            return nil
        case .warning:
            let safeTarget = calculateSafeGuestRAM(availableMemoryBytes: availableMemoryBytes)
            return QMPCommand(execute: "balloon", arguments: ["value": Int64(safeTarget)])
        case .critical:
            let safeTarget = calculateSafeGuestRAM(availableMemoryBytes: availableMemoryBytes)
            let emergencyTarget = max(self.minSafeFloorBytes, safeTarget / 2)
            return QMPCommand(execute: "balloon", arguments: ["value": Int64(emergencyTarget)])
        }
    }

    /// Evaluates real-time usage against Jetsam ceiling; returns true if usage >= 90%.
    public func checkJetsamEmergency(currentUsageBytes: UInt64, memoryCeilingBytes: UInt64) -> Bool {
        self.currentUsageBytes = currentUsageBytes
        self.memoryCeilingBytes = memoryCeilingBytes

        if memoryCeilingBytes <= 0 {
            self.isEmergencyPaused = true
            return true
        }

        let dangerLimit = Double(memoryCeilingBytes) * self.dangerThresholdPercent
        let exceeds = Double(currentUsageBytes) >= dangerLimit
        if exceeds {
            self.isEmergencyPaused = true
        }
        return exceeds
    }

    /// Issues emergency QMP stop command to prevent iOS kernel SIGKILL.
    public func emergencyAutoPause() -> QMPCommand {
        self.isEmergencyPaused = true
        return QMPCommand(execute: "stop", arguments: [:])
    }

    /// Issues QMP cont command after memory pressure normalizes.
    public func resumeExecution() -> QMPCommand {
        self.isEmergencyPaused = false
        return QMPCommand(execute: "cont", arguments: [:])
    }
}
