//
//  QMPClient.swift
//  Desk-simulator Engine Layer
//
//  QEMU Machine Protocol (QMP) client over Unix Domain Socket.
//  Dispatches VirtIO ballooning, pause, resume, and lifecycle queries.
//

import Foundation

#if canImport(Darwin)
import Darwin
#elseif canImport(Glibc)
import Glibc
#endif

public enum QMPError: Error, LocalizedError {
    case notConnected
    case handshakeFailed(String)
    case commandFailed(String)
    case invalidResponse
    case socketError(String)

    public var errorDescription: String? {
        switch self {
        case .notConnected:
            return "QMP client is not connected to monitor socket."
        case .handshakeFailed(let reason):
            return "QMP capabilities handshake failed: \(reason)"
        case .commandFailed(let detail):
            return "QMP command execution failed: \(detail)"
        case .invalidResponse:
            return "Received invalid or unparseable JSON response from QMP."
        case .socketError(let msg):
            return "QMP socket error: \(msg)"
        }
    }
}

public final class QMPClient {
    public let socketPath: String
    public private(set) var isConnected: Bool = false
    public private(set) var isNegotiated: Bool = false

    private var socketFD: Int32 = -1
    private let qmpQueue = DispatchQueue(label: "com.mobimi.desk.engine.qmp", qos: .userInteractive)

    public init(socketPath: String) throws {
        try QEMUArgumentsBuilder.validateSocketPath(socketPath)
        self.socketPath = socketPath
    }

    deinit {
        disconnectSync()
    }

    /// Establishes connection to the QMP Unix Domain Socket and completes capabilities handshake.
    public func connect(completion: @escaping (Result<Void, QMPError>) -> Void) {
        qmpQueue.async { [weak self] in
            guard let self = self else { return }

            guard FileManager.default.fileExists(atPath: self.socketPath) else {
                completion(.failure(.socketError("Socket not found at \(self.socketPath)")))
                return
            }

            #if canImport(Darwin) || canImport(Glibc)
            let fd = socket(AF_UNIX, SOCK_STREAM, 0)
            guard fd >= 0 else {
                let errStr = String(cString: strerror(errno))
                completion(.failure(.socketError("Failed to create socket: \(errStr)")))
                return
            }

            var addr = sockaddr_un()
            #if canImport(Darwin)
            addr.sun_len = UInt8(MemoryLayout<sockaddr_un>.size)
            #endif
            addr.sun_family = sa_family_t(AF_UNIX)

            let maxPathLen = MemoryLayout.size(ofValue: addr.sun_path)
            guard self.socketPath.utf8.count < maxPathLen else {
                close(fd)
                completion(.failure(.socketError("Socket path exceeds maximum allowable length.")))
                return
            }

            self.socketPath.withCString { cstr in
                withUnsafeMutablePointer(to: &addr.sun_path) { pathPtr in
                    let rawPtr = UnsafeMutableRawPointer(pathPtr).assumingMemoryBound(to: CChar.self)
                    strncpy(rawPtr, cstr, maxPathLen - 1)
                    rawPtr[maxPathLen - 1] = 0
                }
            }

            let connectRes = withUnsafePointer(to: &addr) { addrPtr in
                addrPtr.withMemoryRebound(to: sockaddr.self, capacity: 1) { sa in
                    #if canImport(Darwin)
                    return Darwin.connect(fd, sa, socklen_t(MemoryLayout<sockaddr_un>.size))
                    #else
                    return Glibc.connect(fd, sa, socklen_t(MemoryLayout<sockaddr_un>.size))
                    #endif
                }
            }

            guard connectRes == 0 else {
                let errStr = String(cString: strerror(errno))
                close(fd)
                completion(.failure(.socketError("connect() failed: \(errStr)")))
                return
            }

            self.socketFD = fd
            self.isConnected = true

            // Read QMP greeting banner
            _ = self.readRawLine(fd: fd)

            // Negotiate QMP capabilities
            let capCmd: [String: Any] = ["execute": "qmp_capabilities"]
            self.executeRaw(command: capCmd) { capResult in
                switch capResult {
                case .success:
                    self.isNegotiated = true
                    completion(.success(()))
                case .failure(let err):
                    self.disconnectSync()
                    completion(.failure(.handshakeFailed(err.localizedDescription)))
                }
            }
            #else
            // Fallback for non-POSIX build simulation
            self.isConnected = true
            self.isNegotiated = true
            completion(.success(()))
            #endif
        }
    }

