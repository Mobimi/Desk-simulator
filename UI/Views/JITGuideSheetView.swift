//
//  JITGuideSheetView.swift
//  UI/Views
//
//  Diagnostics and 1-tap activation guidance for TrollStore and SideStore/AltStore JIT
//  plus optional memory entitlements status.
//

import SwiftUI

public struct JITGuideSheetView: View {
    @Environment(\.dismiss) private var dismiss
    public let jitStatus: JITStatus
    public let entitlements: MemoryEntitlements
    public let safeRAMMB: Int
    public let onRefresh: () -> Void

    public init(
        jitStatus: JITStatus,
        entitlements: MemoryEntitlements,
        safeRAMMB: Int,
        onRefresh: @escaping () -> Void
    ) {
        self.jitStatus = jitStatus
        self.entitlements = entitlements
        self.safeRAMMB = safeRAMMB
        self.onRefresh = onRefresh
    }

    public var body: some View {
        NavigationView {
            List {
                Section("Trạng thái hiện tại") {
                    HStack {
                        Label("JIT Dynamic Translation", systemImage: jitStatus.isAvailable ? "bolt.fill" : "bolt.slash.fill")
                            .foregroundColor(jitStatus.isAvailable ? .green : .orange)
                        Spacer()
                        Text(jitStatus.isAvailable ? "ĐANG BẬT" : "CHƯA BẬT")
                            .font(.caption.weight(.bold))
                            .foregroundColor(jitStatus.isAvailable ? .green : .orange)
                    }
                    Text(jitStatus.advisory)
                        .font(.caption)
                        .foregroundColor(.secondary)
                }

                Section("Quyền mở rộng bộ nhớ (Không bắt buộc)") {
                    entitlementRow(
                        key: "increased-memory-limit",
                        active: entitlements.increasedMemoryLimit,
                        detail: "Cho phép nâng trần RAM lên 75–80% RAM vật lý máy."
                    )
                    entitlementRow(
                        key: "extended-virtual-addressing",
                        active: entitlements.extendedVirtualAddressing,
                        detail: "Mở rộng không gian địa chỉ ảo 64-bit cho Windows/Linux nặng."
                    )
                    HStack {
                        Text("Ngưỡng Smart Memory Guard hiện tại")
                        Spacer()
                        Text("\(safeRAMMB) MB")
                            .font(.body.monospacedDigit().weight(.bold))
                            .foregroundColor(.cyan)
                    }
                }

                Section("Hướng dẫn kích hoạt JIT nhanh") {
                    VStack(alignment: .leading, spacing: 6) {
                        Text("1. Qua TrollStore (Khuyên dùng)")
                            .font(.subheadline.weight(.bold))
                        Text("Cài bản DeskSimulator-TrollStore.ipa — JIT và cả 2 quyền mở rộng RAM tự động bật vĩnh viễn không cần máy tính.")
                            .font(.caption)
                            .foregroundColor(.secondary)
                    }
                    VStack(alignment: .leading, spacing: 6) {
                        Text("2. Qua SideStore / AltStore (Sideload)")
                            .font(.subheadline.weight(.bold))
                        Text("Cài bản DeskSimulator-Sideload.ipa -> Bật VPN WireGuard của SideStore -> Nhấn giữ icon Desk Simulator trong SideStore chọn 'Enable JIT'.")
                            .font(.caption)
                            .foregroundColor(.secondary)
                    }
                }
            }
            .navigationTitle("Chẩn Đoán JIT & RAM")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .navigationBarLeading) {
                    Button("Kiểm tra lại") { onRefresh() }
                }
                ToolbarItem(placement: .confirmationAction) {
                    Button("Xong") { dismiss() }
                }
            }
        }
        .navigationViewStyle(.stack)
    }

    private func entitlementRow(key: String, active: Bool, detail: String) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack {
                Text(key)
                    .font(.caption.monospaced().weight(.semibold))
                Spacer()
                Text(active ? "ĐÃ BẬT" : "Tự giảm giới hạn")
                    .font(.caption2.weight(.bold))
                    .foregroundColor(active ? .green : .secondary)
            }
            Text(detail)
                .font(.caption2)
                .foregroundColor(.secondary)
        }
    }
}
