//
//  ChannelPolicy.swift
//  Desk-simulator Engine Layer
//
//  Channel policy explicitly pruning non-essential SPICE channels
//  (Smartcard, separate WebDAV) to reclaim ~100MB host RAM.
//

import Foundation

public enum SPICEChannel: String, CaseIterable, Codable {
    case main = "main"
    case display = "display"
    case inputs = "inputs"
    case cursor = "cursor"
    case playback = "playback"
    case record = "record"
    case smartcard = "smartcard"
    case usbredir = "usbredir"
    case webdav = "webdav"

    public var isEssential: Bool {
        switch self {
        case .main, .display, .inputs, .cursor, .playback:
            return true
        default:
            return false
        }
    }

    public var isPrunedByDefault: Bool {
        switch self {
        case .smartcard, .usbredir, .webdav:
            return true
        default:
            return false
        }
    }
}

public struct SPICEChannelPolicy {
    public private(set) var enabledChannels: Set<SPICEChannel>
    public private(set) var disabledChannels: Set<SPICEChannel>

    /// Target memory reclaim baseline in MB (Sec 2.3 of architecture spec)
    public static let targetMemorySavingMB: Int = 100

    public init(
        enabledChannels: Set<SPICEChannel> = [.main, .display, .inputs, .cursor, .playback],
        disabledChannels: Set<SPICEChannel> = [.smartcard, .usbredir, .webdav]
    ) {
        self.enabledChannels = enabledChannels
        self.disabledChannels = disabledChannels
    }

    /// Factory method for mobile-optimized profile
    public static var optimizedForIOS: SPICEChannelPolicy {
        return SPICEChannelPolicy(
            enabledChannels: [.main, .display, .inputs, .cursor, .playback],
            disabledChannels: [.smartcard, .usbredir, .webdav]
        )
    }

    /// Verifies that non-essential channels are safely pruned
    public var isCompliantWithMobileLimits: Bool {
        guard !disabledChannels.contains(.main),
              !disabledChannels.contains(.display),
              !disabledChannels.contains(.inputs) else {
            return false
        }
        return disabledChannels.contains(.smartcard) && disabledChannels.contains(.webdav)
    }

    /// Generates SPICE chardev / CLI flags for disabling channels
    public func generateQEMUChannelFlags() -> [String] {
        var flags: [String] = []
        if disabledChannels.contains(.smartcard) {
            flags.append(contentsOf: ["-global", "spice.smartcard=off"])
        }
        return flags
    }

    /// Generates configure build flags for build-time channel stripping
    public func generateBuildDisableFlags() -> [String] {
        return disabledChannels.map { "--disable-spice-\($0.rawValue)" }
    }
}
