//
//  RuntimeMemoryMonitor.swift
//  Management/Runtime
//
//  Live Darwin memory telemetry, entitlement probing, Jetsam danger zone calculation,
//  and DispatchSource memory pressure listener driving VirtIO-Balloon and Auto-Pause.
//

import Foundation
import Combine

#if canImport(Darwin)
import Darwin
#endif

public enum JetsamDangerZone: String, Codable {
    case safe = "An toàn"
    case caution = "Cảnh báo"
    case danger = "Nguy hiểm Jetsam"

    public var descriptionText: String {
        switch self {
        case .safe:
            return "Mức RAM ổn định, an toàn trước iOS Jetsam."
        case .caution:
            return "RAM đang tiến gần giới hạn. VirtIO Balloon sẵn sàng xả bộ nhớ."
        case .danger:
            return "Chạm vùng nguy hiểm (>= 90%). Tự động tạm dừng VM để chống văng!"
        }
    }
}

@MainActor
public final class RuntimeMemoryMonitor: ObservableObject {
    public let memoryGuard: MemoryGuard

    @Published public private(set) var entitlements: MemoryEntitlements
    @Published public private(set) var physicalMemoryBytes: UInt64 = 0
    @Published public private(set) var availableMemoryBytes: UInt64 = 0
    @Published public private(set) var currentFootprintBytes: UInt64 = 0
    @Published public private(set) var safeGuestCeilingMB: Int = 1024
    @Published public private(set) var jetsamUsageRatio: Double = 0.0
    @Published public private(set) var dangerZone: JetsamDangerZone = .safe
    @Published public private(set) var pressureLevel: MemoryPressureLevel = .normal
    @Published public private(set) var lastActionLog: String = "Smart Memory Guard đang sẵn sàng."

    /// Live process memory footprint converted to Megabytes for UI telemetry display.
    public var currentUsageMB: Int {
        Int(currentFootprintBytes / (1024 * 1024))
    }

    private var pressureSource: DispatchSourceMemoryPressure?
    private var telemetryTimer: Timer?
    private var autoPauseEnabled: Bool = true
    private var onMemoryCommand: ((QMPCommand) -> Void)?

    public init() {
        let hasIncreased = desk_probe_increased_memory_entitlement()
        let hasExtendedVA = desk_probe_extended_va_entitlement()
        let guardService = MemoryGuard(
            increasedMemoryLimit: hasIncreased,
            extendedVirtualAddressing: hasExtendedVA
        )
        self.memoryGuard = guardService
        self.entitlements = guardService.detectEntitlements()
        refreshSnapshot()
    }

    deinit {
        pressureSource?.cancel()
        telemetryTimer?.invalidate()
    }

    /// Starts live polling and hooks Darwin memory pressure notifications.
    public func startMonitoring(autoPauseOnDanger: Bool, onCommand: @escaping (QMPCommand) -> Void) {
        self.autoPauseEnabled = autoPauseOnDanger
        self.onMemoryCommand = onCommand
        refreshSnapshot()

        // Hook kernel memory pressure events for immediate VirtIO-Balloon deflation
        pressureSource?.cancel()
        let source = DispatchSource.makeMemoryPressureSource(eventMask: [.warning, .critical], queue: .main)
        source.setEventHandler { [weak self] in
            guard let self = self else { return }
            let event = source.data
            let level: MemoryPressureLevel = event.contains(.critical) ? .critical : .warning
            Task { @MainActor in
                self.handleKernelPressure(level: level)
            }
        }
        source.resume()
        self.pressureSource = source

        telemetryTimer?.invalidate()
        telemetryTimer = Timer.scheduledTimer(withTimeInterval: 1.5, repeats: true) { [weak self] _ in
            Task { @MainActor in
                self?.refreshSnapshot()
            }
        }
    }

    public func stopMonitoring() {
        pressureSource?.cancel()
        pressureSource = nil
        telemetryTimer?.invalidate()
        telemetryTimer = nil
        onMemoryCommand = nil
    }

    /// Reads live Darwin memory counters and evaluates Jetsam danger thresholds.
    public func refreshSnapshot() {
        let total = desk_physical_memory_bytes()
        let avail = desk_available_memory_bytes()
        let used = desk_process_footprint_bytes()

        self.physicalMemoryBytes = total
        self.availableMemoryBytes = avail
        self.currentFootprintBytes = used

        // Compute dynamic ceiling from live available budget + active entitlement ratio
        let safeBytes = memoryGuard.calculateSafeGuestRAM(availableMemoryBytes: avail)
        let entitlementCapBytes = UInt64(Double(total) * entitlements.ceilingRatio)
        let effectiveSafeBytes = min(safeBytes, entitlementCapBytes > memoryGuard.safetyBufferBytes ? entitlementCapBytes - memoryGuard.safetyBufferBytes : memoryGuard.minSafeFloorBytes)
        self.safeGuestCeilingMB = max(1024, Int(effectiveSafeBytes / (1024 * 1024)))

        let ceilingBytes = max(1, avail + used)
        let ratio = min(1.0, Double(used) / Double(ceilingBytes))
        self.jetsamUsageRatio = ratio

        if ratio >= memoryGuard.dangerThresholdPercent {
            self.dangerZone = .danger
            if autoPauseEnabled && memoryGuard.checkJetsamEmergency(currentUsageBytes: used, memoryCeilingBytes: ceilingBytes) {
                let stopCmd = memoryGuard.emergencyAutoPause()
                self.lastActionLog = "Jetsam >= 90%! Tự động Pause máy ảo để cứu dữ liệu."
                onMemoryCommand?(stopCmd)
            }
        } else if ratio >= 0.75 {
            self.dangerZone = .caution
        } else {
            self.dangerZone = .safe
        }
    }

    /// Evaluates what Jetsam danger level a manual guest RAM slider selection represents.
    public func evaluateManualSelection(ramMB: Int) -> JetsamDangerZone {
        if ramMB <= safeGuestCeilingMB {
            return .safe
        } else if Double(ramMB) <= Double(safeGuestCeilingMB) * 1.15 {
            return .caution
        } else {
            return .danger
        }
    }

    /// Maximum manual RAM slider upper bound (in MB) based on device physical RAM.
    public var maxSelectableRAMMB: Int {
        let physicalMB = Int(physicalMemoryBytes / (1024 * 1024))
        return max(2048, min(physicalMB - 512, 8192))
    }

    private func handleKernelPressure(level: MemoryPressureLevel) {
        self.pressureLevel = level
        let avail = desk_available_memory_bytes()
        if let cmd = memoryGuard.handleMemoryPressure(level: level, availableMemoryBytes: avail) {
            let targetMB = (cmd.arguments["value"] ?? 0) / (1024 * 1024)
            self.lastActionLog = "iOS Memory Pressure (\(level.rawValue)): Gửi VirtIO-Balloon thu hồi về \(targetMB) MB."
            onMemoryCommand?(cmd)
        }
        if level == .critical && autoPauseEnabled {
            let stopCmd = memoryGuard.emergencyAutoPause()
            self.lastActionLog = "Áp lực bộ nhớ Critical! Kích hoạt tự động Pause bảo vệ tiến trình."
            onMemoryCommand?(stopCmd)
        }
    }
}
