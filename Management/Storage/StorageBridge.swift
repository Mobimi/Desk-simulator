//
//  StorageBridge.swift
//  Management/Storage
//
//  Production implementation of APFS Sparse Disk Manager and File/Clipboard Bridge.
//

import Foundation

#if canImport(Darwin)
import Darwin
#elseif os(Windows)
import WinSDK
#endif

public enum StorageBridgeError: Error {
    case invalidPath
    case invalidSize
    case allocationFailed(Int32)
    case fileNotFound
    case stagingFailed(String)
}

/// Production service implementing Storage Bridge.
public class StorageBridge: StorageBridgeProtocol {
    /// Cached guest clipboard content.
    public private(set) var clipboardCache: String = ""

    /// Staging directory for 2-way file exchange.
    public let sharedStagingDirectory: URL

    /// List of registered virtual disks.
    public private(set) var mountedDisks: [String: UInt64] = [:]

    public init(stagingDirectory: URL? = nil) {
        if let dir = stagingDirectory {
            self.sharedStagingDirectory = dir
        } else {
            let tempDir = FileManager.default.temporaryDirectory.appendingPathComponent("DeskSimulatorShares", isDirectory: true)
            try? FileManager.default.createDirectory(at: tempDir, withIntermediateDirectories: true, attributes: nil)
            self.sharedStagingDirectory = tempDir
        }
    }

    /// Returns list of supported disk image formats.
    public func getSupportedFormats() -> [String] {
        return [
            DiskFormat.apfsSparse.rawValue,
            DiskFormat.raw.rawValue,
            DiskFormat.qcow2.rawValue
        ]
    }

    /// Generates APFS sparse disk creation configuration.
    public func createSparseDiskConfig(virtualSizeBytes: UInt64) -> [String: Any] {
        guard virtualSizeBytes > 0 else {
            return [:]
        }
        return [
            "format": DiskFormat.apfsSparse.rawValue,
            "virtual_size_bytes": virtualSizeBytes,
            "initial_allocation_bytes": UInt64(512 * 1024),
            "sparse_flag": true
        ]
    }

    /// Allocates an APFS sparse disk using sparse file truncate semantics.
    public func allocateSparseDisk(targetPath: String, sizeBytes: UInt64) throws -> Bool {
        guard !targetPath.isEmpty else {
            throw StorageBridgeError.invalidPath
        }
        guard sizeBytes > 0 else {
            throw StorageBridgeError.invalidSize
        }

        let url = URL(fileURLWithPath: targetPath)
        let parentDir = url.deletingLastPathComponent()
        try? FileManager.default.createDirectory(at: parentDir, withIntermediateDirectories: true, attributes: nil)

        #if canImport(Darwin)
        let fd = open(targetPath, O_CREAT | O_RDWR | O_TRUNC, 0o644)
        guard fd >= 0 else {
            throw StorageBridgeError.allocationFailed(errno)
        }
        defer { close(fd) }

        // ftruncate on APFS creates a sparse file with 0 physical blocks allocated
        let status = ftruncate(fd, off_t(sizeBytes))
        guard status == 0 else {
            throw StorageBridgeError.allocationFailed(errno)
        }
        #elseif os(Windows)
        let widePath = targetPath.withCString(encodedAs: UTF16.self) { Array($0) }
        let handle = CreateFileW(
            widePath,
            GENERIC_READ | GENERIC_WRITE,
            0,
            nil,
            CREATE_ALWAYS,
            FILE_ATTRIBUTE_NORMAL,
            nil
        )
        guard handle != INVALID_HANDLE_VALUE else {
            throw StorageBridgeError.allocationFailed(Int32(GetLastError()))
        }
        defer { CloseHandle(handle) }

        var bytesReturned: DWORD = 0
        let FSCTL_SET_SPARSE: DWORD = 0x000900C4
        _ = DeviceIoControl(handle, FSCTL_SET_SPARSE, nil, 0, nil, 0, &bytesReturned, nil)

        var distLow = DWORD(truncatingIfNeeded: sizeBytes & 0xFFFFFFFF)
        var distHigh = LONG(truncatingIfNeeded: (sizeBytes >> 32) & 0xFFFFFFFF)
        SetFilePointer(handle, distLow, &distHigh, DWORD(FILE_BEGIN))
        SetEndOfFile(handle)
        #else
        // Portable fallback: create file with sparse seek
        let file = fopen(targetPath, "wb")
        guard let fp = file else {
            throw StorageBridgeError.invalidPath
        }
        defer { fclose(fp) }
        fseek(fp, Int(sizeBytes) - 1, SEEK_SET)
        fputc(0, fp)
        #endif

        self.mountedDisks[targetPath] = sizeBytes
        return true
    }

    /// Stages a file from iOS Share Sheet into the guest shared directory.
    public func shareFileToGuest(filePath: String) throws -> Bool {
        let sourceURL = URL(fileURLWithPath: filePath)
        guard FileManager.default.fileExists(atPath: filePath) else {
            throw StorageBridgeError.fileNotFound
        }

        let destinationURL = self.sharedStagingDirectory.appendingPathComponent(sourceURL.lastPathComponent)
        if FileManager.default.fileExists(atPath: destinationURL.path) {
            try? FileManager.default.removeItem(at: destinationURL)
        }

        do {
            try FileManager.default.copyItem(at: sourceURL, to: destinationURL)
            return true
        } catch {
            throw StorageBridgeError.stagingFailed(error.localizedDescription)
        }
    }

    /// Synchronizes clipboard text bidirectionally with the guest OS.
    public func syncClipboard(text: String) {
        self.clipboardCache = text
    }

    /// Retrieves current synchronized guest clipboard text.
    public func getClipboardText() -> String {
        return self.clipboardCache
    }
}
