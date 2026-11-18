//
//  HomeViewModel.swift
//  UI/ViewModels
//
//  Main dashboard ViewModel coordinating VMStore, JIT detection, Entitlements telemetry,
//  and iOS Share Sheet / ISO URL ingestion.
//

import Foundation
import Combine

@MainActor
public final class HomeViewModel: ObservableObject {
    public let store: VMStore
    public let memoryMonitor: RuntimeMemoryMonitor
    public let pCoreScheduler: PCoreScheduler

    @Published public private(set) var jitStatus: JITStatus
    @Published public var selectedProfileForSession: VMProfile?
    @Published public var selectedProfileForSettings: VMProfile?
    @Published public var isPresentingWizard: Bool = false
    @Published public var isPresentingJITGuide: Bool = false
    @Published public var incomingISOURL: URL?
    @Published public var toastMessage: String?

    private var cancellables = Set<AnyCancellable>()

    public init(
        store: VMStore = VMStore(),
        memoryMonitor: RuntimeMemoryMonitor = RuntimeMemoryMonitor(),
        pCoreScheduler: PCoreScheduler = PCoreScheduler()
    ) {
        self.store = store
        self.memoryMonitor = memoryMonitor
        self.pCoreScheduler = pCoreScheduler
        self.jitStatus = JITDetector.detectJIT()

        store.objectWillChange
            .sink { [weak self] _ in self?.objectWillChange.send() }
            .store(in: &cancellables)

        memoryMonitor.objectWillChange
            .sink { [weak self] _ in self?.objectWillChange.send() }
            .store(in: &cancellables)
    }

    public func refreshDiagnostics() {
        self.jitStatus = JITDetector.detectJIT()
        self.memoryMonitor.refreshSnapshot()
    }

    public func quickProvisionTemplate(_ template: VMTemplate) {
        let profile = store.createVM(from: template)
        showToast("Đã tạo máy ảo '\(profile.name)' với APFS Sparse Disk!")
    }

    public func launchVM(_ profile: VMProfile) {
        store.markBooted(profile.id)
        selectedProfileForSession = profile
    }

    public func handleIncomingURL(_ url: URL) {
        let ext = url.pathExtension.lowercased()
        if ext == "iso" || ext == "img" {
            self.incomingISOURL = url
            self.isPresentingWizard = true
            showToast("Đã nhận tệp đĩa '\(url.lastPathComponent)'. Mở Smart ISO Auto-Pilot...")
        } else {
            // Stage directly into shared folder for guest Windows Desktop
            let accessing = url.startAccessingSecurityScopedResource()
            defer { if accessing { url.stopAccessingSecurityScopedResource() } }
            if (try? store.storageBridge.shareFileToGuest(filePath: url.path)) == true {
                showToast("Đã gửi '\(url.lastPathComponent)' vào thư mục Desktop máy ảo!")
            } else {
                showToast("Không thể chuyển tệp '\(url.lastPathComponent)'.")
            }
        }
    }

    public func showToast(_ message: String) {
        self.toastMessage = message
        Task {
            try? await Task.sleep(nanoseconds: 3_000_000_000)
            if self.toastMessage == message {
                self.toastMessage = nil
            }
        }
    }
}
