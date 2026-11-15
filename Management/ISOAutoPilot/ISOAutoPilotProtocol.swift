//
//  ISOAutoPilotProtocol.swift
//  Management/ISOAutoPilot
//
//  Created for Desk-simulator Management Layer.
//

import Foundation

/// Supported guest operating system classifications.
public enum OperatingSystemType: String, Codable {
    case windows11 = "WINDOWS_11"
    case windows10 = "WINDOWS_10"
    case linuxUbuntu = "LINUX_UBUNTU"
    case unknown = "UNKNOWN"
}

/// VirtIO driver injection configuration result.
public struct VirtIOInjectionConfig: Codable, Equatable {
    public let injectDrivers: Bool
    public let nativeDrivers: Bool
    public let targetOS: OperatingSystemType
    public let drivers: [String]
    public let driveParam: String

    public init(
        injectDrivers: Bool,
        nativeDrivers: Bool = false,
        targetOS: OperatingSystemType,
        drivers: [String],
        driveParam: String
    ) {
        self.injectDrivers = injectDrivers
        self.nativeDrivers = nativeDrivers
        self.targetOS = targetOS
        self.drivers = drivers
        self.driveParam = driveParam
    }
}

/// Protocol defining ISO Auto-Pilot contracts.
public protocol ISOAutoPilotProtocol {
    /// Inspects raw ISO volume descriptor / boot header bytes to identify OS type.
    func identifyOperatingSystem(isoHeaderBytes: Data) -> OperatingSystemType

    /// Generates VirtIO-win driver bundle mounting configuration.
    func generateVirtIOInjectionConfig(osType: OperatingSystemType) -> [String: Any]

    /// Generates unattended XML response file bypassing Windows 11 hardware checks.
    func generateWindows11BypassXML(localUsername: String) -> String
}
