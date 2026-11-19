//
//  VMSettingsView.swift
//  UI/Views
//
//  Per-VM configuration screen featuring:
//  - Smart Memory Guard toggle (locks slider when ON; unlocks + Jetsam Danger Zone meter when OFF)
//  - Auto P-Core toggle (locks vCPU to P-cores when ON; unlocks + Thermal Alerts when OFF)
//  - Dynamic Core Boost toggle
//  - SPICE Unix Domain Socket, TCG buffer clamping (128-256MB), APFS Sparse & Share Sheet
//

import SwiftUI

public struct VMSettingsView: View {
    @Environment(\.dismiss) private var dismiss
    @State private var draft: VMProfile
    @ObservedObject private var memoryMonitor: RuntimeMemoryMonitor
    private let pCoreScheduler: PCoreScheduler
    private let onSave: (VMProfile) -> Void

    public init(
        profile: VMProfile,
        memoryMonitor: RuntimeMemoryMonitor,
        pCoreScheduler: PCoreScheduler,
        onSave: @escaping (VMProfile) -> Void
    ) {
        _draft = State(initialValue: profile)
        self.memoryMonitor = memoryMonitor
        self.pCoreScheduler = pCoreScheduler
        self.onSave = onSave
    }

    public var body: some View {
        NavigationView {
            Form {
                Section("Thông tin chung") {
                    TextField("Tên máy ảo", text: $draft.name)
                    Picker("Kiến trúc CPU", selection: $draft.architecture) {
                        ForEach(TargetArchitecture.allCases, id: \.self) { arch in
                            Text(arch.displayName).tag(arch)
                        }
                    }
                }

                // MARK: - Smart Memory Guard (Hybrid Mode)
                Section {
                    Toggle("Smart Memory Guard (Tự động chống văng)", isOn: $draft.isSmartMemoryEnabled)

                    if draft.isSmartMemoryEnabled {
                        HStack {
                            Label("RAM cấp tự động (Đã khóa an toàn)", systemImage: "lock.shield.fill")
                                .foregroundColor(.green)
                            Spacer()
                            Text("\(memoryMonitor.safeGuestCeilingMB) MB")
                                .font(.body.monospacedDigit().weight(.bold))
                                .foregroundColor(.cyan)
                        }
                        Text("Đang bảo lưu cứng 450MB cho iOS & kích hoạt VirtIO-Balloon xả RAM khi có Memory Pressure.")
                            .font(.caption)
                            .foregroundColor(.secondary)
                    } else {
                        let zone = memoryMonitor.evaluateManualSelection(ramMB: draft.manualRAMMB)
                        VStack(alignment: .leading, spacing: 8) {
                            HStack {
                                Text("RAM Thủ Công:")
                                Spacer()
                                Text("\(draft.manualRAMMB) MB")
                                    .font(.body.monospacedDigit().weight(.bold))
                                    .foregroundColor(colorForZone(zone))
                            }
                            Slider(
                                value: Binding(
                                    get: { Double(draft.manualRAMMB) },
                                    set: { draft.manualRAMMB = Int($0) }
                                ),
                                in: 512...Double(memoryMonitor.maxSelectableRAMMB),
                                step: 128
                            )
                            .tint(colorForZone(zone))

                            HStack {
                                Circle().fill(colorForZone(zone)).frame(width: 8, height: 8)
                                Text("Vùng Jetsam: \(zone.rawValue)")
                                    .font(.caption.weight(.bold))
                                    .foregroundColor(colorForZone(zone))
                            }
                            Text(zone.descriptionText)
                                .font(.caption2)
                                .foregroundColor(.secondary)
                        }

                        Toggle("Tự động Pause máy ảo khi chạm 90% Jetsam", isOn: $draft.autoPauseOnJetsamDanger)
                    }

                    HStack {
                        Text("Entitlements hoạt động")
                            .font(.caption)
                            .foregroundColor(.secondary)
                        Spacer()
                        Text(entitlementSummary)
                            .font(.caption.weight(.semibold))
                            .foregroundColor(memoryMonitor.entitlements.increasedMemoryLimit ? .green : .orange)
                    }
                } header: {
                    Text("Quản lý RAM & Chống văng Jetsam")
                }

                // MARK: - P-Core Scheduler & Dynamic Core Boost
                Section {
                    Toggle("Tự động gán theo nhân mạnh (Auto P-Core)", isOn: $draft.isAutoPCoreEnabled)

                    if draft.isAutoPCoreEnabled {
                        HStack {
                            Label("vCPU ghim vào P-Core + Mach QoS Interactive", systemImage: "cpu.fill")
                                .font(.caption)
                                .foregroundColor(.cyan)
                            Spacer()
                            Text("\(pCoreScheduler.getPhysicalPCoreCount()) vCPUs")
                                .font(.body.monospacedDigit().weight(.bold))
                        }
                    } else {
                        Stepper("Số nhân vCPU thủ công: \(draft.manualVCPUs)", value: $draft.manualVCPUs, in: 1...8)
                        Toggle("Cảnh báo quá nhiệt (Thermal Throttling)", isOn: $draft.thermalAlertsEnabled)
                    }

                    Toggle("Dynamic Core Boost (Tăng tốc lúc Boot)", isOn: $draft.dynamicCoreBoostEnabled)
                } header: {
                    Text("CPU, P-Core & Nhiệt độ")
                }

                // MARK: - Graphics & TCG Clamping
                Section {
                    Picker("Tần số quét Metal ProMotion", selection: $draft.refreshRateHz) {
                        Text("60 Hz (Tiết kiệm pin)").tag(60)
                        Text("120 Hz (ProMotion Siêu Mượt)").tag(120)
                    }

                    Stepper("TCG Buffer (-tb-size): \(draft.tbSizeMB) MB", value: $draft.tbSizeMB, in: 128...256, step: 32)

                    HStack {
                        Text("SPICE IPC Transport")
                        Spacer()
                        Text("Unix Domain Socket")
                            .font(.caption.weight(.bold))
                            .foregroundColor(.green)
                    }
                } header: {
                    Text("Đồ họa Metal & Lõi QEMU")
                }

                // MARK: - Storage & File Sharing
                Section {
                    Toggle("Đồng bộ Clipboard 2 chiều", isOn: $draft.clipboardSyncEnabled)
                    Toggle("Thư mục chia sẻ iOS Share Sheet", isOn: $draft.sharedFolderEnabled)
                    Toggle("Nhúng driver VirtIO ngầm", isOn: $draft.virtIOInjectionEnabled)
                    Toggle("Bypass TPM 2.0 / MS Account (Win 11)", isOn: $draft.win11BypassEnabled)
                } header: {
                    Text("Lưu trữ APFS Sparse & Tiện ích")
                }
            }
            .navigationTitle("Cấu Hình Máy Ảo")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Hủy") { dismiss() }
                }
                ToolbarItem(placement: .confirmationAction) {
                    Button("Lưu") {
                        onSave(draft)
                        dismiss()
                    }
                    .font(.headline)
                }
            }
        }
        .navigationViewStyle(.stack)
    }

    private func colorForZone(_ zone: JetsamDangerZone) -> Color {
        switch zone {
        case .safe: return .green
        case .caution: return .yellow
        case .danger: return .red
        }
    }

    private var entitlementSummary: String {
        if memoryMonitor.entitlements.increasedMemoryLimit && memoryMonitor.entitlements.extendedVirtualAddressing {
            return "Full (Increased RAM + Extended VA)"
        } else if memoryMonitor.entitlements.increasedMemoryLimit {
            return "Increased RAM (75%)"
        } else {
            return "Sideload chuẩn (50% - Không bắt buộc)"
        }
    }
}
