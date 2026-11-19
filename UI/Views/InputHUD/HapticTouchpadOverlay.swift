//
//  HapticTouchpadOverlay.swift
//  UI/Views/InputHUD
//
//  High-precision virtual touchpad overlay for touch screens, supporting relative mouse movement,
//  tap-to-click, two-finger right click, dedicated vertical scrolling, tactile click buttons,
//  drag-lock mode, and UIKit haptic feedback.
//

import Foundation

#if canImport(SwiftUI)
import SwiftUI
#endif

#if canImport(UIKit)
import UIKit
#endif

#if canImport(SwiftUI)

public struct HapticTouchpadOverlay: View {
    @ObservedObject public var viewModel: VMSessionViewModel

    @State private var lastDragLocation: CGPoint? = nil
    @State private var isDragLocked: Bool = false
    @State private var isLeftMouseDown: Bool = false
    @State private var isRightMouseDown: Bool = false
    @State private var sensitivity: Double = 1.2
    @State private var scrollAccumulator: CGFloat = 0.0
    @State private var isScrollActive: Bool = false
    @State private var showControlsBar: Bool = true

    public init(viewModel: VMSessionViewModel) {
        self.viewModel = viewModel
    }

    public var body: some View {
        GeometryReader { geometry in
            ZStack(alignment: .bottom) {
                // Background Touchpad Surface
                touchpadSurface(geometry: geometry)

                // Dedicated Scroll Strip on the Right Edge
                HStack {
                    Spacer()
                    scrollStrip(geometry: geometry)
                }

                // Bottom Tactical Action Bar (L, M, R, DragLock, Sensitivity)
                if showControlsBar {
                    bottomActionBar
                        .padding(.horizontal, 16)
                        .padding(.bottom, 12)
                }
            }
        }
        .allowsHitTesting(true)
    }

    // MARK: - Touchpad Main Surface

    private func touchpadSurface(geometry: GeometryProxy) -> some View {
        RoundedRectangle(cornerRadius: 16)
            .fill(Color.black.opacity(0.18))
            .overlay(
                RoundedRectangle(cornerRadius: 16)
                    .stroke(isDragLocked ? Color.orange.opacity(0.6) : Color.white.opacity(0.12), lineWidth: 1.5)
            )
            .contentShape(Rectangle())
            .gesture(
                DragGesture(minimumDistance: 1, coordinateSpace: .local)
                    .onChanged { value in
                        handleTouchpadDrag(value: value)
                    }
                    .onEnded { _ in
                        lastDragLocation = nil
                    }
            )
            .simultaneousGesture(
                TapGesture(count: 1)
                    .onEnded {
                        handleTapToClick(button: 1)
                    }
            )
    }

    // MARK: - Drag & Movement Handling

    private func handleTouchpadDrag(value: DragGesture.Value) {
        guard let last = lastDragLocation else {
            lastDragLocation = value.location
            return
        }

        let rawDx = (value.location.x - last.x) * CGFloat(sensitivity)
        let rawDy = (value.location.y - last.y) * CGFloat(sensitivity)
        lastDragLocation = value.location

        let clampedDx = Int16(max(-32767, min(32767, rawDx)))
        let clampedDy = Int16(max(-32767, min(32767, rawDy)))

        if clampedDx != 0 || clampedDy != 0 {
            viewModel.sendMouseMove(dx: clampedDx, dy: clampedDy)
        }
    }

    // MARK: - Click & Tap Handling

