//
//  MetalDisplayRenderer.swift
//  Desk-simulator Engine Layer
//
//  Metal rendering pipeline interface for SPICE display framebuffers.
//

import Foundation

#if canImport(Metal)
import Metal
import QuartzCore
#endif

public struct DisplayViewport {
    public var width: Int
    public var height: Int
    public var scaleFactor: Double
    public var refreshRateHz: Int

    public init(width: Int = 1920, height: Int = 1080, scaleFactor: Double = 2.0, refreshRateHz: Int = 60) {
        self.width = width
        self.height = height
        self.scaleFactor = scaleFactor
        self.refreshRateHz = refreshRateHz
    }
}

public protocol MetalDisplayRendererProtocol: AnyObject {
    var viewport: DisplayViewport { get set }
    var isReadyForRendering: Bool { get }

    func updateFramebuffer(with data: Data, width: Int, height: Int, stride: Int)
    func resizeViewport(width: Int, height: Int)
    func drawFrame()
}

public final class MetalDisplayRenderer: MetalDisplayRendererProtocol {
    public var viewport: DisplayViewport
    public private(set) var isReadyForRendering: Bool = false
    public private(set) var currentFrameCount: UInt64 = 0

    private var currentFramebufferData: Data?
    private let renderQueue = DispatchQueue(label: "com.mobimi.desk.spice.renderer", qos: .userInteractive)

    #if canImport(Metal)
    private var device: MTLDevice?
    private var commandQueue: MTLCommandQueue?
    private var currentTexture: MTLTexture?
    #endif

    public init(initialViewport: DisplayViewport = DisplayViewport()) {
        self.viewport = initialViewport
        #if canImport(Metal)
        self.device = MTLCreateSystemDefaultDevice()
        if let dev = self.device {
            self.commandQueue = dev.makeCommandQueue()
            self.isReadyForRendering = (self.commandQueue != nil)
        } else {
            self.isReadyForRendering = false
        }
        #else
        self.isReadyForRendering = true
        #endif
    }

    /// Ingests SPICE display frame data into the rendering pipeline.
    public func updateFramebuffer(with data: Data, width: Int, height: Int, stride: Int) {
        renderQueue.async { [weak self] in
            guard let self = self else { return }
            self.currentFramebufferData = data
            self.viewport.width = width
            self.viewport.height = height
            self.drawFrame()
        }
    }

    /// Resizes the display viewport dynamically based on orientation or window size.
    public func resizeViewport(width: Int, height: Int) {
        viewport.width = width
        viewport.height = height
    }

    /// Executes render pass for the latest display framebuffer.
    public func drawFrame() {
        guard isReadyForRendering, let data = currentFramebufferData else { return }

        #if canImport(Metal)
        guard let device = self.device, let commandQueue = self.commandQueue else { return }
        let descriptor = MTLTextureDescriptor.texture2DDescriptor(
            pixelFormat: .bgra8Unorm,
            width: max(1, viewport.width),
            height: max(1, viewport.height),
            mipmapped: false
        )
        if currentTexture == nil || currentTexture?.width != viewport.width || currentTexture?.height != viewport.height {
            currentTexture = device.makeTexture(descriptor: descriptor)
        }
        if let texture = currentTexture {
            let bytesPerRow = viewport.width * 4
            let region = MTLRegionMake2D(0, 0, viewport.width, viewport.height)
            data.withUnsafeBytes { raw in
                if let base = raw.baseAddress, data.count >= bytesPerRow * viewport.height {
                    texture.replace(region: region, mipmapLevel: 0, withBytes: base, bytesPerRow: bytesPerRow)
                }
            }
            if let commandBuffer = commandQueue.makeCommandBuffer() {
                commandBuffer.commit()
            }
        }
        #endif

        currentFrameCount += 1
    }
}
