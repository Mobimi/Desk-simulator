//
//  VMDisplaySessionView.swift
//  UI/Views
//
//  Integrated fullscreen VM session host coordinating MetalDisplayView at up to 120Hz ProMotion,
//  dynamic Input HUD overlays (Haptic Touchpad / Virtual Gamepad), floating PC shortcut toolbar,
//  live telemetry overlay, and VM lifecycle controls.
//

import Foundation

#if canImport(SwiftUI)
import SwiftUI
#endif

#if canImport(UIKit)
import UIKit
#endif

#if canImport(SwiftUI)

public struct VMDisplaySessionView: View {
    @ObservedObject public var viewModel: VMSessionViewModel
    @Environment(\.dismiss) private var dismiss

    @State private var showShutdownConfirmation: Bool = false
    @State private var isHeaderCollapsed: Bool = false
    @State private var isShowingDocumentPicker: Bool = false

    public init(viewModel: VMSessionViewModel) {
        self.viewModel = viewModel
    }

    public var body: some View {
        ZStack {
            // Layer 0: Pure Black Letterboxed Background
            Color.black.ignoresSafeArea()

            // Layer 1: Metal Display View (Fitted with Aspect Ratio)
            displayLayer

            // Layer 2: Active Input HUD Layer
            inputHUDLayer

            // Layer 3: Floating PC Shortcut Toolbar (Bottom)
            if viewModel.showShortcutToolbar {
                VStack {
                    Spacer()
                    PCShortcutToolbar(viewModel: viewModel)
                        .padding(.bottom, 20)
                }
            }

            // Layer 4: Top Floating Control Header & Telemetry
            VStack(spacing: 6) {
                if !isHeaderCollapsed {
                    topControlHeader
                    if viewModel.showTelemetryOverlay {
                        telemetryPill
                    }
                } else {
                    collapsedHeaderTab
                }
                Spacer()
            }
            .padding(.top, 8)
            .padding(.horizontal, 12)

            // Layer 5: Transient Status Banner Alert
            if let banner = viewModel.statusBanner {
                VStack {
                    Spacer().frame(height: 56)
                    statusBannerView(banner)
                    Spacer()
                }
                .transition(.move(edge: .top).combined(with: .opacity))
            }

            // Layer 6: Hidden System Keyboard Input Receiver
            if viewModel.isSystemKeyboardVisible {
                hiddenKeyboardReceiver
            }
        }
        .onAppear {
            viewModel.startSession()
        }
        .onDisappear {
            viewModel.stopSession()
        }
        .confirmationDialog(
            "Bạn có chắc muốn dừng máy ảo?",
            isPresented: $showShutdownConfirmation,
            titleVisibility: .visible
        ) {
            Button("Tắt nguồn máy ảo (Shutdown)", role: .destructive) {
                viewModel.stopSession(force: false)
                dismiss()
            }
            Button("Buộc dừng ngay lập tức (Force Kill)", role: .destructive) {
                viewModel.stopSession(force: true)
                dismiss()
            }
            Button("Hủy", role: .cancel) {}
        }
        .sheet(isPresented: $isShowingDocumentPicker) {
            DocumentPickerSheet { url in
                viewModel.shareFileToGuestDesktop(url: url)
            }
        }
    }

    // MARK: - Display Layer

    private var displayLayer: some View {
        MetalDisplayView(renderer: viewModel.displayRenderer)
            .aspectRatio(
                CGSize(
                    width: max(1, viewModel.displayRenderer.viewport.width),
                    height: max(1, viewModel.displayRenderer.viewport.height)
                ),
                contentMode: .fit
            )
            .ignoresSafeArea()
    }

    // MARK: - Input HUD Layer

    @ViewBuilder
    private var inputHUDLayer: some View {
        switch viewModel.inputMode {
        case .touchpad:
            HapticTouchpadOverlay(viewModel: viewModel)
        case .gamepad:
            VirtualGamepadOverlay(viewModel: viewModel)
        }
    }

    // MARK: - Top Floating Control Header