    /// Disconnects from the QMP monitor socket.
    public func disconnect() {
        qmpQueue.async { [weak self] in
            self?.disconnectSync()
        }
    }

    private func disconnectSync() {
        if socketFD >= 0 {
            #if canImport(Darwin) || canImport(Glibc)
            close(socketFD)
            #endif
            socketFD = -1
        }
        isConnected = false
        isNegotiated = false
    }

    /// Executes arbitrary QMP command dict over the socket wire.
    public func executeRaw(command: [String: Any], completion: @escaping (Result<[String: Any], QMPError>) -> Void) {
        qmpQueue.async { [weak self] in
            guard let self = self, self.isConnected else {
                completion(.failure(.notConnected))
                return
            }

            do {
                var payload = try JSONSerialization.data(withJSONObject: command, options: [])
                payload.append(0x0A) // Append '\n' per QMP wire protocol

                #if canImport(Darwin) || canImport(Glibc)
                guard self.socketFD >= 0 else {
                    completion(.failure(.notConnected))
                    return
                }

                // Write command payload to socket
                let writeResult = self.writeRawBytes(data: payload, fd: self.socketFD)
                guard writeResult else {
                    completion(.failure(.socketError("Failed to write command to socket.")))
                    return
                }

                // Read newline-terminated JSON response
                guard let responseData = self.readRawLine(fd: self.socketFD) else {
                    completion(.failure(.invalidResponse))
                    return
                }

                guard let json = try JSONSerialization.jsonObject(with: responseData, options: []) as? [String: Any] else {
                    completion(.failure(.invalidResponse))
                    return
                }

                if let errDict = json["error"] as? [String: Any], let desc = errDict["desc"] as? String {
                    completion(.failure(.commandFailed(desc)))
                    return
                }

                completion(.success(json))
                #else
                let simulatedResponse: [String: Any] = ["return": [:]]
                completion(.success(simulatedResponse))
                #endif
            } catch {
                completion(.failure(.commandFailed(error.localizedDescription)))
            }
        }
    }

    #if canImport(Darwin) || canImport(Glibc)
    private func writeRawBytes(data: Data, fd: Int32) -> Bool {
        return data.withUnsafeBytes { rawBuffer -> Bool in
            guard let baseAddress = rawBuffer.baseAddress else { return true }
            var totalSent = 0
            let totalLength = data.count
            while totalSent < totalLength {
                let sent = write(fd, baseAddress.advanced(by: totalSent), totalLength - totalSent)
                if sent < 0 {
                    if errno == EINTR { continue }
                    return false
                }
                totalSent += sent
            }
            return true
        }
    }

    private func readRawLine(fd: Int32) -> Data? {
        var buffer = Data()
        var char: UInt8 = 0
        while true {
            let bytesRead = read(fd, &char, 1)
            if bytesRead == 1 {
                if char == 0x0A { // '\n'
                    break
                }
                buffer.append(char)
            } else if bytesRead < 0 && errno == EINTR {
                continue
            } else {
                break
            }
        }
        return buffer.isEmpty ? nil : buffer
    }
    #endif

    public func setBalloonMemory(targetBytes: UInt64, completion: @escaping (Result<Void, QMPError>) -> Void) {
        let cmd: [String: Any] = [
            "execute": "balloon",
            "arguments": ["value": targetBytes]
        ]
        executeRaw(command: cmd) { result in
            switch result {
            case .success: completion(.success(()))
            case .failure(let err): completion(.failure(err))
            }
        }
    }

    public func pauseVM(completion: @escaping (Result<Void, QMPError>) -> Void) {
        executeRaw(command: ["execute": "stop"]) { result in
            switch result {
            case .success: completion(.success(()))
            case .failure(let err): completion(.failure(err))
            }
        }
    }

    public func resumeVM(completion: @escaping (Result<Void, QMPError>) -> Void) {
        executeRaw(command: ["execute": "cont"]) { result in
            switch result {
            case .success: completion(.success(()))
            case .failure(let err): completion(.failure(err))
            }
        }
    }

    public func queryStatus(completion: @escaping (Result<[String: Any], QMPError>) -> Void) {
        executeRaw(command: ["execute": "query-status"], completion: completion)
    }

    public func shutdown(force: Bool = false, completion: @escaping (Result<Void, QMPError>) -> Void) {
        let cmd: [String: Any] = ["execute": force ? "quit" : "system_powerdown"]
        executeRaw(command: cmd) { result in
            switch result {
            case .success: completion(.success(()))
            case .failure(let err): completion(.failure(err))
            }
        }
    }
}
