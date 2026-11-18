//
//  MetalDisplayView.swift
//  UI/Views
//
//  High-performance SwiftUI UIViewRepresentable wrapper for MTKView delegating framebuffer
//  presentation to MetalDisplayRenderer at up to 120Hz ProMotion.
//

import Foundation

#if canImport(SwiftUI)
import SwiftUI
#endif

#if canImport(MetalKit) && canImport(UIKit)
import MetalKit
import UIKit

public struct MetalDisplayView: UIViewRepresentable {
    public let renderer: MetalDisplayRenderer

    public init(renderer: MetalDisplayRenderer) {
        self.renderer = renderer
    }

    public func makeCoordinator() -> Coordinator {
        Coordinator(renderer: renderer)
    }

    public func makeUIView(context: Context) -> MTKView {
        let mtkView = MTKView(frame: .zero)
        mtkView.device = MTLCreateSystemDefaultDevice()
        mtkView.colorPixelFormat = .bgra8Unorm
        mtkView.clearColor = MTLClearColor(red: 0.0, green: 0.0, blue: 0.0, alpha: 1.0)
        mtkView.preferredFramesPerSecond = renderer.viewport.refreshRateHz
        mtkView.enableSetNeedsDisplay = false
        mtkView.isPaused = false
        mtkView.delegate = context.coordinator
        mtkView.contentMode = .scaleAspectFit
        return mtkView
    }

    public func updateUIView(_ uiView: MTKView, context: Context) {
        if uiView.preferredFramesPerSecond != renderer.viewport.refreshRateHz {
            uiView.preferredFramesPerSecond = renderer.viewport.refreshRateHz
        }
    }

    public final class Coordinator: NSObject, MTKViewDelegate {
        private let renderer: MetalDisplayRenderer

        public init(renderer: MetalDisplayRenderer) {
            self.renderer = renderer
            super.init()
        }

        public func mtkView(_ view: MTKView, drawableSizeWillChange size: CGSize) {
            let width = Int(size.width)
            let height = Int(size.height)
            if width > 0 && height > 0 {
                renderer.resizeViewport(width: width, height: height)
            }
        }

        public func draw(in view: MTKView) {
            guard let drawable = view.currentDrawable else { return }
            renderer.render(to: drawable)
        }
    }
}

#elseif canImport(SwiftUI)

public struct MetalDisplayView: View {
    public let renderer: MetalDisplayRenderer

    public init(renderer: MetalDisplayRenderer) {
        self.renderer = renderer
    }

    public var body: some View {
        ZStack {
            Color.black
            Text("Metal display simulator view (\(renderer.viewport.width)x\(renderer.viewport.height) @ \(renderer.viewport.refreshRateHz)Hz)")
                .foregroundColor(.white.opacity(0.6))
                .font(.footnote)
        }
    }
}

#endif
