//
//  SPICEConnection.swift
//  Desk-simulator Engine Layer
//
//  Unix Domain Socket SPICE client connection wrapper.
//

import Foundation

#if canImport(Darwin)
import Darwin
#elseif canImport(Glibc)
import Glibc
#endif

public enum SPICEConnectionState: Equatable {
    case disconnected
    case connecting(socketPath: String)
    case connected(socketPath: String)
    case failed(error: String)
}

public protocol SPICEConnectionDelegate: AnyObject {
    func spiceConnection(_ connection: SPICEConnection, didChangeState state: SPICEConnectionState)
    func spiceConnection(_ connection: SPICEConnection, didReceiveDisplayFrame data: Data, width: Int, height: Int)
    func spiceConnection(_ connection: SPICEConnection, didEncounterError error: Error)
}

public final class SPICEConnection {
    public let socketPath: String
    public let channelPolicy: SPICEChannelPolicy
    public private(set) var state: SPICEConnectionState = .disconnected
    public weak var delegate: SPICEConnectionDelegate?

    private var socketFD: Int32 = -1
    private let connectionQueue = DispatchQueue(label: "com.mobimi.desk.spice.connection", qos: .userInteractive)

    public init(socketPath: String, channelPolicy: SPICEChannelPolicy = .optimizedForIOS) throws {
        try QEMUArgumentsBuilder.validateSocketPath(socketPath)
        self.socketPath = socketPath
        self.channelPolicy = channelPolicy
    }

    deinit {
        disconnectSync()
    }

    /// Establishes connection to the SPICE server via local Unix Domain Socket.
    public func connect() {
        connectionQueue.async { [weak self] in
            guard let self = self else { return }
            self.updateState(.connecting(socketPath: self.socketPath))

            guard FileManager.default.fileExists(atPath: self.socketPath) else {
                self.updateState(.failed(error: "Socket file does not exist at \(self.socketPath)"))
                return
            }

            #if canImport(Darwin) || canImport(Glibc)
            let fd = socket(AF_UNIX, SOCK_STREAM, 0)
            guard fd >= 0 else {
                let errStr = String(cString: strerror(errno))
                self.updateState(.failed(error: "Failed to allocate UDS socket: \(errStr)"))
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
                self.updateState(.failed(error: "Socket path length exceeds maximum allowable length."))
                return
            }

            self.socketPath.withCString { cstr in
                withUnsafeMutablePointer(to: &addr.sun_path) { pathPtr in
                    let rawPtr = UnsafeMutableRawPointer(pathPtr).assumingMemoryBound(to: CChar.self)
                    strncpy(rawPtr, cstr, maxPathLen - 1)
                    rawPtr[maxPathLen - 1] = 0
                }
            }

            let res = withUnsafePointer(to: &addr) { addrPtr in
                addrPtr.withMemoryRebound(to: sockaddr.self, capacity: 1) { sa in
                    #if canImport(Darwin)
                    return Darwin.connect(fd, sa, socklen_t(MemoryLayout<sockaddr_un>.size))
                    #else
                    return Glibc.connect(fd, sa, socklen_t(MemoryLayout<sockaddr_un>.size))
                    #endif
                }
            }

            guard res == 0 else {
                let errStr = String(cString: strerror(errno))
                close(fd)
                self.updateState(.failed(error: "connect() to SPICE UDS failed: \(errStr)"))
                return
            }

            self.socketFD = fd
            self.updateState(.connected(socketPath: self.socketPath))
            #else
            self.updateState(.connected(socketPath: self.socketPath))
            #endif
        }
    }

    /// Disconnects from the SPICE Unix Domain Socket.
    public func disconnect() {
        connectionQueue.async { [weak self] in
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
        updateState(.disconnected)
    }

    /// Sends input event packet (e.g. mouse move, key press) over UDS.
    public func sendInputEvent(data: Data) -> Bool {
        guard case .connected = state else { return false }

        #if canImport(Darwin) || canImport(Glibc)
        guard socketFD >= 0 else { return false }
        return data.withUnsafeBytes { rawBuffer -> Bool in
            guard let baseAddress = rawBuffer.baseAddress else { return true }
            var totalSent = 0
            let totalLength = data.count
            while totalSent < totalLength {
                let sent = write(socketFD, baseAddress.advanced(by: totalSent), totalLength - totalSent)
                if sent < 0 {
                    if errno == EINTR { continue }
                    return false
                }
                totalSent += sent
            }
            return true
        }
        #else
        return true
        #endif
    }

    private func updateState(_ newState: SPICEConnectionState) {
        self.state = newState
        DispatchQueue.main.async { [weak self] in
            guard let self = self else { return }
            self.delegate?.spiceConnection(self, didChangeState: newState)
        }
    }
}
