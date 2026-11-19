//
//  SmartSetupWizardView.swift
//  UI/Views
//
//  Tri-Mode Setup Wizard:
//  1. 1-Click Template Catalog
//  2. Smart ISO Auto-Pilot (auto-detects OS, injects VirtIO & bypasses Win11 TPM 2.0)
//  3. Needs-Based Wizard (no technical jargon!)
//

import SwiftUI
import UniformTypeIdentifiers

public struct SmartSetupWizardView: View {
    @Environment(\.dismiss) private var dismiss
    @StateObject private var wizardVM: SetupWizardViewModel
    @ObservedObject private var memoryMonitor: RuntimeMemoryMonitor
    private let store: VMStore
    private let onCreated: (VMProfile) -> Void

    @State private var isShowingISOImporter: Bool = false

    public init(
        store: VMStore,
        memoryMonitor: RuntimeMemoryMonitor,
        initialISOURL: URL? = nil,
        onCreated: @escaping (VMProfile) -> Void
    ) {
        self.store = store
        self.memoryMonitor = memoryMonitor
        self.onCreated = onCreated
        _wizardVM = StateObject(wrappedValue: SetupWizardViewModel(isoAutoPilot: store.isoAutoPilot, initialISOURL: initialISOURL))
    }

    public var body: some View {
        NavigationView {
            VStack(spacing: 16) {
                Picker("Chế độ tạo máy ảo", selection: $wizardVM.mode) {
                    ForEach(SetupWizardMode.allCases) { mode in
                        Text(mode.rawValue).tag(mode)
                    }
                }
                .pickerStyle(.segmented)
                .padding(.horizontal, 16)

                ScrollView {
                    VStack(spacing: 16) {
                        switch wizardVM.mode {
                        case .templates:
                            templatesModeView
                        case .isoAutoPilot:
                            isoAutoPilotView
                        case .needsWizard:
                            needsBasedView
                        }
                    }
                    .padding(.horizontal, 16)
                    .padding(.bottom, 30)
                }
            }
            .background(Color(red: 0.06, green: 0.07, blue: 0.10).ignoresSafeArea())
            .navigationTitle("Tạo Máy Ảo Thông Minh")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Đóng") { dismiss() }
                }
            }
            .fileImporter(
                isPresented: $isShowingISOImporter,
                allowedContentTypes: [.data],
                allowsMultipleSelection: false
            ) { result in
                if case .success(let urls) = result, let url = urls.first {
                    wizardVM.inspectISO(at: url)
                }
            }
        }
        .navigationViewStyle(.stack)
    }

    // MARK: - Mode 1: 1-Click Template Catalog

    private var templatesModeView: some View {
        VStack(spacing: 12) {
            ForEach(VMTemplate.catalog) { template in
                VStack(alignment: .leading, spacing: 10) {
                    HStack {
                        Image(systemName: template.iconName)
                            .foregroundColor(.cyan)
                            .font(.title3)
                        VStack(alignment: .leading, spacing: 2) {
                            Text(template.title)
                                .font(.subheadline.weight(.bold))
                                .foregroundColor(.white)
                            Text("\(template.architecture.displayName) • \(template.estimatedDownloadSize)")
                                .font(.caption2)
                                .foregroundColor(.secondary)
                        }
                        Spacer()
                        Button("Cài ngay") {
                            let created = store.createVM(from: template)
                            onCreated(created)
                            dismiss()
                        }
                        .font(.caption.weight(.bold))
                        .foregroundColor(.white)
                        .padding(.horizontal, 14)
                        .padding(.vertical, 8)
                        .background(Color.blue, in: Capsule())
                    }

                    Text(template.summary)
                        .font(.caption)
                        .foregroundColor(.gray)
                }
                .padding(14)
                .background(RoundedRectangle(cornerRadius: 16).fill(Color.white.opacity(0.06)))
            }
        }
    }

    // MARK: - Mode 2: Smart ISO Auto-Pilot

    private var isoAutoPilotView: some View {
        VStack(alignment: .leading, spacing: 16) {
            Button {
                isShowingISOImporter = true
            } label: {
                HStack(spacing: 12) {
                    Image(systemName: "opticaldisc.fill")
                        .font(.title2)
                        .foregroundColor(.cyan)
                    VStack(alignment: .leading, spacing: 2) {
                        Text(wizardVM.selectedISOURL?.lastPathComponent ?? "Chọn file ISO Windows / Linux")
                            .font(.subheadline.weight(.semibold))
                            .foregroundColor(.white)
                            .lineLimit(1)
                        Text("Tự nhận diện phiên bản, nhúng VirtIO & Bypass TPM 2.0")
                            .font(.caption2)
                            .foregroundColor(.secondary)
                    }
                    Spacer()
                    Image(systemName: "folder.badge.plus")
                        .foregroundColor(.blue)
                }
                .padding(16)
                .background(RoundedRectangle(cornerRadius: 16).fill(Color.white.opacity(0.08)))
            }

            if wizardVM.selectedISOURL != nil {
                VStack(alignment: .leading, spacing: 10) {
                    Label("Kết quả phân tích ISO Auto-Pilot", systemImage: "wand.and.stars")
                        .font(.subheadline.weight(.bold))
                        .foregroundColor(.cyan)

                    HStack {
                        Text("Hệ điều hành:")
                            .foregroundColor(.secondary)
                        Spacer()
                        Text(wizardVM.detectedOS.rawValue)
                            .font(.caption.weight(.bold))
                            .foregroundColor(.white)
                    }
                    HStack {
                        Text("Kiến trúc CPU:")
                            .foregroundColor(.secondary)
                        Spacer()
                        Picker("Kiến trúc", selection: $wizardVM.detectedArchitecture) {
                            ForEach(TargetArchitecture.allCases, id: \.self) { arch in
                                Text(arch.rawValue.uppercased()).tag(arch)
                            }
                        }
                        .pickerStyle(.segmented)
                        .frame(width: 170)
                    }

                    Text(wizardVM.virtIOConfigSummary)
                        .font(.caption)
                        .foregroundColor(.green)
                        .padding(10)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .background(Color.green.opacity(0.12), in: RoundedRectangle(cornerRadius: 10))

                    Toggle("Tự động Bypass TPM 2.0, RAM & MS Account", isOn: $wizardVM.autoBypassWin11)
                        .font(.caption)
                }
                .padding(14)
                .background(RoundedRectangle(cornerRadius: 16).fill(Color.white.opacity(0.06)))
            }

            commonDiskAndNameFields
            createButton(title: "Bắt đầu với Smart ISO Auto-Pilot")
        }
    }

    // MARK: - Mode 3: Needs-Based Wizard

    private var needsBasedView: some View {
        VStack(alignment: .leading, spacing: 16) {
            Text("1. Bạn dùng máy ảo này để làm gì?")
                .font(.subheadline.weight(.bold))
                .foregroundColor(.white)

            ForEach(VMUseCase.allCases) { useCase in
                Button {
                    wizardVM.selectedUseCase = useCase
                } label: {
                    HStack(spacing: 12) {
                        Image(systemName: useCase.iconName)
                            .font(.title3)
                            .foregroundColor(wizardVM.selectedUseCase == useCase ? .cyan : .gray)
                            .frame(width: 30)
                        VStack(alignment: .leading, spacing: 2) {
                            Text(useCase.rawValue)
                                .font(.subheadline.weight(.semibold))
                                .foregroundColor(.white)
                            Text(useCase.subtitle)
                                .font(.caption2)
                                .foregroundColor(.secondary)
                        }
                        Spacer()
                        if wizardVM.selectedUseCase == useCase {
                            Image(systemName: "checkmark.circle.fill")
                                .foregroundColor(.cyan)
                        }
                    }
                    .padding(14)
                    .background(
                        RoundedRectangle(cornerRadius: 14)
                            .fill(wizardVM.selectedUseCase == useCase ? Color.blue.opacity(0.20) : Color.white.opacity(0.05))
                            .overlay(
                                RoundedRectangle(cornerRadius: 14)
                                    .stroke(wizardVM.selectedUseCase == useCase ? Color.cyan : Color.clear, lineWidth: 1)
                            )
                    )
                }
            }

            Text("2. Ưu tiên hiệu năng & nhiệt độ")
                .font(.subheadline.weight(.bold))
                .foregroundColor(.white)

            Picker("Hiệu năng", selection: $wizardVM.selectedPowerProfile) {
                ForEach(VMPowerProfile.allCases) { profile in
                    Text(profile.rawValue).tag(profile)
                }
            }
            .pickerStyle(.wheel)
            .frame(height: 110)

            commonDiskAndNameFields
            createButton(title: "Tạo máy ảo đã tối ưu tự động")
        }
    }

    private var commonDiskAndNameFields: some View {
        VStack(alignment: .leading, spacing: 12) {
            TextField("Tên máy ảo (ví dụ: Windows 11 của tôi)", text: $wizardVM.vmName)
                .textFieldStyle(.roundedBorder)

            Stepper("Ổ đĩa APFS Sparse: \(wizardVM.diskSizeGB) GB", value: $wizardVM.diskSizeGB, in: 8...256, step: 8)
                .font(.subheadline)
                .foregroundColor(.white)

            Toggle("Bật Smart Memory Guard (Chống văng Jetsam)", isOn: $wizardVM.useSmartMemoryGuard)
                .font(.subheadline)
                .foregroundColor(.white)

            Text("Smart Guard tự động khóa trần an toàn ở \(memoryMonitor.safeGuestCeilingMB) MB dựa trên RAM thực & Entitlement hiện tại.")
                .font(.caption2)
                .foregroundColor(.secondary)
        }
        .padding(14)
        .background(RoundedRectangle(cornerRadius: 16).fill(Color.white.opacity(0.06)))
    }

    private func createButton(title: String) -> some View {
        Button {
            let profile = wizardVM.buildProfile(using: store)
            onCreated(profile)
            dismiss()
        } label: {
            Text(title)
                .font(.headline.weight(.bold))
                .foregroundColor(.white)
                .frame(maxWidth: .infinity)
                .padding(.vertical, 14)
                .background(Color.blue, in: RoundedRectangle(cornerRadius: 16))
        }
    }
}
