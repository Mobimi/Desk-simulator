//
//  VMStore.swift
//  Management/Runtime
//
//  Persistent store managing user VMProfiles, APFS Sparse Disk provisioning,
//  and unattended ISO Auto-Pilot artifacts.
//

import Foundation
import Combine

@MainActor
public final class VMStore: ObservableObject {
    @Published public private(set) var profiles: [VMProfile] = []
    @Published public var lastErrorMessage: String?

    public let storageBridge: StorageBridge
    public let isoAutoPilot: ISOAutoPilot
    public let vmsDirectory: URL
    private let profilesFileURL: URL

    public init(baseDirectory: URL? = nil) {
        let docs = baseDirectory ?? FileManager.default.urls(for: .documentDirectory, in: .userDomainMask).first ?? FileManager.default.temporaryDirectory
        let rootDir = docs.appendingPathComponent("DeskSimulator", isDirectory: true)
        self.vmsDirectory = rootDir.appendingPathComponent("VMs", isDirectory: true)
        self.profilesFileURL = rootDir.appendingPathComponent("profiles.json")
        let shareDir = rootDir.appendingPathComponent("SharedFiles", isDirectory: true)

        try? FileManager.default.createDirectory(at: vmsDirectory, withIntermediateDirectories: true)
        try? FileManager.default.createDirectory(at: shareDir, withIntermediateDirectories: true)

        self.storageBridge = StorageBridge(stagingDirectory: shareDir)
        self.isoAutoPilot = ISOAutoPilot()
        loadProfiles()
    }

    public func loadProfiles() {
        guard FileManager.default.fileExists(atPath: profilesFileURL.path) else {
            self.profiles = []
            return
        }
        do {
            let data = try Data(contentsOf: profilesFileURL)
            self.profiles = try JSONDecoder().decode([VMProfile].self, from: data)
        } catch {
            self.lastErrorMessage = "Không thể đọc danh sách máy ảo: \(error.localizedDescription)"
            self.profiles = []
        }
    }

    public func saveProfiles() {
        do {
            let encoder = JSONEncoder()
            encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
            let data = try encoder.encode(profiles)
            try data.write(to: profilesFileURL, options: .atomic)
        } catch {
            self.lastErrorMessage = "Lỗi lưu cấu hình máy ảo: \(error.localizedDescription)"
        }
    }

    /// Creates a new VM with a pre-allocated APFS Sparse Disk and optional unattended XML bypass.
    @discardableResult
    public func createVM(
        name: String,
        architecture: TargetArchitecture,
        osType: OperatingSystemType,
        useCase: VMUseCase,
        powerProfile: VMPowerProfile,
        diskSizeGB: Int,
        isoImagePath: String? = nil,
        isSmartMemoryEnabled: Bool = true,
        manualRAMMB: Int = 2048,
        win11BypassEnabled: Bool = true
    ) -> VMProfile {
        let vmID = UUID()
        let vmFolder = vmsDirectory.appendingPathComponent(vmID.uuidString, isDirectory: true)
        try? FileManager.default.createDirectory(at: vmFolder, withIntermediateDirectories: true)

        let diskURL = vmFolder.appendingPathComponent("disk.img")
        let sizeBytes = UInt64(max(4, diskSizeGB)) * 1024 * 1024 * 1024
        _ = try? storageBridge.allocateSparseDisk(targetPath: diskURL.path, sizeBytes: sizeBytes)

        // Generate unattended Windows 11 bypass XML automatically when applicable
        if win11BypassEnabled && (osType == .windows11 || osType == .windows10) {
            let xml = isoAutoPilot.generateWindows11BypassXML(localUsername: "DeskUser")
            let xmlURL = vmFolder.appendingPathComponent("autounattend.xml")
            try? xml.write(to: xmlURL, atomically: true, encoding: .utf8)
        }

        let profile = VMProfile(
            id: vmID,
            name: name.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty ? "Máy ảo PC" : name,
            architecture: architecture,
            osType: osType,
            useCase: useCase,
            powerProfile: powerProfile,
            isSmartMemoryEnabled: isSmartMemoryEnabled,
            manualRAMMB: manualRAMMB,
            tbSizeMB: powerProfile.recommendedTBSizeMB,
            refreshRateHz: powerProfile.recommendedRefreshRateHz,
            diskSizeGB: diskSizeGB,
            diskImagePath: diskURL.path,
            isoImagePath: isoImagePath,
            virtIOInjectionEnabled: (osType == .windows11 || osType == .windows10),
            win11BypassEnabled: win11BypassEnabled
        )

        profiles.insert(profile, at: 0)
        saveProfiles()
        return profile
    }

    /// 1-Click creation directly from the curated Template Catalog.
    @discardableResult
    public func createVM(from template: VMTemplate) -> VMProfile {
        return createVM(
            name: template.title,
            architecture: template.architecture,
            osType: template.osType,
            useCase: template.id.contains("ubuntu") ? .development : .office,
            powerProfile: .balanced,
            diskSizeGB: template.diskSizeGB,
            isSmartMemoryEnabled: true,
            manualRAMMB: template.recommendedRAMMB,
            win11BypassEnabled: template.osType == .windows11
        )
    }

    public func updateProfile(_ updated: VMProfile) {
        if let idx = profiles.firstIndex(where: { $0.id == updated.id }) {
            profiles[idx] = updated
            saveProfiles()
        }
    }

    public func deleteProfile(_ profile: VMProfile) {
        profiles.removeAll { $0.id == profile.id }
        let vmFolder = vmsDirectory.appendingPathComponent(profile.id.uuidString, isDirectory: true)
        try? FileManager.default.removeItem(at: vmFolder)
        saveProfiles()
    }

    public func markBooted(_ profileID: UUID) {
        if let idx = profiles.firstIndex(where: { $0.id == profileID }) {
            profiles[idx].lastBootedAt = Date()
            saveProfiles()
        }
    }
}
