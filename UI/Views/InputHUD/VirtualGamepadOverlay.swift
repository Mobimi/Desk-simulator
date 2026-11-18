//
//  VirtualGamepadOverlay.swift
//  UI/Views/InputHUD
//
//  On-screen virtual gamepad overlay for touch screens, providing dual analog thumbsticks
//  with deadzone filtering & spring-back, D-Pad, ABXY diamond cluster, shoulder triggers/bumpers,
//  Select/Start system buttons, opacity control, and layout editing mode.
//

import Foundation

#if canImport(SwiftUI)
import SwiftUI
#endif

#if canImport(UIKit)
import UIKit
#endif

/// Standard virtual gamepad button mapping definitions.
public enum GamepadButtonID: UInt8, CaseIterable {
    case a          = 0
    case b          = 1
    case x          = 2
    case y          = 3
    case lb         = 4
    case rb         = 5
    case lt         = 6
    case rt         = 7
    case selectBack = 8
    case startMenu  = 9
    case l3         = 10
    case r3         = 11
    case dpadUp     = 12
    case dpadDown   = 13
    case dpadLeft   = 14
    case dpadRight  = 15
}

#if canImport(SwiftUI)

public struct VirtualGamepadOverlay: View {
    @ObservedObject public var viewModel: VMSessionViewModel

    // Thumbstick states
    @State private var leftStickDrag: CGSize = .zero
    @State private var rightStickDrag: CGSize = .zero

    // Active pressed button tracking for visual highlight
    @State private var activeButtons: Set<UInt8> = []

    // Custom layout positions when isEditingGamepadLayout is enabled
    @State private var leftClusterOffset: CGSize = .zero
    @State private var rightClusterOffset: CGSize = .zero

    private let maxTravel: CGFloat = 40.0
    private let deadzone: Float = 0.08

    public init(viewModel: VMSessionViewModel) {
        self.viewModel = viewModel
    }

    public var body: some View {
        GeometryReader { geometry in
            ZStack {
                // Top Shoulder Bumpers & Triggers (LB, LT, RB, RT)
                VStack {
                    topShouldersRow
                        .padding(.horizontal, 24)
                        .padding(.top, 12)
                    Spacer()
                }

                // Center Select / Start Navigation Bar
                VStack {
                    Spacer().frame(height: 18)
                    centerSystemRow
                    Spacer()
                }

                // Bottom Left: D-Pad & Left Analog Thumbstick
                VStack {
                    Spacer()
                    HStack(alignment: .bottom, spacing: 28) {
                        dpadCluster
                        analogStick(
                            stickId: 0,
                            stickOffset: $leftStickDrag,
                            l3r3ButtonId: GamepadButtonID.l3.rawValue,
                            label: "L3"
                        )
                        Spacer()
                    }
                    .padding(.leading, 20)
                    .padding(.bottom, 24)
                    .offset(leftClusterOffset)
                    .gesture(
                        viewModel.isEditingGamepadLayout ?
                        DragGesture().onChanged { value in
                            leftClusterOffset = value.translation
                        } : nil
                    )
                }

                // Bottom Right: Right Analog Thumbstick & ABXY Action Diamond
                VStack {
                    Spacer()
                    HStack(alignment: .bottom, spacing: 28) {
                        Spacer()
                        analogStick(
                            stickId: 1,
                            stickOffset: $rightStickDrag,
                            l3r3ButtonId: GamepadButtonID.r3.rawValue,
                            label: "R3"
                        )
                        abxyCluster
                    }
                    .padding(.trailing, 20)
                    .padding(.bottom, 24)
                    .offset(rightClusterOffset)
                    .gesture(
                        viewModel.isEditingGamepadLayout ?
                        DragGesture().onChanged { value in
                            rightClusterOffset = value.translation
                        } : nil
                    )
                }

                // Layout Edit Mode Indicator Banner
                if viewModel.isEditingGamepadLayout {
                    VStack {
                        Spacer()
                        HStack {
                            Image(systemName: "hand.draw.fill")
                            Text("Chế độ chỉnh sửa vị trí nút: Kéo để di chuyển cụm nút")
                                .font(.system(size: 13, weight: .medium))
                            Button("Xong") {
                                viewModel.isEditingGamepadLayout = false
                            }
                            .font(.system(size: 13, weight: .bold))
                            .padding(.horizontal, 10)
                            .padding(.vertical, 4)
                            .background(Capsule().fill(Color.blue))
                        }
                        .foregroundColor(.white)
                        .padding(.horizontal, 16)
                        .padding(.vertical, 8)
                        .background(Capsule().fill(Color.black.opacity(0.8)))
                        .padding(.bottom, 12)
                    }
                }
            }
            .opacity(viewModel.gamepadOpacity)
        }
        .allowsHitTesting(true)
    }

    // MARK: - Top Shoulder Bumpers & Triggers (LB, LT, RB, RT)