    private var topControlHeader: some View {
        HStack(spacing: 10) {
            // Close / Power Button
            Button(action: {
                showShutdownConfirmation = true
            }) {
                Image(systemName: "xmark.circle.fill")
                    .font(.system(size: 20))
                    .foregroundColor(.red.opacity(0.9))
            }

            // VM State & Pause/Resume
            Button(action: {
                if viewModel.vmState == .running {
                    viewModel.pauseSession()
                } else if viewModel.vmState == .paused {
                    viewModel.resumeSession()
                }
            }) {
                HStack(spacing: 5) {
                    Image(systemName: viewModel.vmState == .running ? "pause.fill" : "play.fill")
                        .font(.system(size: 11, weight: .bold))
                    Text(viewModel.vmState == .running ? "Tạm dừng" : "Tiếp tục")
                        .font(.system(size: 11, weight: .semibold))
                }
                .foregroundColor(.white)
                .padding(.horizontal, 8)
                .frame(height: 28)
                .background(
                    Capsule().fill(Color.white.opacity(0.18))
                )
            }

            Spacer()

            // Input Mode Switcher (Touchpad vs Gamepad)
            Picker("Input Mode", selection: $viewModel.inputMode) {
                ForEach(InputHUDMode.allCases) { mode in
                    Text(mode.rawValue).tag(mode)
                }
            }
            .pickerStyle(.segmented)
            .frame(width: 170)

            // Shortcut Bar Toggle
            Button(action: {
                viewModel.showShortcutToolbar.toggle()
            }) {
                Image(systemName: "keyboard")
                    .font(.system(size: 13))
                    .foregroundColor(viewModel.showShortcutToolbar ? .cyan : .white.opacity(0.6))
                    .frame(width: 28, height: 28)
                    .background(Circle().fill(Color.white.opacity(0.14)))
            }

            // Telemetry Overlay Toggle
            Button(action: {
                viewModel.showTelemetryOverlay.toggle()
            }) {
                Image(systemName: "speedometer")
                    .font(.system(size: 13))
                    .foregroundColor(viewModel.showTelemetryOverlay ? .green : .white.opacity(0.6))
                    .frame(width: 28, height: 28)
                    .background(Circle().fill(Color.white.opacity(0.14)))
            }

            // Clipboard Host -> Guest
            Menu {
                Button("Gửi Clipboard từ iPhone -> Windows") {
                    viewModel.pushHostClipboardToGuest()
                }
                Button("Lấy Clipboard từ Windows -> iPhone") {
                    viewModel.pullGuestClipboardToHost()
                }
                Button("Gửi tệp vào Desktop máy ảo...") {
                    isShowingDocumentPicker = true
                }
            } label: {
                Image(systemName: "doc.on.clipboard")
                    .font(.system(size: 13))
                    .foregroundColor(.white.opacity(0.85))
                    .frame(width: 28, height: 28)
                    .background(Circle().fill(Color.white.opacity(0.14)))
            }

            // Collapse Header Button
            Button(action: {
                withAnimation { isHeaderCollapsed = true }
            }) {
                Image(systemName: "chevron.up")
                    .font(.system(size: 12, weight: .bold))
                    .foregroundColor(.white.opacity(0.6))
                    .frame(width: 24, height: 28)
            }
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 6)
        .background(
            RoundedRectangle(cornerRadius: 14)
                .fill(Color.black.opacity(0.65))
        )
        .overlay(
            RoundedRectangle(cornerRadius: 14)
                .stroke(Color.white.opacity(0.18), lineWidth: 1)
        )
    }

    // MARK: - Collapsed Header Tab

    private var collapsedHeaderTab: some View {
        Button(action: {
            withAnimation { isHeaderCollapsed = false }
        }) {
            HStack(spacing: 6) {
                Image(systemName: "chevron.down")
                    .font(.system(size: 10, weight: .bold))
                Text(viewModel.profile.name)
                    .font(.system(size: 11, weight: .semibold))
            }
            .foregroundColor(.white.opacity(0.8))
            .padding(.horizontal, 12)
            .padding(.vertical, 4)
            .background(Capsule().fill(Color.black.opacity(0.65)))
            .overlay(Capsule().stroke(Color.white.opacity(0.2), lineWidth: 1))
        }
    }