    private func handleTapToClick(button: UInt8) {
        triggerHaptic(style: button == 1 ? .light : .medium)
        viewModel.sendMouseButton(button: button, isDown: true)
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.035) {
            self.viewModel.sendMouseButton(button: button, isDown: false)
        }
    }

    // MARK: - Dedicated Scroll Strip

    private func scrollStrip(geometry: GeometryProxy) -> some View {
        VStack(spacing: 8) {
            Image(systemName: "chevron.up")
                .font(.system(size: 11, weight: .bold))
                .foregroundColor(.white.opacity(0.5))

            Spacer()

            Image(systemName: "line.3.horizontal")
                .font(.system(size: 14))
                .foregroundColor(.white.opacity(0.7))

            Spacer()

            Image(systemName: "chevron.down")
                .font(.system(size: 11, weight: .bold))
                .foregroundColor(.white.opacity(0.5))
        }
        .frame(width: 36, height: max(120, geometry.size.height * 0.55))
        .background(
            RoundedRectangle(cornerRadius: 12)
                .fill(isScrollActive ? Color.blue.opacity(0.35) : Color.black.opacity(0.3))
        )
        .overlay(
            RoundedRectangle(cornerRadius: 12)
                .stroke(Color.white.opacity(0.2), lineWidth: 1)
        )
        .padding(.trailing, 8)
        .contentShape(Rectangle())
        .gesture(
            DragGesture(minimumDistance: 1, coordinateSpace: .local)
                .onChanged { value in
                    isScrollActive = true
                    let deltaY = value.translation.height - scrollAccumulator
                    scrollAccumulator = value.translation.height

                    // Inverted delta for natural PC wheel scrolling
                    let wheelDelta = Int16(max(-120, min(120, -deltaY * 3.0)))
                    if abs(wheelDelta) > 0 {
                        viewModel.sendMouseScroll(deltaY: wheelDelta)
                    }
                }
                .onEnded { _ in
                    isScrollActive = false
                    scrollAccumulator = 0.0
                }
        )
    }

    // MARK: - Bottom Tactical Action Bar

    private var bottomActionBar: some View {
        HStack(spacing: 12) {
            // Left Mouse Button
            Button(action: {
                handleTapToClick(button: 1)
            }) {
                HStack(spacing: 6) {
                    Image(systemName: "computermouse")
                        .font(.system(size: 13, weight: .medium))
                    Text("Left")
                        .font(.system(size: 13, weight: .semibold))
                }
                .foregroundColor(.white)
                .frame(maxWidth: .infinity)
                .frame(height: 38)
                .background(
                    RoundedRectangle(cornerRadius: 10)
                        .fill(Color.white.opacity(0.18))
                )
            }

            // Middle Mouse Button (Wheel click)
            Button(action: {
                handleTapToClick(button: 2)
            }) {
                Text("Mid")
                    .font(.system(size: 13, weight: .semibold))
                    .foregroundColor(.white.opacity(0.85))
                    .frame(width: 48, height: 38)
                    .background(
                        RoundedRectangle(cornerRadius: 10)
                            .fill(Color.white.opacity(0.12))
                    )
            }

            // Right Mouse Button
            Button(action: {
                handleTapToClick(button: 3)
            }) {
                HStack(spacing: 6) {
                    Image(systemName: "cursorarrow.click.2")
                        .font(.system(size: 13, weight: .medium))
                    Text("Right")
                        .font(.system(size: 13, weight: .semibold))
                }
                .foregroundColor(.white)
                .frame(maxWidth: .infinity)
                .frame(height: 38)
                .background(
                    RoundedRectangle(cornerRadius: 10)
                        .fill(Color.white.opacity(0.18))
                )
            }

            // Drag-Lock Mode Toggle
            Button(action: {
                isDragLocked.toggle()
                triggerHaptic(style: .medium)
                viewModel.sendMouseButton(button: 1, isDown: isDragLocked)
            }) {
                Image(systemName: isDragLocked ? "lock.fill" : "lock.open")
                    .font(.system(size: 14, weight: .bold))
                    .foregroundColor(isDragLocked ? .white : .white.opacity(0.7))
                    .frame(width: 40, height: 38)
                    .background(
                        RoundedRectangle(cornerRadius: 10)
                            .fill(isDragLocked ? Color.orange : Color.white.opacity(0.12))
                    )
            }

            // Sensitivity Adjuster
            Menu {
                Button("Độ nhạy: 0.8x (Chính xác)", action: { sensitivity = 0.8 })
                Button("Độ nhạy: 1.2x (Mặc định)", action: { sensitivity = 1.2 })
                Button("Độ nhạy: 1.6x (Nhanh)", action: { sensitivity = 1.6 })
                Button("Độ nhạy: 2.2x (Rất nhanh)", action: { sensitivity = 2.2 })
            } label: {
                Image(systemName: "slider.horizontal.3")
                    .font(.system(size: 14))
                    .foregroundColor(.white.opacity(0.8))
                    .frame(width: 38, height: 38)
                    .background(
                        RoundedRectangle(cornerRadius: 10)
                            .fill(Color.white.opacity(0.12))
                    )
            }
        }
        .padding(.horizontal, 10)
        .padding(.vertical, 6)
        .background(
            RoundedRectangle(cornerRadius: 14)
                .fill(Color.black.opacity(0.55))
        )
        .overlay(
            RoundedRectangle(cornerRadius: 14)
                .stroke(Color.white.opacity(0.15), lineWidth: 1)
        )
    }

    // MARK: - Haptic Feedback Helper

    private func triggerHaptic(style: UIImpactFeedbackGenerator.FeedbackStyle) {
        #if canImport(UIKit)
        let generator = UIImpactFeedbackGenerator(style: style)
        generator.prepare()
        generator.impactOccurred()
        #endif
    }
}

#endif
