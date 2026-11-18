//
//  VMProfile.swift
//  Management/Runtime
//
//  Persistent Virtual Machine profile model, Needs-Based presets, and 1-Click Template Catalog.
//

import Foundation

public enum VMUseCase: String, CaseIterable, Codable, Identifiable {
    case gaming = "Chơi game PC"
    case office = "Văn phòng & Học tập"
    case development = "Lập trình & Vọc vạch"

    public var id: String { rawValue }

    public var iconName: String {
        switch self {
        case .gaming: return "gamecontroller.fill"
        case .office: return "doc.text.fill"
        case .development: return "terminal.fill"
        }
    }

    public var subtitle: String {
        switch self {
        case .gaming: return "Ưu tiên FPS cao, bật Gamepad ảo & VirtIO-GPU 120Hz"
        case .office: return "Cân bằng RAM/Pin, bật đồng bộ Clipboard & Share Sheet"
        case .development: return "Ưu tiên tốc độ ổ đĩa APFS Sparse & phím tắt Terminal"
        }
    }
}

public enum VMPowerProfile: String, CaseIterable, Codable, Identifiable {
    case batterySaver = "Tiết kiệm pin & Mát máy"
    case balanced = "Cân bằng (Khuyên dùng)"
    case maxPerformance = "Hiệu năng tối đa"

    public var id: String { rawValue }

    public var recommendedTBSizeMB: Int {
        switch self {
        case .batterySaver: return 128
        case .balanced: return 192
        case .maxPerformance: return 256
        }
    }

    public var recommendedRefreshRateHz: Int {
        switch self {
        case .batterySaver: return 60
        case .balanced: return 60
        case .maxPerformance: return 120
        }
    }
}

public struct VMProfile: Identifiable, Codable, Equatable {
    public var id: UUID
    public var name: String
    public var architecture: TargetArchitecture
    public var osType: OperatingSystemType
    public var useCase: VMUseCase
    public var powerProfile: VMPowerProfile

    // Smart Memory Guard settings
    public var isSmartMemoryEnabled: Bool
    public var manualRAMMB: Int
    public var autoPauseOnJetsamDanger: Bool

    // P-Core Scheduler settings
    public var isAutoPCoreEnabled: Bool
    public var manualVCPUs: Int
    public var dynamicCoreBoostEnabled: Bool
    public var thermalAlertsEnabled: Bool

    // Engine & Display settings
    public var tbSizeMB: Int
    public var refreshRateHz: Int

    // Storage & ISO Auto-Pilot settings
    public var diskSizeGB: Int
    public var diskImagePath: String
    public var isoImagePath: String?
    public var virtIOInjectionEnabled: Bool
    public var win11BypassEnabled: Bool
    public var clipboardSyncEnabled: Bool
    public var sharedFolderEnabled: Bool

    public var createdAt: Date
    public var lastBootedAt: Date?

    public init(
        id: UUID = UUID(),
        name: String,
        architecture: TargetArchitecture = .aarch64,
        osType: OperatingSystemType = .windows11,
        useCase: VMUseCase = .office,
        powerProfile: VMPowerProfile = .balanced,
        isSmartMemoryEnabled: Bool = true,
        manualRAMMB: Int = 2048,
        autoPauseOnJetsamDanger: Bool = true,
        isAutoPCoreEnabled: Bool = true,
        manualVCPUs: Int = 2,
        dynamicCoreBoostEnabled: Bool = true,
        thermalAlertsEnabled: Bool = true,
        tbSizeMB: Int = 128,
        refreshRateHz: Int = 120,
        diskSizeGB: Int = 32,
        diskImagePath: String = "",
        isoImagePath: String? = nil,
        virtIOInjectionEnabled: Bool = true,
        win11BypassEnabled: Bool = true,
        clipboardSyncEnabled: Bool = true,
        sharedFolderEnabled: Bool = true,
        createdAt: Date = Date(),
        lastBootedAt: Date? = nil
    ) {
        self.id = id
        self.name = name
        self.architecture = architecture
        self.osType = osType
        self.useCase = useCase
        self.powerProfile = powerProfile
        self.isSmartMemoryEnabled = isSmartMemoryEnabled
        self.manualRAMMB = manualRAMMB
        self.autoPauseOnJetsamDanger = autoPauseOnJetsamDanger
        self.isAutoPCoreEnabled = isAutoPCoreEnabled
        self.manualVCPUs = manualVCPUs
        self.dynamicCoreBoostEnabled = dynamicCoreBoostEnabled
        self.thermalAlertsEnabled = thermalAlertsEnabled
        self.tbSizeMB = QEMUArgumentsBuilder.clampTCGSize(tbSizeMB)
        self.refreshRateHz = refreshRateHz
        self.diskSizeGB = diskSizeGB
        self.diskImagePath = diskImagePath
        self.isoImagePath = isoImagePath
        self.virtIOInjectionEnabled = virtIOInjectionEnabled
        self.win11BypassEnabled = win11BypassEnabled
        self.clipboardSyncEnabled = clipboardSyncEnabled
        self.sharedFolderEnabled = sharedFolderEnabled
        self.createdAt = createdAt
        self.lastBootedAt = lastBootedAt
    }

