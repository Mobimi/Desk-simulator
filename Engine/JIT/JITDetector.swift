//
//  JITDetector.swift
//  Desk-simulator Engine Layer
//
//  Runtime JIT entitlement detection (CS_DEBUGGED, TrollStore, AltJIT, SideStore).
//

import Foundation

#if canImport(Darwin)
import Darwin
#endif

public enum JITSource: String, CaseIterable, Codable {
    case trollStore = "TROLLSTORE"
    case altJIT = "ALTJIT"
    case sideStore = "SIDESTORE"
    case none = "NONE"

    public var displayName: String {
        switch self {
        case .trollStore:
            return "TrollStore (Unrestricted CS_DEBUGGED)"
        case .altJIT:
            return "AltJIT (AltServer JIT Attach)"
        case .sideStore:
            return "SideStore (Local VPN WireGuard JIT)"
        case .none:
            return "No JIT Active"
        }
    }
}

public struct JITStatus: Codable {
    public let isAvailable: Bool
    public let source: JITSource
    public let advisory: String

    public init(isAvailable: Bool, source: JITSource, advisory: String) {
        self.isAvailable = isAvailable
        self.source = source
        self.advisory = advisory
    }
}

public final class JITDetector {
    /// Detects runtime JIT availability for the current process.
    public static func detectJIT(hasCSDebugged: Bool? = nil, envMarker: String? = nil) -> JITStatus {
        let isDebugged: Bool
        if let explicit = hasCSDebugged {
            isDebugged = explicit
        } else {
            // Darwin CS_DEBUGGED probe representation
            #if targetEnvironment(simulator)
            isDebugged = true
            #else
            isDebugged = checkKernelDebugFlag()
            #endif
        }

        let marker = envMarker ?? ProcessInfo.processInfo.environment["JIT_SOURCE"] ?? ""
        let lower = marker.lowercased()

        if isDebugged {
            let source: JITSource
            if lower.contains("trollstore") {
                source = .trollStore
            } else if lower.contains("sidestore") {
                source = .sideStore
            } else {
                source = .altJIT
            }
            return JITStatus(
                isAvailable: true,
                source: source,
                advisory: "JIT is active via \(source.displayName). TCG code cache enabled."
            )
        } else {
            return JITStatus(
                isAvailable: false,
                source: .none,
                advisory: "JIT is not active. Please enable JIT via SideStore or AltStore to launch VM."
            )
        }
    }

    private static func checkKernelDebugFlag() -> Bool {
        #if canImport(Darwin)
        return desk_is_jit_enabled()
        #else
        return false
        #endif
    }
}
