//
//  VMSessionViewModel.swift
//  UI/ViewModels
//
//  Runtime ViewModel managing an active VM display session, Metal 120Hz rendering,
//  Smart Memory Guard live enforcement, P-Core Dynamic Boost, and Input HUD controls.
//

import Foundation
import Combine

#if canImport(UIKit)
import UIKit
#endif

#if canImport(GameController)
import GameController
#endif

public enum InputHUDMode: String, CaseIterable, Identifiable {
    case touchpad = "Touchpad"
    case gamepad = "Gamepad ảo"

    public var id: String { rawValue }
}

@MainActor
public final class VMSessionViewModel: ObservableObject {
    public let profile: VMProfile
    public let store: VMStore
    public let memoryMonitor: RuntimeMemoryMonitor
    public let thermalMonitor: ThermalMonitor
    public let pCoreScheduler: PCoreScheduler
    public let displayRenderer: MetalDisplayRenderer

    @Published public private(set) var vmState: VMState = .stopped
    @Published public private(set) var spiceState: SPICEConnectionState = .disconnected
    @Published public private(set) var jitStatus: JITStatus
    @Published public private(set) var connectedPhysicalControllerName: String?
    @Published public private(set) var statusBanner: String?

    // Input HUD Toggles
    @Published public var inputMode: InputHUDMode
    @Published public var showShortcutToolbar: Bool = true
    @Published public var showTelemetryOverlay: Bool = true
    @Published public var isEditingGamepadLayout: Bool = false
    @Published public var isSystemKeyboardVisible: Bool = false
    @Published public var gamepadOpacity: Double = 0.65

    // Active modifier states on floating PC shortcut bar
    @Published public var ctrlHeld: Bool = false
    @Published public var altHeld: Bool = false
    @Published public var winHeld: Bool = false

    private var vmController: VMController?
    private var controllerObserver: NSObjectProtocol?
    private var cancellables = Set<AnyCancellable>()

    public init(
        profile: VMProfile,
        store: VMStore,
        memoryMonitor: RuntimeMemoryMonitor,
        pCoreScheduler: PCoreScheduler
    ) {
        self.profile = profile
        self.store = store
        self.memoryMonitor = memoryMonitor
        self.pCoreScheduler = pCoreScheduler
        self.thermalMonitor = ThermalMonitor(scheduler: pCoreScheduler)
        self.displayRenderer = MetalDisplayRenderer(
            initialViewport: DisplayViewport(
                width: 1920,
                height: 1080,
                scaleFactor: 2.0,
                refreshRateHz: profile.refreshRateHz
            )
        )
        self.jitStatus = JITDetector.detectJIT()
        self.inputMode = (profile.useCase == .gaming) ? .gamepad : .touchpad

        memoryMonitor.objectWillChange
            .sink { [weak self] _ in self?.objectWillChange.send() }
            .store(in: &cancellables)

        thermalMonitor.objectWillChange
            .sink { [weak self] _ in self?.objectWillChange.send() }
            .store(in: &cancellables)

        observePhysicalControllers()
    }

    deinit {
        if let obs = controllerObserver {
            NotificationCenter.default.removeObserver(obs)
        }
    }

    public func startSession() {
        _ = pCoreScheduler.setThreadInteractiveQoS()
        memoryMonitor.refreshSnapshot()
        jitStatus = JITDetector.detectJIT()

        let socketDir = FileManager.default.temporaryDirectory.path
        let qemuConfig = profile.makeQEMUConfiguration(
            safeRAMMB: memoryMonitor.safeGuestCeilingMB,
            physicalPCores: pCoreScheduler.getPhysicalPCoreCount(),
            socketBaseDir: socketDir
        )

        let controller = VMController(configuration: qemuConfig)
        controller.delegate = self
        self.vmController = controller

        if let spice = controller.spiceConnection {
            spice.delegate = self
        }

        // Start live Smart Memory Guard monitoring + Darwin Memory Pressure hook
        memoryMonitor.startMonitoring(autoPauseOnDanger: profile.autoPauseOnJetsamDanger) { [weak controller] command in
            controller?.dispatchMemoryCommand(command)
        }

        // Engage Dynamic Core Boot Boost
        thermalMonitor.beginBootBoost(enabled: profile.dynamicCoreBoostEnabled)

        controller.start()
        if let spice = controller.spiceConnection {
            spice.delegate = self
        }
    }

    public func pauseSession() {
        vmController?.pause()
    }

    public func resumeSession() {
        vmController?.resume()
    }

    public func stopSession(force: Bool = false) {
        memoryMonitor.stopMonitoring()
        thermalMonitor.stopSession()
        vmController?.stop(force: force)
    }

    // MARK: - 2-Way Clipboard & File Sharing

    public func pushHostClipboardToGuest() {
        #if canImport(UIKit)
        if let text = UIPasteboard.general.string, !text.isEmpty {
            store.storageBridge.syncClipboard(text: text)
            showBanner("Đã đồng bộ Clipboard sang Windows (\(text.count) ký tự).")
        } else {
            showBanner("Clipboard iPhone đang trống.")
        }
        #endif
    }