    /// Generates a validated QEMUConfiguration respecting Smart Memory Guard & P-Core limits.
    public func makeQEMUConfiguration(safeRAMMB: Int, physicalPCores: Int, socketBaseDir: String) -> QEMUConfiguration {
        let effectiveRAM = isSmartMemoryEnabled ? safeRAMMB : manualRAMMB
        let effectiveVCPUs = isAutoPCoreEnabled ? max(1, min(physicalPCores, 2)) : max(1, manualVCPUs)
        let shortId = String(id.uuidString.prefix(8))
        let spiceSock = "\(socketBaseDir)/sp_\(shortId).sock"
        let qmpSock = "\(socketBaseDir)/qm_\(shortId).sock"

        var extraArgs: [String] = []
        if architecture == .aarch64 {
            extraArgs.append(contentsOf: ["-M", "virt", "-cpu", "max"])
        } else {
            extraArgs.append(contentsOf: ["-M", "q35", "-cpu", "max"])
        }
        // Enable VirtIO-Balloon device for Darwin Memory Pressure reclamation
        extraArgs.append(contentsOf: ["-device", "virtio-balloon-pci"])

        return QEMUConfiguration(
            architecture: architecture,
            ramMB: max(512, effectiveRAM),
            tbSizeMB: QEMUArgumentsBuilder.clampTCGSize(tbSizeMB),
            vCPUs: effectiveVCPUs,
            spiceSocketPath: spiceSock,
            qmpSocketPath: qmpSock,
            diskImagePath: diskImagePath.isEmpty ? nil : diskImagePath,
            cdromImagePath: isoImagePath,
            disableSmartcard: true,
            additionalArgs: extraArgs
        )
    }
}

/// Curated 1-Click Template Catalog item for effortless setup.
public struct VMTemplate: Identifiable, Hashable {
    public let id: String
    public let title: String
    public let badge: String
    public let summary: String
    public let architecture: TargetArchitecture
    public let osType: OperatingSystemType
    public let recommendedRAMMB: Int
    public let diskSizeGB: Int
    public let estimatedDownloadSize: String
    public let iconName: String
    public let accentHex: String

    public static let catalog: [VMTemplate] = [
        VMTemplate(
            id: "tiny11-arm64",
            title: "Tiny11 ARM64 (Tối ưu iPhone)",
            badge: "Khuyên dùng",
            summary: "Windows 11 siêu nhẹ đã lược bỏ Bloatware, nhúng sẵn VirtIO & Bypass TPM 2.0. Mượt nhất trên chip Apple.",
            architecture: .aarch64,
            osType: .windows11,
            recommendedRAMMB: 2048,
            diskSizeGB: 32,
            estimatedDownloadSize: "2.8 GB",
            iconName: "desktopcomputer",
            accentHex: "3B82F6"
        ),
        VMTemplate(
            id: "tiny10-x64",
            title: "Tiny10 x86_64 Classic",
            badge: "Tương thích cao",
            summary: "Windows 10 64-bit tinh giản chạy phần mềm & game PC cổ điển, đã nhúng sẵn driver mạng & đĩa VirtIO.",
            architecture: .x86_64,
            osType: .windows10,
            recommendedRAMMB: 2048,
            diskSizeGB: 24,
            estimatedDownloadSize: "2.1 GB",
            iconName: "laptopcomputer",
            accentHex: "0EA5E9"
        ),
        VMTemplate(
            id: "alpine-desktop-arm64",
            title: "Alpine Linux XFCE Siêu Nhẹ",
            badge: "Khởi động 5 giây",
            summary: "Hệ điều hành Linux giao diện đồ họa đầy đủ, chỉ ăn ~250MB RAM, không bao giờ lo Jetsam trên iPhone 4GB RAM.",
            architecture: .aarch64,
            osType: .linuxUbuntu,
            recommendedRAMMB: 1024,
            diskSizeGB: 8,
            estimatedDownloadSize: "320 MB",
            iconName: "bolt.shield.fill",
            accentHex: "10B981"
        ),
        VMTemplate(
            id: "ubuntu-arm64",
            title: "Ubuntu 24.04 Desktop ARM64",
            badge: "Lập trình",
            summary: "Môi trường Linux đầy đủ cho lập trình, Docker/SSH, VS Code và học tập với driver VirtIO tích hợp sẵn.",
            architecture: .aarch64,
            osType: .linuxUbuntu,
            recommendedRAMMB: 2048,
            diskSizeGB: 24,
            estimatedDownloadSize: "1.9 GB",
            iconName: "terminal.fill",
            accentHex: "F97316"
        )
    ]
}
