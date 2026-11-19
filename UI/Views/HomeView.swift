//
//  HomeView.swift
//  UI/Views
//
//  Modern iOS dashboard displaying live JIT/Entitlements status, Smart Memory headroom,
//  user Virtual Machines, and the 1-Click Template Catalog.
//

import SwiftUI

public struct HomeView: View {
    @ObservedObject public var viewModel: HomeViewModel

    public init(viewModel: HomeViewModel) {
        self.viewModel = viewModel
    }

    public var body: some View {
        NavigationView {
            ZStack(alignment: .bottom) {
                ScrollView {
                    VStack(spacing: 20) {
                        statusHeaderCard
                        myVMsSection
                        templateCatalogSection
                    }
                    .padding(.horizontal, 16)
                    .padding(.top, 12)
                    .padding(.bottom, 80)
                }
                .background(Color(red: 0.06, green: 0.07, blue: 0.10).ignoresSafeArea())

                if let toast = viewModel.toastMessage {
                    Text(toast)
                        .font(.footnote.weight(.semibold))
                        .foregroundColor(.white)
                        .padding(.horizontal, 16)
                        .padding(.vertical, 10)
                        .background(.ultraThinMaterial, in: Capsule())
                        .overlay(Capsule().stroke(Color.blue.opacity(0.6), lineWidth: 1))
                        .padding(.bottom, 16)
                        .transition(.move(edge: .bottom).combined(with: .opacity))
                }
            }
            .navigationTitle("Desk Simulator")
            .toolbar {
                ToolbarItem(placement: .navigationBarLeading) {
                    Button {
                        viewModel.refreshDiagnostics()
                        viewModel.isPresentingJITGuide = true
                    } label: {
                        Image(systemName: viewModel.jitStatus.isAvailable ? "bolt.circle.fill" : "exclamationmark.triangle.fill")
                            .foregroundColor(viewModel.jitStatus.isAvailable ? .green : .orange)
                    }
                }
                ToolbarItem(placement: .navigationBarTrailing) {
                    Button {
                        viewModel.incomingISOURL = nil
                        viewModel.isPresentingWizard = true
                    } label: {
                        Label("Tạo mới", systemImage: "plus.circle.fill")
                            .font(.body.weight(.semibold))
                    }
                }
            }
            .sheet(isPresented: $viewModel.isPresentingWizard) {
                SmartSetupWizardView(
                    store: viewModel.store,
                    memoryMonitor: viewModel.memoryMonitor,
                    initialISOURL: viewModel.incomingISOURL
                ) { created in
                    viewModel.showToast("Sẵn sàng chạy '\(created.name)'!")
                }
            }
            .sheet(isPresented: $viewModel.isPresentingJITGuide) {
                JITGuideSheetView(
                    jitStatus: viewModel.jitStatus,
                    entitlements: viewModel.memoryMonitor.entitlements,
                    safeRAMMB: viewModel.memoryMonitor.safeGuestCeilingMB
                ) {
                    viewModel.refreshDiagnostics()
                }
            }
            .sheet(item: $viewModel.selectedProfileForSettings) { profile in
                VMSettingsView(
                    profile: profile,
                    memoryMonitor: viewModel.memoryMonitor,
                    pCoreScheduler: viewModel.pCoreScheduler
                ) { updated in
                    viewModel.store.updateProfile(updated)
                    viewModel.showToast("Đã lưu cấu hình '\(updated.name)'.")
                }
            }
            .fullScreenCover(item: $viewModel.selectedProfileForSession) { profile in
                VMDisplaySessionView(
                    viewModel: VMSessionViewModel(
                        profile: profile,
                        store: viewModel.store,
                        memoryMonitor: viewModel.memoryMonitor,
                        pCoreScheduler: viewModel.pCoreScheduler
                    )
                )
            }
        }
        .navigationViewStyle(.stack)
    }

    // MARK: - Live System Health Card (JIT + Entitlements + Smart Memory Guard)

