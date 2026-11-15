//
//  PCoreSchedulerProtocol.swift
//  Management/PCoreScheduler
//
//  Created for Desk-simulator Management Layer.
//

import Foundation

/// Standard Darwin QoS class identifiers.
public enum DarwinQoSClass: UInt32 {
    case userInteractive = 0x21
    case userInitiated = 0x19
    case utility = 0x11
    case background = 0x09
}

/// Dynamic Boot Boost state machine states.
public enum BootBoostState: String, Codable {
    case idle = "IDLE"
    case booting = "BOOTING"
    case bootBoost = "BOOT_BOOST"
    case running = "RUNNING"
    case steadyState = "STEADY_STATE"
    case stopped = "STOPPED"
}

/// Topology assignment result structure.
public struct TopologyAssignment: Codable, Equatable {
    public let vcpus: Int
    public let pcoreAffinity: [Int]

    public init(vcpus: Int, pcoreAffinity: [Int]) {
        self.vcpus = vcpus
        self.pcoreAffinity = pcoreAffinity
    }
}

/// Protocol defining P-Core Scheduler interface contracts.
public protocol PCoreSchedulerProtocol {
    /// Default vCPU allocation (2 physical P-cores).
    var defaultVCPUs: Int { get }

    /// Timeout in seconds before boot boost de-escalates to steady state.
    var bootBoostTimeoutSeconds: Int { get }

    /// Current state in the Boot Boost state machine.
    var currentState: BootBoostState { get }

    /// Discovers the physical performance core (P-core) count via sysctl (`hw.perflevel0.physicalcpu`).
    func getPhysicalPCoreCount() -> Int

    /// Assigns vCPU topology restricted to physical P-cores avoiding E-core scheduling stutter.
    func assignTopology(pCores: Int) -> TopologyAssignment

    /// Clamps user-requested vCPU count within safe physical P-core boundaries [1, pCores].
    func clampVCPUs(requested: Int, pCores: Int) -> Int

    /// Elevates thread priority to Mach User Interactive QoS (`QOS_CLASS_USER_INTERACTIVE`).
    func setThreadInteractiveQoS() -> Bool

    /// Elevates thread QoS for vCPU thread or auxiliary thread.
    func elevateQoS(threadId: String, isVCPU: Bool) -> UInt32

    /// Demotes background auxiliary threads to background QoS.
    func demoteQoSBackground(threadId: String) -> UInt32

    /// Transitions the Dynamic Boot Boost state machine (`BOOTING` -> `RUNNING`).
    func updateBootBoostState(isBooting: Bool)
}