    // MARK: - Live Telemetry HUD Pill

    private var telemetryPill: some View {
        HStack(spacing: 12) {
            // Memory Gauge
            HStack(spacing: 4) {
                Circle()
                    .fill(telemetryDangerColor)
                    .frame(width: 7, height: 7)
                Text("RAM: \(viewModel.memoryMonitor.currentUsageMB)MB / \(viewModel.memoryMonitor.safeGuestCeilingMB)MB")
                    .font(.system(size: 10, weight: .medium, design: .monospaced))
                    .foregroundColor(.white.opacity(0.9))
            }

            // JIT Status
            HStack(spacing: 4) {
                Text("JIT:")
                    .font(.system(size: 10, weight: .semibold))
                    .foregroundColor(.white.opacity(0.6))
                Text(viewModel.jitStatus.isAvailable ? "BẬT" : "TẮT")
                    .font(.system(size: 10, weight: .bold))
                    .foregroundColor(viewModel.jitStatus.isAvailable ? .green : .orange)
            }

            // Thermal Alert Level
            HStack(spacing: 4) {
                Text("Nhiệt:")
                    .font(.system(size: 10, weight: .semibold))
                    .foregroundColor(.white.opacity(0.6))
                Text(thermalLevelString)
                    .font(.system(size: 10, weight: .bold))
                    .foregroundColor(thermalColor)
            }

            // Refresh Rate (ProMotion)
            Text("\(viewModel.displayRenderer.viewport.refreshRateHz)Hz")
                .font(.system(size: 10, weight: .bold, design: .monospaced))
                .foregroundColor(.cyan)
        }
        .padding(.horizontal, 10)
        .padding(.vertical, 4)
        .background(Capsule().fill(Color.black.opacity(0.6)))
        .overlay(Capsule().stroke(Color.white.opacity(0.15), lineWidth: 1))
    }

    private var telemetryDangerColor: Color {
        switch viewModel.memoryMonitor.dangerZone {
        case .safe:    return .green
        case .caution: return .yellow
        case .danger:  return .red
        }
    }

    private var thermalLevelString: String {
        switch viewModel.thermalMonitor.thermalLevel {
        case .nominal:  return "Mát"
        case .fair:     return "Ấm"
        case .serious:  return "Nóng"
        case .critical: return "Quá nhiệt"
        }
    }

    private var thermalColor: Color {
        switch viewModel.thermalMonitor.thermalLevel {
        case .nominal:  return .green
        case .fair:     return .yellow
        case .serious:  return .orange
        case .critical: return .red
        }
    }

    // MARK: - Status Banner

    private func statusBannerView(_ text: String) -> some View {
        Text(text)
            .font(.system(size: 12, weight: .medium))
            .foregroundColor(.white)
            .padding(.horizontal, 14)
            .padding(.vertical, 7)
            .background(Capsule().fill(Color.black.opacity(0.85)))
            .overlay(Capsule().stroke(Color.white.opacity(0.25), lineWidth: 1))
            .shadow(radius: 6)
    }

    // MARK: - Hidden Keyboard Input Receiver

    private var hiddenKeyboardReceiver: some View {
        HiddenKeystrokeForwarder { character in
            forwardCharacter(character)
        }
        .frame(width: 1, height: 1)
        .opacity(0.01)
    }