    private var statusHeaderCard: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                HStack(spacing: 8) {
                    Circle()
                        .fill(viewModel.jitStatus.isAvailable ? Color.green : Color.orange)
                        .frame(width: 10, height: 10)
                    Text(viewModel.jitStatus.isAvailable ? "JIT Đang Bật (\(viewModel.jitStatus.source.rawValue))" : "Chưa bật JIT")
                        .font(.subheadline.weight(.bold))
                        .foregroundColor(.white)
                }
                Spacer()
                Button("Chi tiết") {
                    viewModel.refreshDiagnostics()
                    viewModel.isPresentingJITGuide = true
                }
                .font(.caption.weight(.semibold))
                .padding(.horizontal, 10)
                .padding(.vertical, 5)
                .background(Color.white.opacity(0.12), in: Capsule())
            }

            HStack(spacing: 8) {
                entitlementPill(
                    title: "Increased RAM",
                    active: viewModel.memoryMonitor.entitlements.increasedMemoryLimit
                )
                entitlementPill(
                    title: "Extended VA",
                    active: viewModel.memoryMonitor.entitlements.extendedVirtualAddressing
                )
                Spacer()
                Text("Trần an toàn: \(viewModel.memoryMonitor.safeGuestCeilingMB) MB")
                    .font(.caption.monospacedDigit().weight(.semibold))
                    .foregroundColor(.cyan)
            }

            HStack(spacing: 12) {
                Label("\(viewModel.pCoreScheduler.getPhysicalPCoreCount()) P-Cores", systemImage: "cpu.fill")
                Label("SPICE Unix Socket", systemImage: "bolt.horizontal.fill")
                Label("120Hz Metal", systemImage: "sparkles")
            }
            .font(.caption2.weight(.medium))
            .foregroundColor(.gray)
        }
        .padding(16)
        .background(
            RoundedRectangle(cornerRadius: 18)
                .fill(Color.white.opacity(0.06))
                .overlay(
                    RoundedRectangle(cornerRadius: 18)
                        .stroke(Color.white.opacity(0.10), lineWidth: 1)
                )
        )
    }

    private func entitlementPill(title: String, active: Bool) -> some View {
        HStack(spacing: 4) {
            Image(systemName: active ? "checkmark.shield.fill" : "shield.slash")
                .font(.caption2)
            Text(title)
                .font(.caption2.weight(.semibold))
        }
        .foregroundColor(active ? .green : .secondary)
        .padding(.horizontal, 8)
        .padding(.vertical, 4)
        .background((active ? Color.green : Color.gray).opacity(0.15), in: Capsule())
    }

    // MARK: - User Virtual Machines

    private var myVMsSection: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                Text("Máy ảo của bạn")
                    .font(.headline.weight(.bold))
                    .foregroundColor(.white)
                Spacer()
                Text("\(viewModel.store.profiles.count) máy")
                    .font(.caption)
                    .foregroundColor(.secondary)
            }

            if viewModel.store.profiles.isEmpty {
                VStack(spacing: 12) {
                    Image(systemName: "desktopcomputer.trianglebadge.exclamationmark")
                        .font(.system(size: 36))
                        .foregroundColor(.blue.opacity(0.8))
                    Text("Chưa có máy ảo nào")
                        .font(.subheadline.weight(.semibold))
                        .foregroundColor(.white)
                    Text("Chọn một bản Windows/Linux có sẵn bên dưới hoặc nạp file ISO của riêng bạn — tự động cài driver VirtIO 100%.")
                        .font(.caption)
                        .foregroundColor(.secondary)
                        .multilineTextAlignment(.center)
                    Button {
                        viewModel.isPresentingWizard = true
                    } label: {
                        Text("Tạo máy ảo đầu tiên")
                            .font(.subheadline.weight(.semibold))
                            .foregroundColor(.white)
                            .padding(.horizontal, 20)
                            .padding(.vertical, 10)
                            .background(Color.blue, in: Capsule())
                    }
                }
                .frame(maxWidth: .infinity)
                .padding(24)
                .background(RoundedRectangle(cornerRadius: 18).fill(Color.white.opacity(0.05)))
            } else {
                ForEach(viewModel.store.profiles) { profile in
                    vmCard(profile)
                }
            }
        }
    }

    private func vmCard(_ profile: VMProfile) -> some View {
        HStack(spacing: 14) {
            ZStack {
                RoundedRectangle(cornerRadius: 14)
                    .fill(LinearGradient(colors: [.blue.opacity(0.85), .indigo.opacity(0.85)], startPoint: .topLeading, endPoint: .bottomTrailing))
                    .frame(width: 52, height: 52)
                Image(systemName: profile.useCase.iconName)
                    .font(.title3)
                    .foregroundColor(.white)
            }

            VStack(alignment: .leading, spacing: 4) {
                Text(profile.name)
                    .font(.subheadline.weight(.bold))
                    .foregroundColor(.white)
                    .lineLimit(1)

                HStack(spacing: 6) {
                    Text(profile.architecture.rawValue.uppercased())
                    Text("•")
                    Text(profile.isSmartMemoryEnabled ? "Smart RAM" : "\(profile.manualRAMMB) MB")
                    Text("•")
                    Text(profile.isAutoPCoreEnabled ? "Auto P-Core" : "\(profile.manualVCPUs) vCPU")
                }
                .font(.caption2.monospacedDigit())
                .foregroundColor(.secondary)
            }

            Spacer()

            Button {
                viewModel.selectedProfileForSettings = profile
            } label: {
                Image(systemName: "slider.horizontal.3")
                    .font(.body)
                    .foregroundColor(.white.opacity(0.85))
                    .frame(width: 36, height: 36)
                    .background(Color.white.opacity(0.10), in: Circle())
            }

            Button {
                viewModel.launchVM(profile)
            } label: {
                Image(systemName: "play.fill")
                    .font(.body)
                    .foregroundColor(.white)
                    .frame(width: 40, height: 40)
                    .background(Color.green, in: Circle())
            }
        }
        .padding(14)
        .background(
            RoundedRectangle(cornerRadius: 18)
                .fill(Color.white.opacity(0.06))
                .overlay(RoundedRectangle(cornerRadius: 18).stroke(Color.white.opacity(0.08), lineWidth: 1))
        )
        .contextMenu {
            Button {
                viewModel.selectedProfileForSettings = profile
            } label: {
                Label("Cấu hình Smart Guard & CPU", systemImage: "slider.horizontal.3")
            }
            Button(role: .destructive) {
                viewModel.store.deleteProfile(profile)
            } label: {
                Label("Xóa máy ảo", systemImage: "trash")
            }
        }
    }

    // MARK: - 1-Click Template Catalog

    private var templateCatalogSection: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                Text("Kho Máy Ảo 1-Click")
                    .font(.headline.weight(.bold))
                    .foregroundColor(.white)
                Spacer()
                Text("Đã nhúng sẵn VirtIO")
                    .font(.caption2.weight(.semibold))
                    .foregroundColor(.green)
            }

            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: 14) {
                    ForEach(VMTemplate.catalog) { template in
                        templateCard(template)
                    }
                }
            }
        }
    }

    private func templateCard(_ template: VMTemplate) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                Image(systemName: template.iconName)
                    .font(.title2)
                    .foregroundColor(.cyan)
                Spacer()
                Text(template.badge)
                    .font(.caption2.weight(.bold))
                    .foregroundColor(.black)
                    .padding(.horizontal, 8)
                    .padding(.vertical, 3)
                    .background(Color.cyan, in: Capsule())
            }

            Text(template.title)
                .font(.subheadline.weight(.bold))
                .foregroundColor(.white)
                .lineLimit(2)

            Text(template.summary)
                .font(.caption2)
                .foregroundColor(.secondary)
                .lineLimit(3)

            Spacer(minLength: 4)

            HStack {
                Text("\(template.architecture.rawValue.uppercased()) • \(template.estimatedDownloadSize)")
                    .font(.caption2.monospacedDigit())
                    .foregroundColor(.gray)
                Spacer()
                Button("Cài 1-Click") {
                    viewModel.quickProvisionTemplate(template)
                }
                .font(.caption.weight(.bold))
                .foregroundColor(.white)
                .padding(.horizontal, 12)
                .padding(.vertical, 6)
                .background(Color.blue, in: Capsule())
            }
        }
        .padding(14)
        .frame(width: 255, height: 190)
        .background(
            RoundedRectangle(cornerRadius: 18)
                .fill(Color.white.opacity(0.06))
                .overlay(RoundedRectangle(cornerRadius: 18).stroke(Color.white.opacity(0.10), lineWidth: 1))
        )
    }
}
