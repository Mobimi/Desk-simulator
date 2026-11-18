//
//  ThermalMonitor.swift
//  Management/Runtime
//
//  Monitors iOS thermal state to prevent aggressive Apple Silicon throttling,
//  coordinating with PCoreScheduler's Dynamic Core Boost state machine.
//

import Foundation
import Combine

public enum ThermalAlertLevel: String {
    case nominal = "Mát mẻ"
    case fair = "Ấm nhẹ"
    case serious = "Nóng - Nguy cơ giảm xung"
    case critical = "Quá nhiệt!"

    public var iconName: String {
        switch self {
        case .nominal: return "thermometer.low"
        case .fair: return "thermometer.medium"
        case .serious: return "thermometer.high"
        case .critical: return "flame.fill"
        }
    }

    public var isWarning: Bool {
        self == .serious || self == .critical
    }
}

@MainActor
public final class ThermalMonitor: ObservableObject {
    @Published public private(set) var level: ThermalAlertLevel = .nominal

    /// Public alias for thermal alert level to support telemetry HUD and View bindings.
    public var thermalLevel: ThermalAlertLevel {
        level
    }

    @Published public private(set) var boostState: BootBoostState = .idle
    @Published public private(set) var advisoryMessage: String?

    private var observer: NSObjectProtocol?
    private var boostTimer: Timer?
    private let scheduler: PCoreScheduler

    public init(scheduler: PCoreScheduler = PCoreScheduler()) {
        self.scheduler = scheduler
        updateThermalState()
        observer = NotificationCenter.default.addObserver(
            forName: ProcessInfo.thermalStateDidChangeNotification,
            object: nil,
            queue: .main
        ) { [weak self] _ in
            Task { @MainActor in
                self?.updateThermalState()
            }
        }
    }

    deinit {
        if let observer = observer {
            NotificationCenter.default.removeObserver(observer)
        }
        boostTimer?.invalidate()
    }

    public func updateThermalState() {
        switch ProcessInfo.processInfo.thermalState {
        case .nominal:
            level = .nominal
            advisoryMessage = nil
        case .fair:
            level = .fair
            advisoryMessage = nil
        case .serious:
            level = .serious
            advisoryMessage = "iPhone đang nóng. Hệ thống khuyên bật Auto P-Core hoặc hạ bớt vCPU để giữ FPS ổn định."
            if boostState == .bootBoost {
                settleToSteadyState()
            }
        case .critical:
            level = .critical
            advisoryMessage = "Cảnh báo quá nhiệt nghiêm trọng! Hạ tải CPU tự động để tránh iOS bóp xung."
            settleToSteadyState()
        @unknown default:
            level = .nominal
            advisoryMessage = nil
        }
    }

    /// Triggers Dynamic Core Boost during initial OS boot sequence, then settles to steady-state.
    public func beginBootBoost(enabled: Bool) {
        boostTimer?.invalidate()
        guard enabled else {
            scheduler.transitionState(to: .steadyState)
            boostState = .steadyState
            return
        }

        scheduler.transitionState(to: .bootBoost)
        boostState = .bootBoost

        let duration = TimeInterval(scheduler.bootBoostTimeoutSeconds)
        boostTimer = Timer.scheduledTimer(withTimeInterval: duration, repeats: false) { [weak self] _ in
            Task { @MainActor in
                self?.settleToSteadyState()
            }
        }
    }

    public func settleToSteadyState() {
        boostTimer?.invalidate()
        boostTimer = nil
        scheduler.transitionState(to: .steadyState)
        boostState = .steadyState
    }

    public func stopSession() {
        boostTimer?.invalidate()
        boostTimer = nil
        scheduler.transitionState(to: .stopped)
        boostState = .stopped
    }
}
