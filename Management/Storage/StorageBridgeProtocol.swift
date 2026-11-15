//
//  StorageBridgeProtocol.swift
//  Management/Storage
//
//  Created for Desk-simulator Management Layer.
//

import Foundation

/// Supported virtual disk image formats.
public enum DiskFormat: String, Codable {
    case apfsSparse = "APFS_SPARSE"
    case raw = "RAW"
    case qcow2 = "QCOW2"
}

/// Sparse disk configuration representation.
public struct SparseDiskConfig: Codable, Equatable {
    public let format: DiskFormat
    public let virtualSizeBytes: UInt64
    public let initialAllocationBytes: UInt64
    public let sparseFlag: Bool

    public init(
        format: DiskFormat = .apfsSparse,
        virtualSizeBytes: UInt64,
        initialAllocationBytes: UInt64 = 512 * 1024,
        sparseFlag: Bool = true
    ) {
        self.format = format
        self.virtualSizeBytes = virtualSizeBytes
        self.initialAllocationBytes = initialAllocationBytes
        self.sparseFlag = sparseFlag
    }
}

/// Protocol defining APFS Sparse Disk manager and two-way iOS bridge contracts.
public protocol StorageBridgeProtocol {
    /// Returns supported disk image formats.
    func getSupportedFormats() -> [String]

    /// Generates APFS sparse disk creation configuration.
    func createSparseDiskConfig(virtualSizeBytes: UInt64) -> [String: Any]

    /// Creates and allocates an APFS sparse disk file at targetPath.
    func allocateSparseDisk(targetPath: String, sizeBytes: UInt64) throws -> Bool

    /// Stages a file from iOS Share Sheet into the guest shared directory.
    func shareFileToGuest(filePath: String) throws -> Bool

    /// Synchronizes clipboard text bidirectionally with the guest OS.
    func syncClipboard(text: String)

    /// Retrieves current synchronized guest clipboard text.
    func getClipboardText() -> String
}
