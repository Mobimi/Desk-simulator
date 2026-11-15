//
//  ISOAutoPilot.swift
//  Management/ISOAutoPilot
//
//  Production implementation of ISO Auto-Pilot for Desk-simulator.
//

import Foundation

/// Production service implementing ISO Auto-Pilot.
public class ISOAutoPilot: ISOAutoPilotProtocol {
    public init() {}

    /// Inspects raw ISO volume descriptor / boot header bytes to identify OS type.
    public func identifyOperatingSystem(isoHeaderBytes: Data) -> OperatingSystemType {
        guard isoHeaderBytes.count >= 16 else {
            return .unknown
        }

        // Strip null bytes to handle UTF-16 LE / BE and Joliet/UDF encoded volume descriptors
        let nonNullBytes = isoHeaderBytes.filter { $0 != 0 }
        let asciiString = String(decoding: nonNullBytes, as: UTF8.self).uppercased()

        if asciiString.contains("MICROSOFT WINDOWS 11") || asciiString.contains("WIN11") {
            return .windows11
        }
        if asciiString.contains("MICROSOFT WINDOWS 10") || asciiString.contains("WIN10") {
            return .windows10
        }
        if asciiString.contains("UBUNTU") || asciiString.contains("LINUX") {
            return .linuxUbuntu
        }

        return .unknown
    }

    /// Generates VirtIO-win driver bundle mounting configuration.
    public func generateVirtIOInjectionConfig(osType: OperatingSystemType) -> [String: Any] {
        switch osType {
        case .windows11, .windows10:
            return [
                "inject_drivers": true,
                "native_drivers": false,
                "target_os": osType.rawValue,
                "drivers": ["viostor", "netkvm", "balloon", "vioscsi", "qxl"],
                "drive_param": "-drive file=virtio-win.iso,media=cdrom,readonly=on"
            ]
        case .linuxUbuntu:
            return [
                "inject_drivers": false,
                "native_drivers": true,
                "target_os": osType.rawValue,
                "drivers": ["virtio_pci", "virtio_blk", "virtio_net"],
                "drive_param": ""
            ]
        case .unknown:
            return [
                "inject_drivers": false,
                "native_drivers": false,
                "target_os": OperatingSystemType.unknown.rawValue,
                "drivers": [String](),
                "drive_param": ""
            ]
        }
    }

    /// Generates unattended XML response file bypassing Windows 11 hardware checks.
    public func generateWindows11BypassXML(localUsername: String) -> String {
        // Strip control characters (including \r, \n) and leading/trailing whitespace
        let stripped = localUsername.components(separatedBy: .controlCharacters).joined()
            .trimmingCharacters(in: .whitespacesAndNewlines)
        let cleanUsername = stripped.isEmpty ? "DeskUser" : stripped

        // XML entity escaping: ampersand MUST be replaced first
        let safeUsername = cleanUsername
            .replacingOccurrences(of: "&", with: "&amp;")
            .replacingOccurrences(of: "<", with: "&lt;")
            .replacingOccurrences(of: ">", with: "&gt;")
            .replacingOccurrences(of: "\"", with: "&quot;")
            .replacingOccurrences(of: "'", with: "&apos;")

        return """
<?xml version="1.0" encoding="utf-8"?>
<unattend xmlns="urn:schemas-microsoft-com:unattend">
    <settings pass="windowsPE">
        <component name="Microsoft-Windows-Setup" processorArchitecture="amd64" publicKeyToken="31bf3856ad364e35" language="neutral" versionScope="nonSxS">
            <RunSynchronous>
                <RunSynchronousCommand wcm:action="add" xmlns:wcm="http://schemas.microsoft.com/WMIConfig/2002/State">
                    <Order>1</Order>
                    <Path>reg add HKLM\\SYSTEM\\Setup\\LabConfig /v BypassTPMCheck /t REG_DWORD /d 1 /f</Path>
                </RunSynchronousCommand>
                <RunSynchronousCommand wcm:action="add" xmlns:wcm="http://schemas.microsoft.com/WMIConfig/2002/State">
                    <Order>2</Order>
                    <Path>reg add HKLM\\SYSTEM\\Setup\\LabConfig /v BypassSecureBootCheck /t REG_DWORD /d 1 /f</Path>
                </RunSynchronousCommand>
                <RunSynchronousCommand wcm:action="add" xmlns:wcm="http://schemas.microsoft.com/WMIConfig/2002/State">
                    <Order>3</Order>
                    <Path>reg add HKLM\\SYSTEM\\Setup\\LabConfig /v BypassRAMCheck /t REG_DWORD /d 1 /f</Path>
                </RunSynchronousCommand>
                <RunSynchronousCommand wcm:action="add" xmlns:wcm="http://schemas.microsoft.com/WMIConfig/2002/State">
                    <Order>4</Order>
                    <Path>reg add HKLM\\SYSTEM\\Setup\\LabConfig /v BypassCPUCheck /t REG_DWORD /d 1 /f</Path>
                </RunSynchronousCommand>
                <RunSynchronousCommand wcm:action="add" xmlns:wcm="http://schemas.microsoft.com/WMIConfig/2002/State">
                    <Order>5</Order>
                    <Path>reg add HKLM\\SYSTEM\\Setup\\LabConfig /v BypassStorageCheck /t REG_DWORD /d 1 /f</Path>
                </RunSynchronousCommand>
            </RunSynchronous>
            <UserData>
                <AcceptEula>true</AcceptEula>
            </UserData>
        </component>
    </settings>
    <settings pass="oobeSystem">
        <component name="Microsoft-Windows-Shell-Setup" processorArchitecture="amd64" publicKeyToken="31bf3856ad364e35" language="neutral" versionScope="nonSxS">
            <UserAccounts>
                <LocalAccounts>
                    <LocalAccount wcm:action="add" xmlns:wcm="http://schemas.microsoft.com/WMIConfig/2002/State">
                        <Name>\(safeUsername)</Name>
                        <Group>Administrators</Group>
                    </LocalAccount>
                </LocalAccounts>
            </UserAccounts>
        </component>
    </settings>
</unattend>
"""
    }
}