    private func forwardCharacter(_ char: Character) {
        // Map common ASCII keys to Scancode Set 1
        let scancode: UInt16?
        switch char {
        case "\n", "\r": scancode = 0x001C // Enter
        case "\t": scancode = 0x000F // Tab
        case " ": scancode = 0x0039 // Space
        case "a", "A": scancode = 0x001E
        case "b", "B": scancode = 0x0030
        case "c", "C": scancode = 0x002E
        case "d", "D": scancode = 0x0020
        case "e", "E": scancode = 0x0012
        case "f", "F": scancode = 0x0021
        case "g", "G": scancode = 0x0022
        case "h", "H": scancode = 0x0023
        case "i", "I": scancode = 0x0017
        case "j", "J": scancode = 0x0024
        case "k", "K": scancode = 0x0025
        case "l", "L": scancode = 0x0026
        case "m", "M": scancode = 0x0032
        case "n", "N": scancode = 0x0031
        case "o", "O": scancode = 0x0018
        case "p", "P": scancode = 0x0019
        case "q", "Q": scancode = 0x0010
        case "r", "R": scancode = 0x0013
        case "s", "S": scancode = 0x001F
        case "t", "T": scancode = 0x0014
        case "u", "U": scancode = 0x0016
        case "v", "V": scancode = 0x002F
        case "w", "W": scancode = 0x0011
        case "x", "X": scancode = 0x002D
        case "y", "Y": scancode = 0x0015
        case "z", "Z": scancode = 0x002C
        case "1": scancode = 0x0002
        case "2": scancode = 0x0003
        case "3": scancode = 0x0004
        case "4": scancode = 0x0005
        case "5": scancode = 0x0006
        case "6": scancode = 0x0007
        case "7": scancode = 0x0008
        case "8": scancode = 0x0009
        case "9": scancode = 0x000A
        case "0": scancode = 0x000B
        default: scancode = nil
        }

        if let code = scancode {
            viewModel.tapPCShortcut(scancodes: [code])
        }
    }
}

// MARK: - Hidden Keystroke Forwarder

#if canImport(UIKit)
internal struct HiddenKeystrokeForwarder: UIViewRepresentable {
    let onKeystroke: (Character) -> Void

    func makeCoordinator() -> Coordinator {
        Coordinator(onKeystroke: onKeystroke)
    }

    func makeUIView(context: Context) -> UITextField {
        let field = UITextField(frame: .zero)
        field.delegate = context.coordinator
        field.autocorrectionType = .no
        field.autocapitalizationType = .none
        field.spellCheckingType = .no
        DispatchQueue.main.async {
            field.becomeFirstResponder()
        }
        return field
    }

    func updateUIView(_ uiView: UITextField, context: Context) {}

    class Coordinator: NSObject, UITextFieldDelegate {
        let onKeystroke: (Character) -> Void

        init(onKeystroke: @escaping (Character) -> Void) {
            self.onKeystroke = onKeystroke
        }

        func textField(_ textField: UITextField, shouldChangeCharactersIn range: NSRange, replacementString string: String) -> Bool {
            for char in string {
                onKeystroke(char)
            }
            return false
        }
    }
}
#else
internal struct HiddenKeystrokeForwarder: View {
    let onKeystroke: (Character) -> Void
    var body: some View { EmptyView() }
}
#endif

// MARK: - Document Picker Sheet

#if canImport(UIKit)
internal struct DocumentPickerSheet: UIViewControllerRepresentable {
    let onPick: (URL) -> Void

    func makeUIViewController(context: Context) -> UIDocumentPickerViewController {
        let picker = UIDocumentPickerViewController(forOpeningContentTypes: [.item], asCopy: true)
        picker.delegate = context.coordinator
        return picker
    }

    func updateUIViewController(_ uiViewController: UIDocumentPickerViewController, context: Context) {}

    func makeCoordinator() -> Coordinator {
        Coordinator(onPick: onPick)
    }

    class Coordinator: NSObject, UIDocumentPickerDelegate {
        let onPick: (URL) -> Void

        init(onPick: @escaping (URL) -> Void) {
            self.onPick = onPick
        }

        func documentPicker(_ controller: UIDocumentPickerViewController, didPickDocumentsAt urls: [URL]) {
            if let first = urls.first {
                onPick(first)
            }
        }
    }
}
#else
internal struct DocumentPickerSheet: View {
    let onPick: (URL) -> Void
    var body: some View { EmptyView() }
}
#endif

#endif