    private var topShouldersRow: some View {
        HStack {
            // Left Shoulders
            HStack(spacing: 8) {
                shoulderButton(label: "LT", id: GamepadButtonID.lt.rawValue, width: 56)
                shoulderButton(label: "LB", id: GamepadButtonID.lb.rawValue, width: 52)
            }

            Spacer()

            // Right Shoulders
            HStack(spacing: 8) {
                shoulderButton(label: "RB", id: GamepadButtonID.rb.rawValue, width: 52)
                shoulderButton(label: "RT", id: GamepadButtonID.rt.rawValue, width: 56)
            }
        }
    }

    private func shoulderButton(label: String, id: UInt8, width: CGFloat) -> some View {
        let isPressed = activeButtons.contains(id)
        return Text(label)
            .font(.system(size: 13, weight: .bold))
            .foregroundColor(isPressed ? .black : .white)
            .frame(width: width, height: 34)
            .background(
                RoundedRectangle(cornerRadius: 10)
                    .fill(isPressed ? Color.white : Color.white.opacity(0.22))
            )
            .overlay(
                RoundedRectangle(cornerRadius: 10)
                    .stroke(Color.white.opacity(0.3), lineWidth: 1)
            )
            .contentShape(Rectangle())
            .gesture(
                DragGesture(minimumDistance: 0)
                    .onChanged { _ in
                        if !activeButtons.contains(id) {
                            pressButton(id: id)
                        }
                    }
                    .onEnded { _ in
                        releaseButton(id: id)
                    }
            )
    }

    // MARK: - Center System Buttons (Select/Back, Start/Menu)

    private var centerSystemRow: some View {
        HStack(spacing: 36) {
            systemButton(label: "SELECT", id: GamepadButtonID.selectBack.rawValue)
            systemButton(label: "START", id: GamepadButtonID.startMenu.rawValue)
        }
    }

    private func systemButton(label: String, id: UInt8) -> some View {
        let isPressed = activeButtons.contains(id)
        return Text(label)
            .font(.system(size: 10, weight: .bold))
            .foregroundColor(isPressed ? .black : .white.opacity(0.85))
            .padding(.horizontal, 10)
            .frame(height: 24)
            .background(
                Capsule().fill(isPressed ? Color.white : Color.white.opacity(0.18))
            )
            .overlay(
                Capsule().stroke(Color.white.opacity(0.25), lineWidth: 1)
            )
            .gesture(
                DragGesture(minimumDistance: 0)
                    .onChanged { _ in
                        if !activeButtons.contains(id) {
                            pressButton(id: id)
                        }
                    }
                    .onEnded { _ in
                        releaseButton(id: id)
                    }
            )
    }

    // MARK: - D-Pad Cross

    private var dpadCluster: some View {
        ZStack {
            // Background Cross
            RoundedRectangle(cornerRadius: 12)
                .fill(Color.white.opacity(0.12))
                .frame(width: 42, height: 120)

            RoundedRectangle(cornerRadius: 12)
                .fill(Color.white.opacity(0.12))
                .frame(width: 120, height: 42)

            // Up
            dpadDirectionButton(systemName: "arrowtriangle.up.fill", id: GamepadButtonID.dpadUp.rawValue)
                .offset(y: -40)

            // Down
            dpadDirectionButton(systemName: "arrowtriangle.down.fill", id: GamepadButtonID.dpadDown.rawValue)
                .offset(y: 40)

            // Left
            dpadDirectionButton(systemName: "arrowtriangle.left.fill", id: GamepadButtonID.dpadLeft.rawValue)
                .offset(x: -40)

            // Right
            dpadDirectionButton(systemName: "arrowtriangle.right.fill", id: GamepadButtonID.dpadRight.rawValue)
                .offset(x: 40)

            // Center pivot
            Circle()
                .fill(Color.black.opacity(0.4))
                .frame(width: 24, height: 24)
        }
        .frame(width: 120, height: 120)
    }

    private func dpadDirectionButton(systemName: String, id: UInt8) -> some View {
        let isPressed = activeButtons.contains(id)
        return Image(systemName: systemName)
            .font(.system(size: 15, weight: .bold))
            .foregroundColor(isPressed ? .yellow : .white)
            .frame(width: 38, height: 38)
            .background(
                Circle().fill(isPressed ? Color.white.opacity(0.35) : Color.clear)
            )
            .contentShape(Circle())
            .gesture(
                DragGesture(minimumDistance: 0)
                    .onChanged { _ in
                        if !activeButtons.contains(id) {
                            pressButton(id: id)
                        }
                    }
                    .onEnded { _ in
                        releaseButton(id: id)
                    }
            )
    }

    // MARK: - Analog Thumbstick

