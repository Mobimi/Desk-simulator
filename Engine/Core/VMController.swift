//
//  VMController.swift
//  Desk-simulator Engine Layer
//
//  Virtual Machine lifecycle controller managing QEMU process execution,
//  SPICE display/input connection, and QMP monitor IPC.
//

import Foundation

public enum VMState: Equatable {
    case stopped
    case starting
    case running
    case paused
    case stopping
    case error(String)
}

public protocol VMControllerDelegate: AnyObject {
    func vmController(_ controller: VMController, didChangeState state: VMState)
    func vmController(_ controller: VMController, didReceiveError error: Error)
}

public final class VMController: NSObject {
    public private(set) var state: VMState = .stopped
    public weak var delegate: VMControllerDelegate?

    public let configuration: QEMUConfiguration
    public let launcher: ProcessLauncher
    public private(set) var spiceConnection: SPICEConnection?
    public private(set) var qmpClient: QMPClient?

    private let controllerQueue = DispatchQueue(label: "com.mobimi.desk.vm.controller", qos: .userInteractive)

    public init(configuration: QEMUConfiguration) {
        self.configuration = configuration
        self.launcher = ProcessLauncher()
        self.spiceConnection = try? SPICEConnection(
            socketPath: configuration.spiceSocketPath,
            channelPolicy: .optimizedForIOS
        )
        if let qmpSocket = configuration.qmpSocketPath {
            self.qmpClient = try? QMPClient(socketPath: qmpSocket)
        }
        super.init()
        self.launcher.delegate = self
    }

    /// Boots the Virtual Machine by assembling CLI arguments and starting the engine thread.
    public func start() {
        // Guarantee SPICE connection is synchronously initialized and non-nil before start() returns
        do {
            let existingSpiceDelegate = self.spiceConnection?.delegate
            self.spiceConnection = try SPICEConnection(
                socketPath: self.configuration.spiceSocketPath,
                channelPolicy: .optimizedForIOS
            )
            self.spiceConnection?.delegate = existingSpiceDelegate

            if let qmpSocket = self.configuration.qmpSocketPath {
                self.qmpClient = try QMPClient(socketPath: qmpSocket)
            }
        } catch {
            self.updateState(.error(error.localizedDescription))
            self.delegate?.vmController(self, didReceiveError: error)
            return
        }

        controllerQueue.async { [weak self] in
            guard let self = self else { return }
            switch self.state {
            case .stopped, .error:
                break
            default:
                return
            }

            self.updateState(.starting)

            do {
                let args = try QEMUArgumentsBuilder.buildArguments(from: self.configuration)

                // Launch QEMU engine thread
                self.launcher.launch(with: args)
                self.updateState(.running)

                // Connect SPICE client
                self.spiceConnection?.connect()

                // Connect QMP monitor client
                self.qmpClient?.connect { _ in }

            } catch {
                self.updateState(.error(error.localizedDescription))
                self.delegate?.vmController(self, didReceiveError: error)
            }
        }
    }

    /// Pauses VM execution via QMP monitor.
    public func pause() {
        controllerQueue.async { [weak self] in
            guard let self = self else { return }
            guard self.state == .running else { return }

            if let qmp = self.qmpClient {
                qmp.pauseVM { [weak self] result in
                    guard let self = self else { return }
                    switch result {
                    case .success:
                        self.updateState(.paused)
                    case .failure(let err):
                        self.delegate?.vmController(self, didReceiveError: err)
                    }
                }
            } else {
                self.updateState(.paused)
            }
        }
    }

    /// Resumes VM execution from paused state via QMP monitor.
    public func resume() {
        controllerQueue.async { [weak self] in
            guard let self = self else { return }
            guard self.state == .paused else { return }

            if let qmp = self.qmpClient {
                qmp.resumeVM { [weak self] result in
                    guard let self = self else { return }
                    switch result {
                    case .success:
                        self.updateState(.running)
                    case .failure(let err):
                        self.delegate?.vmController(self, didReceiveError: err)
                    }
                }
            } else {
                self.updateState(.running)
            }
        }
    }

    /// Stops the Virtual Machine and cleans up all IPC sockets.
    public func stop(force: Bool = false) {
        controllerQueue.async { [weak self] in
            guard let self = self else { return }
            guard self.state == .running || self.state == .paused else { return }

            self.updateState(.stopping)

            self.spiceConnection?.disconnect()
            if let qmp = self.qmpClient, qmp.isConnected {
                qmp.shutdown(force: force) { [weak self] _ in
                    guard let self = self else { return }
                    self.qmpClient?.disconnect()
                    self.launcher.terminate()
                    self.updateState(.stopped)
                }
            } else {
                self.qmpClient?.disconnect()
                self.launcher.terminate()
                self.updateState(.stopped)
            }
        }
    }

    /// Adjusts guest RAM balloon target in megabytes via QMP VirtIO ballooning.
    public func setMemoryBalloon(mb: Int, completion: ((Result<Void, QMPError>) -> Void)? = nil) {
        guard mb > 0 else {
            completion?(.failure(.commandFailed("Invalid balloon target: \(mb)MB")))
            return
        }
        let bytes = UInt64(mb) * 1024 * 1024
        controllerQueue.async { [weak self] in
            guard let self = self else { return }
            if let qmp = self.qmpClient {
                qmp.setBalloonMemory(targetBytes: bytes) { result in
                    completion?(result)
                }
            } else {
                completion?(.failure(.notConnected))
            }
        }
    }

    /// Dispatches a VirtIO-Balloon memory target or emergency QMP command from Smart Memory Guard.
    public func dispatchMemoryCommand(_ command: QMPCommand) {
        controllerQueue.async { [weak self] in
            guard let self = self else { return }
            if command.execute == "stop" {
                self.pause()
            } else if command.execute == "cont" {
                self.resume()
            } else if command.execute == "balloon", let targetBytes = command.arguments["value"], targetBytes > 0 {
                self.qmpClient?.setBalloonMemory(targetBytes: UInt64(targetBytes)) { _ in }
            }
        }
    }

    private func updateState(_ newState: VMState) {
        self.state = newState
        DispatchQueue.main.async { [weak self] in
            guard let self = self else { return }
            self.delegate?.vmController(self, didChangeState: newState)
        }
    }
}

extension VMController: ProcessLauncherDelegate {
    public func launcher(_ launcher: ProcessLauncher, didChangeState state: LaunchState) {
        controllerQueue.async { [weak self] in
            guard let self = self else { return }
            switch state {
            case .failed(let error):
                self.updateState(.error("Launcher failed: \(error)"))
            case .terminated:
                if self.state == .stopping || self.state == .running {
                    self.updateState(.stopped)
                }
            default:
                break
            }
        }
    }

    public func launcher(_ launcher: ProcessLauncher, didLogMessage message: String) {
        // Telemetry & diagnostics logging hook
    }
}
