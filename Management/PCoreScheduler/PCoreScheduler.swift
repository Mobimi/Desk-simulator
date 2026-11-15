//
//  PCoreScheduler.swift
//  Management/PCoreScheduler
//
//  Production implementation of P-Core Scheduler for Apple Silicon.
//

import Foundation

#if canImport(Darwin)
import Darwin
#endif

/// Production service implementing P-Core Scheduler.
public class PCoreScheduler: PCoreSchedulerProtocol {
    /// Default vCPUs pinned strictly to 2 physical P-cores.
    public let defaultVCPUs: Int = 2

    /// Boot boost duration limit (120 seconds).
    public let bootBoostTimeoutSeconds: Int = 120

    /// Active state of the boot boost state machine.
    public private(set) var currentState: BootBoostState = .idle

    /// Cached count of physical P-cores.
    public private(set) var detectedPCores: Int = 2

    /// Thread QoS registration mapping.
    public private(set) var threadRegistry: [String: UInt32] = [:]

    /// Timestamp when boot boost started.
    public private(set) var bootStartTime: Date?

    public init(forcedPCores: Int? = nil) {
        if let forced = forcedPCores {
            self.detectedPCores = max(1, forced)
        } else {
            self.detectedPCores = self.discoverPCores()
        }
    }

    /// Discovers physical P-core count on Apple Silicon via sysctl `hw.perflevel0.physicalcpu`.
    private func discoverPCores() -> Int {
        #if canImport(Darwin)
        var pCores: Int32 = 0
        var size = MemoryLayout<Int32>.size
        let result = sysctlbyname("hw.perflevel0.physicalcpu", &pCores, &size, nil, 0)
        if result == 0 && pCores > 0 {
            return Int(pCores)
        }
        #endif
        // Fallback: Default modern Apple Silicon iPhone has 2 P-cores (A15-A18)
        return self.defaultVCPUs
    }

    /// Returns physical P-core count.
    public func getPhysicalPCoreCount() -> Int {
        return self.detectedPCores
    }

    /// Assigns vCPU topology pinned strictly to physical P-cores.
    public func assignTopology(pCores: Int = 2) -> TopologyAssignment {
        let effectivePCores = pCores > 0 ? pCores : self.detectedPCores
        let assigned = min(effectivePCores, self.defaultVCPUs)
        let affinity = Array(0..<assigned)
        return TopologyAssignment(vcpus: assigned, pcoreAffinity: affinity)
    }

    /// Clamps requested vCPUs safely within physical P-core limits [1, pCores].
    public func clampVCPUs(requested: Int, pCores: Int = 2) -> Int {
        let maxAllowed = max(1, pCores)
        return max(1, min(requested, maxAllowed))
    }

    /// Elevates current thread priority to Mach User Interactive QoS.
    public func setThreadInteractiveQoS() -> Bool {
        #if canImport(Darwin)
        let status = pthread_set_qos_class_self_np(QOS_CLASS_USER_INTERACTIVE, 0)
        return status == 0
        #else
        return true
        #endif
    }

    /// Elevates QoS for thread handle and records in registry.
    public func elevateQoS(threadId: String, isVCPU: Bool = true) -> UInt32 {
        let qos = isVCPU ? DarwinQoSClass.userInteractive.rawValue : DarwinQoSClass.userInitiated.rawValue
        self.threadRegistry[threadId] = qos
        return qos
    }

    /// Demotes auxiliary background thread to background QoS.
    public func demoteQoSBackground(threadId: String) -> UInt32 {
        let qos = DarwinQoSClass.background.rawValue
        self.threadRegistry[threadId] = qos
        return qos
    }

    /// Transitions the Dynamic Boot Boost state machine (`BOOTING` -> `RUNNING`).
    public func updateBootBoostState(isBooting: Bool) {
        if isBooting {
            self.currentState = .booting
            self.bootStartTime = Date()
        } else {
            self.currentState = .running
            self.bootStartTime = nil
        }
    }

    /// Transitions to arbitrary state in state machine.
    public func transitionState(to newState: BootBoostState) {
        self.currentState = newState
        if newState == .booting || newState == .bootBoost {
            self.bootStartTime = Date()
        } else if newState == .running || newState == .steadyState || newState == .stopped {
            self.bootStartTime = nil
        }
    }
}
