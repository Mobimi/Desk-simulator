//
//  SetupWizardViewModel.swift
//  UI/ViewModels
//
//  Powers the Tri-Mode Setup Wizard:
//  1. 1-Click Template Catalog
//  2. Smart ISO Auto-Pilot (auto-detects OS, injects VirtIO & Win11 Bypass)
//  3. Needs-Based Configurator (Gaming / Office / Development)
//

import Foundation
import Combine

public enum SetupWizardMode: String, CaseIterable, Identifiable {
    case templates = "Kho 1-Click"
    case isoAutoPilot = "Nạp ISO Tự Động"
    case needsWizard = "Theo Nhu Cầu"

    public var id: String { rawValue }
}

@MainActor
public final class SetupWizardViewModel: ObservableObject {
    @Published public var mode: SetupWizardMode = .templates

    // Smart ISO Auto-Pilot state
    @Published public var selectedISOURL: URL?
    @Published public var detectedOS: OperatingSystemType = .unknown
    @Published public var detectedArchitecture: TargetArchitecture = .aarch64
    @Published public var virtIOConfigSummary: String = "Chưa nạp file ISO"
    @Published public var autoInjectVirtIO: Bool = true
    @Published public var autoBypassWin11: Bool = true

    // Needs-Based Wizard state
    @Published public var vmName: String = ""
    @Published public var selectedUseCase: VMUseCase = .office
    @Published public var selectedPowerProfile: VMPowerProfile = .balanced
    @Published public var diskSizeGB: Int = 32
    @Published public var useSmartMemoryGuard: Bool = true
    @Published public var manualRAMMB: Int = 2048

    private let isoAutoPilot: ISOAutoPilot

    public init(isoAutoPilot: ISOAutoPilot = ISOAutoPilot(), initialISOURL: URL? = nil) {
        self.isoAutoPilot = isoAutoPilot
        if let url = initialISOURL {
            self.mode = .isoAutoPilot
            inspectISO(at: url)
        }
    }

    /// Reads the ISO primary volume descriptor (32KB–64KB) and runs Smart ISO Auto-Pilot analysis.
    public func inspectISO(at url: URL) {
        self.selectedISOURL = url
        let accessing = url.startAccessingSecurityScopedResource()
        defer { if accessing { url.stopAccessingSecurityScopedResource() } }

        var headerData = Data()
        if let handle = try? FileHandle(forReadingFrom: url) {
            defer { try? handle.close() }
            // ISO 9660 Primary Volume Descriptor starts at sector 16 (32,768 bytes)
            try? handle.seek(toOffset: 32_768)
            if let chunk = try? handle.read(upToCount: 4096) {
                headerData.append(chunk)
            }
        }

        // Also mix filename hint if header read failed or was minimal
        if let nameData = url.lastPathComponent.data(using: .utf8) {
            headerData.append(nameData)
        }

        let identified = isoAutoPilot.identifyOperatingSystem(isoHeaderBytes: headerData)
        self.detectedOS = identified

        let lowerName = url.lastPathComponent.lowercased()
        if lowerName.contains("arm64") || lowerName.contains("aarch64") {
            self.detectedArchitecture = .aarch64
        } else if lowerName.contains("x64") || lowerName.contains("x86") || lowerName.contains("amd64") {
            self.detectedArchitecture = .x86_64
        } else {
            self.detectedArchitecture = (identified == .windows11) ? .aarch64 : .x86_64
        }

        if vmName.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
            vmName = url.deletingPathExtension().lastPathComponent
        }

        let virtIOConfig = isoAutoPilot.generateVirtIOInjectionConfig(osType: identified)
        let inject = (virtIOConfig["inject_drivers"] as? Bool) ?? false
        let native = (virtIOConfig["native_drivers"] as? Bool) ?? false
        let drivers = (virtIOConfig["drivers"] as? [String]) ?? []

        self.autoInjectVirtIO = inject
        self.autoBypassWin11 = (identified == .windows11 || identified == .windows10)

        if inject {
            self.virtIOConfigSummary = "Tự động nhúng driver VirtIO ngầm (\(drivers.joined(separator: ", "))) + tự tạo autounattend.xml bỏ qua TPM 2.0 & MS Account."
        } else if native {
            self.virtIOConfigSummary = "Linux hỗ trợ sẵn VirtIO Native (\(drivers.joined(separator: ", "))) — không cần nạp thêm đĩa driver."
        } else {
            self.virtIOConfigSummary = "Cấu hình chuẩn tương thích tối đa (VirtIO + SPICE Unix Socket)."
        }
    }

    public func buildProfile(using store: VMStore) -> VMProfile {
        let finalName: String
        if !vmName.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
            finalName = vmName
        } else {
            switch selectedUseCase {
            case .gaming: finalName = "PC Chơi Game"
            case .office: finalName = "Windows Văn Phòng"
            case .development: finalName = "Linux Lập Trình"
            }
        }

        let targetArch: TargetArchitecture
        let targetOS: OperatingSystemType
        if mode == .isoAutoPilot {
            targetArch = detectedArchitecture
            targetOS = detectedOS
        } else {
            switch selectedUseCase {
            case .gaming:
                targetArch = .x86_64
                targetOS = .windows10
            case .office:
                targetArch = .aarch64
                targetOS = .windows11
            case .development:
                targetArch = .aarch64
                targetOS = .linuxUbuntu
            }
        }

        return store.createVM(
            name: finalName,
            architecture: targetArch,
            osType: targetOS,
            useCase: selectedUseCase,
            powerProfile: selectedPowerProfile,
            diskSizeGB: diskSizeGB,
            isoImagePath: selectedISOURL?.path,
            isSmartMemoryEnabled: useSmartMemoryGuard,
            manualRAMMB: manualRAMMB,
            win11BypassEnabled: autoBypassWin11
        )
    }
}