    private func analogStick(
        stickId: UInt8,
        stickOffset: Binding<CGSize>,
        l3r3ButtonId: UInt8,
        label: String
    ) -> some View {
        ZStack {
            // Base Circle Ring
            Circle()
                .fill(Color.white.opacity(0.10))
                .frame(width: 110, height: 110)
                .overlay(
                    Circle().stroke(Color.white.opacity(0.25), lineWidth: 1.5)
                )

            // Moving Joystick Knob
            ZStack {
                Circle()
                    .fill(Color.white.opacity(0.32))
                    .frame(width: 54, height: 54)
                    .overlay(
                        Circle().stroke(Color.white.opacity(0.4), lineWidth: 1.5)
                    )

                Text(label)
                    .font(.system(size: 11, weight: .bold))
                    .foregroundColor(.white.opacity(0.75))
            }
            .offset(stickOffset.wrappedValue)
            .gesture(
                DragGesture(minimumDistance: 0)
                    .onChanged { value in
                        handleStickDrag(
                            translation: value.translation,
                            stickId: stickId,
                            stickOffset: stickOffset
                        )
                    }
                    .onEnded { _ in
                        withAnimation(.spring(response: 0.2, dampingFraction: 0.6)) {
                            stickOffset.wrappedValue = .zero
                        }
                        viewModel.sendGamepadStick(stickId: stickId, x: 0.0, y: 0.0)
                    }
            )
            .simultaneousGesture(
                TapGesture(count: 2)
                    .onEnded {
                        // Double tap knob triggers L3 / R3 click
                        pressButton(id: l3r3ButtonId)
                        DispatchQueue.main.asyncAfter(deadline: .now() + 0.1) {
                            self.releaseButton(id: l3r3ButtonId)
                        }
                    }
            )
        }
        .frame(width: 110, height: 110)
    }

    private func handleStickDrag(
        translation: CGSize,
        stickId: UInt8,
        stickOffset: Binding<CGSize>
    ) {
        let distance = hypot(translation.width, translation.height)
        var clampedOffset = translation
        if distance > maxTravel {
            let angle = atan2(translation.height, translation.width)
            clampedOffset = CGSize(
                width: cos(angle) * maxTravel,
                height: sin(angle) * maxTravel
            )
        }
        stickOffset.wrappedValue = clampedOffset

        // Normalized [-1.0, 1.0], Y inverted for standard PC controller coordinate system
        var normX = Float(clampedOffset.width / maxTravel)
        var normY = Float(-clampedOffset.height / maxTravel)

        // Deadzone filtering
        if abs(normX) < deadzone { normX = 0.0 }
        if abs(normY) < deadzone { normY = 0.0 }

        viewModel.sendGamepadStick(stickId: stickId, x: normX, y: normY)
    }

    // MARK: - ABXY Diamond Cluster

    private var abxyCluster: some View {
        ZStack {
            // Y (Yellow) - Top
            abxyButton(label: "Y", id: GamepadButtonID.y.rawValue, color: Color.yellow)
                .offset(y: -42)

            // A (Green) - Bottom
            abxyButton(label: "A", id: GamepadButtonID.a.rawValue, color: Color.green)
                .offset(y: 42)

            // X (Blue) - Left
            abxyButton(label: "X", id: GamepadButtonID.x.rawValue, color: Color.blue)
                .offset(x: -42)

            // B (Red) - Right
            abxyButton(label: "B", id: GamepadButtonID.b.rawValue, color: Color.red)
                .offset(x: 42)
        }
        .frame(width: 120, height: 120)
    }

    private func abxyButton(label: String, id: UInt8, color: Color) -> some View {
        let isPressed = activeButtons.contains(id)
        return Text(label)
            .font(.system(size: 16, weight: .bold))
            .foregroundColor(isPressed ? .black : color)
            .frame(width: 38, height: 38)
            .background(
                Circle().fill(isPressed ? color : Color.white.opacity(0.18))
            )
            .overlay(
                Circle().stroke(color.opacity(0.6), lineWidth: 1.5)
            )
            .contentShape(Circle())
            .gesture(
                DragGesture(minimumDistance: 0)
                    .onChanged { _ in
                        if !activeButtons.contains(id) {
                            pressButton(id: id)
                        }
                    }
                    .onEnded { _ in
                        releaseButton(id: id)
                    }
            )
    }

    // MARK: - Event Dispatch & Haptics

    private func pressButton(id: UInt8) {
        activeButtons.insert(id)
        triggerHaptic()
        viewModel.sendGamepadButton(id: id, isPressed: true)
    }

    private func releaseButton(id: UInt8) {
        activeButtons.remove(id)
        viewModel.sendGamepadButton(id: id, isPressed: false)
    }

    private func triggerHaptic() {
        #if canImport(UIKit)
        let generator = UIImpactFeedbackGenerator(style: .medium)
        generator.prepare()
        generator.impactOccurred()
        #endif
    }
}

#endif
