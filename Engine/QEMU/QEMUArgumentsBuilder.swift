//
//  QEMUArgumentsBuilder.swift
//  Desk-simulator Engine Layer
//
//  CLI argument builder enforcing target whitelist, clamped TCG buffer size,
//  and Unix Domain Socket SPICE IPC.
//

import Foundation

public struct QEMUConfiguration {
    public var architecture: TargetArchitecture
    public var ramMB: Int
    public var tbSizeMB: Int
    public var vCPUs: Int
    public var spiceSocketPath: String
    public var qmpSocketPath: String?
    public var diskImagePath: String?
    public var cdromImagePath: String?
    public var disableSmartcard: Bool
    public var additionalArgs: [String]

    public init(
        architecture: TargetArchitecture,
        ramMB: Int = 2048,
        tbSizeMB: Int = 128,
        vCPUs: Int = 2,
        spiceSocketPath: String,
        qmpSocketPath: String? = nil,
        diskImagePath: String? = nil,
        cdromImagePath: String? = nil,
        disableSmartcard: Bool = true,
        additionalArgs: [String] = []
    ) {
        self.architecture = architecture
        self.ramMB = ramMB
        self.tbSizeMB = tbSizeMB
        self.vCPUs = vCPUs
        self.spiceSocketPath = spiceSocketPath
        self.qmpSocketPath = qmpSocketPath
        self.diskImagePath = diskImagePath
        self.cdromImagePath = cdromImagePath
        self.disableSmartcard = disableSmartcard
        self.additionalArgs = additionalArgs
    }
}

public enum ArgumentBuilderError: Error, LocalizedError {
    case invalidTargetArchitecture(String)
    case invalidSocketPath(String)
    case tcpLoopbackProhibited(String)
    case socketPathTooLong(Int)
    case invalidMemorySize(Int)

    public var errorDescription: String? {
        switch self {
        case .invalidTargetArchitecture(let target):
            return "Target architecture '\(target)' is forbidden or not whitelisted."
        case .invalidSocketPath(let path):
            return "Socket path '\(path)' is empty or malformed."
        case .tcpLoopbackProhibited(let target):
            return "TCP loopback is strictly prohibited ('\(target)'). Must use Unix Domain Socket."
        case .socketPathTooLong(let len):
            return "Unix socket path length (\(len)) exceeds POSIX limit of 108 bytes."
        case .invalidMemorySize(let mb):
            return "Configured RAM size (\(mb)MB) is invalid."
        }
    }
}

public final class QEMUArgumentsBuilder {
    public static let tcgMinMB: Int = 128
    public static let tcgMaxMB: Int = 256
    public static let defaultTcgMB: Int = 128
    public static let maxSocketPathLength: Int = 108

    /// Clamps requested TCG translation buffer size between 128MB and 256MB.
    public static func clampTCGSize(_ requestedMB: Int) -> Int {
        if requestedMB < tcgMinMB {
            return tcgMinMB
        }
        if requestedMB > tcgMaxMB {
            return tcgMaxMB
        }
        return requestedMB
    }

    /// Validates socket path for Unix Domain Socket IPC compliance.
    public static func validateSocketPath(_ path: String) throws {
        let trimmed = path.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else {
            throw ArgumentBuilderError.invalidSocketPath(path)
        }
        guard !trimmed.contains("\0") else {
            throw ArgumentBuilderError.invalidSocketPath("Contains null byte")
        }

        let lower = trimmed.lowercased()
        if lower.contains("127.0.0.1") || lower.contains("localhost") || lower.contains("0.0.0.0") || lower.contains("port=") {
            throw ArgumentBuilderError.tcpLoopbackProhibited(path)
        }

        guard let data = trimmed.data(using: .utf8), data.count <= maxSocketPathLength else {
            throw ArgumentBuilderError.socketPathTooLong(trimmed.utf8.count)
        }
    }

    /// Generates SPICE arguments binding exclusively to Unix Domain Socket.
    public static func generateSpiceUdsArgs(socketPath: String, disableSmartcard: Bool = true) throws -> [String] {
        try validateSocketPath(socketPath)

        var args = [
            "-spice",
            "unix=on,addr=\(socketPath.trimmingCharacters(in: .whitespacesAndNewlines)),disable-ticketing=on"
        ]
        if disableSmartcard {
            args.append(contentsOf: ["-global", "spice.smartcard=off"])
        }
        return args
    }

    /// Builds the complete QEMU CLI argument array for process execution.
    public static func buildArguments(from config: QEMUConfiguration) throws -> [String] {
        var args: [String] = []

        // Binary name
        args.append(config.architecture.binaryName)

        // Memory allocation
        guard config.ramMB > 0 else {
            throw ArgumentBuilderError.invalidMemorySize(config.ramMB)
        }
        args.append(contentsOf: ["-m", String(config.ramMB)])

        // SMP configuration
        let cores = max(1, config.vCPUs)
        args.append(contentsOf: ["-smp", "cpus=\(cores),cores=\(cores)"])

        // TCG accelerator with clamped buffer size
        let clampedTB = clampTCGSize(config.tbSizeMB)
        args.append(contentsOf: ["-accel", "tcg,tb-size=\(clampedTB)"])

        // SPICE display & input over Unix Domain Socket
        let spiceArgs = try generateSpiceUdsArgs(
            socketPath: config.spiceSocketPath,
            disableSmartcard: config.disableSmartcard
        )
        args.append(contentsOf: spiceArgs)

        // QMP Monitor socket if configured
        if let qmpSocket = config.qmpSocketPath {
            try validateSocketPath(qmpSocket)
            args.append(contentsOf: [
                "-qmp",
                "unix:\(qmpSocket),server=on,wait=off"
            ])
        }

        // Primary virtual storage disk
        if let disk = config.diskImagePath {
            args.append(contentsOf: [
                "-drive",
                "file=\(disk),if=virtio,cache=writethrough"
            ])
        }

        // CD-ROM media installer
        if let cdrom = config.cdromImagePath {
            args.append(contentsOf: [
                "-drive",
                "file=\(cdrom),media=cdrom,readonly=on"
            ])
        }

        // Additional user / system arguments
        for arg in config.additionalArgs {
            let lower = arg.lowercased()
            if lower.contains("127.0.0.1") || lower.contains("localhost") || lower.contains("0.0.0.0") || lower.contains("port=") {
                throw ArgumentBuilderError.tcpLoopbackProhibited(arg)
            }
        }
        args.append(contentsOf: config.additionalArgs)

        return args
    }
}
