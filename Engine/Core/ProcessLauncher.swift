//
//  ProcessLauncher.swift
//  Desk-simulator Engine Layer
//
//  Dynamic loader bridge invoking BootstrapBridge C symbols,
//  managing dedicated thread execution with elevated Mach QoS.
//

import Foundation

#if canImport(Darwin)
import Darwin
#endif

public enum LaunchState: Equatable {
    case idle
    case launching
    case running
    case stopping
    case terminated(exitCode: Int32)
    case failed(error: String)
}

public protocol ProcessLauncherDelegate: AnyObject {
    func launcher(_ launcher: ProcessLauncher, didChangeState state: LaunchState)
    func launcher(_ launcher: ProcessLauncher, didLogMessage message: String)
}

public final class ProcessLauncher {
    public private(set) var state: LaunchState = .idle
    public weak var delegate: ProcessLauncherDelegate?

    private var executionThread: Thread?
    private let launcherQueue = DispatchQueue(label: "com.mobimi.desk.engine.launcher", qos: .userInteractive)
    private let stopCondition = NSCondition()
    private var isStopRequested: Bool = false

    public init() {}

    /// Launches stripped QEMU engine on a dedicated interactive thread.
    public func launch(with arguments: [String], environment: [String: String] = [:]) {
        launcherQueue.async { [weak self] in
            guard let self = self else { return }
            switch self.state {
            case .idle, .terminated:
                break
            default:
                self.updateState(.failed(error: "Cannot launch: engine is already active."))
                return
            }

            self.updateState(.launching)
            self.delegate?.launcher(self, didLogMessage: "Preparing QEMU execution with \(arguments.count) arguments.")

            self.isStopRequested = false

            let thread = Thread { [weak self] in
                guard let self = self else { return }
                self.runQEMULoop(arguments: arguments, environment: environment)
            }
            thread.qualityOfService = .userInteractive
            thread.name = "com.mobimi.desk.qemu.main"
            self.executionThread = thread
            thread.start()
        }
    }

    /// Requests graceful termination of the QEMU main loop.
    public func terminate() {
        launcherQueue.async { [weak self] in
            guard let self = self else { return }
            guard self.state == .running else { return }
            self.updateState(.stopping)

            self.stopCondition.lock()
            self.isStopRequested = true
            self.stopCondition.broadcast()
            self.stopCondition.unlock()

            // Invoke BootstrapBridge request exit symbol if dynamically available
            #if canImport(Darwin)
            if let handle = dlopen(nil, RTLD_NOW) {
                defer { dlclose(handle) }
                if let exitSym = dlsym(handle, "qemu_request_exit") {
                    typealias ExitFn = @convention(c) () -> Int32
                    let fn = unsafeBitCast(exitSym, to: ExitFn.self)
                    _ = fn()
                }
            }
            #endif

            self.delegate?.launcher(self, didLogMessage: "Signaled QEMU main loop exit.")
            self.updateState(.terminated(exitCode: 0))
        }
    }

    private func runQEMULoop(arguments: [String], environment: [String: String]) {
        updateState(.running)
        delegate?.launcher(self, didLogMessage: "QEMU main loop running on thread: \(Thread.current.name ?? "unnamed")")

        #if canImport(Darwin)
        // Prepare C-compatible arguments
        var cArgs = arguments.map { strdup($0) }
        cArgs.append(nil)

        var cEnv = environment.map { strdup("\($0.key)=\($0.value)") }
        cEnv.append(nil)

        defer {
            for ptr in cArgs where ptr != nil { free(ptr) }
            for ptr in cEnv where ptr != nil { free(ptr) }
        }

        // Dynamically invoke BootstrapBridge C-ABI symbols if linked
        if let handle = dlopen(nil, RTLD_NOW) {
            defer { dlclose(handle) }
            if let initSym = dlsym(handle, "qemu_init"),
               let mainLoopSym = dlsym(handle, "qemu_main_loop"),
               let cleanupSym = dlsym(handle, "qemu_cleanup") {

                typealias InitFn = @convention(c) (Int32, UnsafeMutablePointer<UnsafeMutablePointer<CChar>?>?, UnsafeMutablePointer<UnsafeMutablePointer<CChar>?>?) -> Int32
                typealias VoidFn = @convention(c) () -> Void

                let initFn = unsafeBitCast(initSym, to: InitFn.self)
                let mainLoopFn = unsafeBitCast(mainLoopSym, to: VoidFn.self)
                let cleanupFn = unsafeBitCast(cleanupSym, to: VoidFn.self)

                let initRet = cArgs.withUnsafeMutableBufferPointer { argvPtr in
                    cEnv.withUnsafeMutableBufferPointer { envpPtr in
                        initFn(Int32(arguments.count), argvPtr.baseAddress, envpPtr.baseAddress)
                    }
                }

                if initRet == 0 {
                    mainLoopFn()
                    cleanupFn()
                    updateState(.terminated(exitCode: 0))
                    return
                } else {
                    updateState(.failed(error: "qemu_init failed with exit code: \(initRet)"))
                    return
                }
            }
        }
        #endif

        // Managed execution loop: retains thread alive until termination requested
        stopCondition.lock()
        while !isStopRequested {
            stopCondition.wait(until: Date(timeIntervalSinceNow: 0.1))
        }
        stopCondition.unlock()

        updateState(.terminated(exitCode: 0))
    }

    private func updateState(_ newState: LaunchState) {
        self.state = newState
        DispatchQueue.main.async { [weak self] in
            guard let self = self else { return }
            self.delegate?.launcher(self, didChangeState: newState)
        }
    }
}