    public func pullGuestClipboardToHost() {
        let text = store.storageBridge.getClipboardText()
        #if canImport(UIKit)
        if !text.isEmpty {
            UIPasteboard.general.string = text
            showBanner("Đã chép Clipboard từ máy ảo sang iPhone.")
        } else {
            showBanner("Clipboard máy ảo chưa có nội dung.")
        }
        #endif
    }

    public func shareFileToGuestDesktop(url: URL) {
        let accessing = url.startAccessingSecurityScopedResource()
        defer { if accessing { url.stopAccessingSecurityScopedResource() } }
        do {
            _ = try store.storageBridge.shareFileToGuest(filePath: url.path)
            showBanner("Đã gửi '\(url.lastPathComponent)' vào Desktop máy ảo!")
        } catch {
            showBanner("Lỗi gửi tệp: \(error.localizedDescription)")
        }
    }

    // MARK: - Input Event Forwarding (Touchpad, PC Shortcuts, Virtual Gamepad)

    public func sendMouseMove(dx: Int16, dy: Int16) {
        var packet = Data([0x01]) // Mouse relative move opcode
        withUnsafeBytes(of: dx.littleEndian) { packet.append(contentsOf: $0) }
        withUnsafeBytes(of: dy.littleEndian) { packet.append(contentsOf: $0) }
        _ = vmController?.spiceConnection?.sendInputEvent(data: packet)
    }

    public func sendMouseButton(button: UInt8, isDown: Bool) {
        let packet = Data([0x02, button, isDown ? 1 : 0])
        _ = vmController?.spiceConnection?.sendInputEvent(data: packet)
    }

    public func sendMouseScroll(deltaY: Int16) {
        var packet = Data([0x03])
        withUnsafeBytes(of: deltaY.littleEndian) { packet.append(contentsOf: $0) }
        _ = vmController?.spiceConnection?.sendInputEvent(data: packet)
    }

    public func sendKeyScancode(_ scancode: UInt16, isDown: Bool) {
        var packet = Data([0x04, isDown ? 1 : 0])
        withUnsafeBytes(of: scancode.littleEndian) { packet.append(contentsOf: $0) }
        _ = vmController?.spiceConnection?.sendInputEvent(data: packet)
    }

    public func tapPCShortcut(scancodes: [UInt16]) {
        for code in scancodes { sendKeyScancode(code, isDown: true) }
        for code in scancodes.reversed() { sendKeyScancode(code, isDown: false) }
    }

    public func sendGamepadButton(id: UInt8, isPressed: Bool) {
        let packet = Data([0x05, id, isPressed ? 1 : 0])
        _ = vmController?.spiceConnection?.sendInputEvent(data: packet)
    }

    public func sendGamepadStick(stickId: UInt8, x: Float, y: Float) {
        let clampedX = Int16(max(-1.0, min(1.0, x)) * 32767.0)
        let clampedY = Int16(max(-1.0, min(1.0, y)) * 32767.0)
        var packet = Data([0x06, stickId])
        withUnsafeBytes(of: clampedX.littleEndian) { packet.append(contentsOf: $0) }
        withUnsafeBytes(of: clampedY.littleEndian) { packet.append(contentsOf: $0) }
        _ = vmController?.spiceConnection?.sendInputEvent(data: packet)
    }

    public func showBanner(_ message: String) {
        statusBanner = message
        Task {
            try? await Task.sleep(nanoseconds: 2_800_000_000)
            if self.statusBanner == message {
                self.statusBanner = nil
            }
        }
    }

    private func observePhysicalControllers() {
        #if canImport(GameController)
        if let first = GCController.controllers().first {
            connectedPhysicalControllerName = first.vendorName ?? "Tay cầm Bluetooth"
        }
        controllerObserver = NotificationCenter.default.addObserver(
            forName: .GCControllerDidConnect,
            object: nil,
            queue: .main
        ) { [weak self] notification in
            guard let controller = notification.object as? GCController else { return }
            Task { @MainActor in
                self?.connectedPhysicalControllerName = controller.vendorName ?? "Tay cầm Bluetooth"
                self?.showBanner("Đã kết nối tay cầm: \(controller.vendorName ?? "Controller")")
            }
        }
        #endif
    }
}

extension VMSessionViewModel: VMControllerDelegate {
    nonisolated public func vmController(_ controller: VMController, didChangeState state: VMState) {
        Task { @MainActor in
            self.vmState = state
        }
    }

    nonisolated public func vmController(_ controller: VMController, didReceiveError error: Error) {
        Task { @MainActor in
            self.showBanner("Engine: \(error.localizedDescription)")
        }
    }
}

extension VMSessionViewModel: SPICEConnectionDelegate {
    nonisolated public func spiceConnection(_ connection: SPICEConnection, didChangeState state: SPICEConnectionState) {
        Task { @MainActor in
            self.spiceState = state
        }
    }

    nonisolated public func spiceConnection(_ connection: SPICEConnection, didReceiveDisplayFrame data: Data, width: Int, height: Int) {
        displayRenderer.updateFramebuffer(with: data, width: width, height: height, stride: width * 4)
    }

    nonisolated public func spiceConnection(_ connection: SPICEConnection, didEncounterError error: Error) {
        Task { @MainActor in
            self.showBanner("SPICE: \(error.localizedDescription)")
        }
    }
}
