//
//  PCShortcutToolbar.swift
//  UI/Views/InputHUD
//
//  Floating quick-access PC toolbar providing essential desktop keyboard keys (Esc, Tab, Ctrl,
//  Alt, Win, Del, F1-F12), modifier key latching, one-tap combination shortcuts (Ctrl+Alt+Del,
//  Alt+F4, Win+D, Win+E), and virtual keyboard toggle.
//

import Foundation

#if canImport(SwiftUI)
import SwiftUI
#endif

#if canImport(UIKit)
import UIKit
#endif

/// Standard IBM PC/AT Scancode Set 1 definitions for guest OS input forwarding.
public enum PCKeyScancode: UInt16, CaseIterable {
    case escape    = 0x0001
    case tab       = 0x000F
    case enter     = 0x001C
    case leftCtrl  = 0x001D
    case leftAlt   = 0x0038
    case space     = 0x0039
    case backspace = 0x000E
    case delete    = 0xE053
    case leftWin   = 0xE05B

    // Arrow navigation
    case up        = 0xE048
    case down      = 0xE050
    case left      = 0xE04B
    case right     = 0xE04D

    // Function keys (F1-F12)
    case f1        = 0x003B
    case f2        = 0x003C
    case f3        = 0x003D
    case f4        = 0x003E
    case f5        = 0x003F
    case f6        = 0x0040
    case f7        = 0x0041
    case f8        = 0x0042
    case f9        = 0x0043
    case f10       = 0x0044
    case f11       = 0x0057
    case f12       = 0x0058
}

#if canImport(SwiftUI)

public struct PCShortcutToolbar: View {
    @ObservedObject public var viewModel: VMSessionViewModel

    @State private var isExpanded: Bool = true
    @State private var showFunctionKeys: Bool = false
    @State private var showCombosSheet: Bool = false

    public init(viewModel: VMSessionViewModel) {
        self.viewModel = viewModel
    }

    public var body: some View {
        VStack(spacing: 6) {
            // Optional Expandable Function Keys Strip (F1-F12)
            if showFunctionKeys && isExpanded {
                functionKeysStrip
                    .transition(.move(edge: .bottom).combined(with: .opacity))
            }

            // Main Primary Shortcut Toolbar
            mainToolbar
        }
        .padding(.horizontal, 8)
        .animation(.easeInOut(duration: 0.2), value: showFunctionKeys)
        .animation(.easeInOut(duration: 0.2), value: isExpanded)
    }

    // MARK: - Main Toolbar

    private var mainToolbar: some View {
        HStack(spacing: 6) {
            // Collapse / Expand toggle
            Button(action: {
                triggerHaptic()
                isExpanded.toggle()
            }) {
                Image(systemName: isExpanded ? "chevron.down" : "keyboard")
                    .font(.system(size: 13, weight: .bold))
                    .foregroundColor(.white.opacity(0.8))
                    .frame(width: 32, height: 36)
                    .background(
                        RoundedRectangle(cornerRadius: 8)
                            .fill(Color.white.opacity(0.12))
                    )
            }

            if isExpanded {
                // Esc key
                keyButton(label: "Esc", scancode: PCKeyScancode.escape.rawValue)

                // Tab key
                keyButton(label: "Tab", scancode: PCKeyScancode.tab.rawValue)

                // Ctrl (Modifier Latching)
                modifierButton(
                    label: "Ctrl",
                    isActive: viewModel.ctrlHeld,
                    scancode: PCKeyScancode.leftCtrl.rawValue
                ) {
                    viewModel.ctrlHeld.toggle()
                    viewModel.sendKeyScancode(PCKeyScancode.leftCtrl.rawValue, isDown: viewModel.ctrlHeld)
                }

                // Alt (Modifier Latching)
                modifierButton(
                    label: "Alt",
                    isActive: viewModel.altHeld,
                    scancode: PCKeyScancode.leftAlt.rawValue
                ) {
                    viewModel.altHeld.toggle()
                    viewModel.sendKeyScancode(PCKeyScancode.leftAlt.rawValue, isDown: viewModel.altHeld)
                }

                // Win (Modifier Latching)
                modifierButton(
                    label: "Win",
                    isActive: viewModel.winHeld,
                    scancode: PCKeyScancode.leftWin.rawValue
                ) {
                    viewModel.winHeld.toggle()
                    viewModel.sendKeyScancode(PCKeyScancode.leftWin.rawValue, isDown: viewModel.winHeld)
                }

                // Del key
                keyButton(label: "Del", scancode: PCKeyScancode.delete.rawValue)

                // F1-F12 Drawer Toggle
                Button(action: {
                    triggerHaptic()
                    showFunctionKeys.toggle()
                }) {
                    Text("Fn")
                        .font(.system(size: 12, weight: .bold))
                        .foregroundColor(showFunctionKeys ? .white : .white.opacity(0.85))
                        .frame(width: 34, height: 36)
                        .background(
                            RoundedRectangle(cornerRadius: 8)
                                .fill(showFunctionKeys ? Color.blue : Color.white.opacity(0.15))
                        )
                }

                // Quick Combos Menu
                combosMenu

                // Virtual iOS Keyboard Toggle
                Button(action: {
                    triggerHaptic()
                    viewModel.isSystemKeyboardVisible.toggle()
                }) {
                    Image(systemName: viewModel.isSystemKeyboardVisible ? "keyboard.chevron.compact.down" : "keyboard.fill")
                        .font(.system(size: 14))
                        .foregroundColor(viewModel.isSystemKeyboardVisible ? .cyan : .white.opacity(0.9))
                        .frame(width: 36, height: 36)
                        .background(
                            RoundedRectangle(cornerRadius: 8)
                                .fill(viewModel.isSystemKeyboardVisible ? Color.cyan.opacity(0.25) : Color.white.opacity(0.15))
                        )
                }
            }
        }
        .padding(.horizontal, 8)
        .padding(.vertical, 5)
        .background(
            RoundedRectangle(cornerRadius: 12)
                .fill(Color.black.opacity(0.65))
        )
        .overlay(
            RoundedRectangle(cornerRadius: 12)
                .stroke(Color.white.opacity(0.2), lineWidth: 1)
        )
    }

    // MARK: - Function Keys Strip (F1-F12)

    private var functionKeysStrip: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 5) {
                ForEach(1...12, id: \.self) { num in
                    let scancode = functionKeyScancode(for: num)
                    Button(action: {
                        triggerHaptic()
                        viewModel.tapPCShortcut(scancodes: [scancode])
                    }) {
                        Text("F\(num)")
                            .font(.system(size: 11, weight: .semibold))
                            .foregroundColor(.white)
                            .frame(width: 34, height: 30)
                            .background(
                                RoundedRectangle(cornerRadius: 6)
                                    .fill(Color.white.opacity(0.18))
                            )
                    }
                }
            }
            .padding(.horizontal, 8)
            .padding(.vertical, 4)
            .background(
                RoundedRectangle(cornerRadius: 10)
                    .fill(Color.black.opacity(0.7))
            )
            .overlay(
                RoundedRectangle(cornerRadius: 10)
                    .stroke(Color.white.opacity(0.15), lineWidth: 1)
            )
        }
    }

    // MARK: - Combos Menu

    private var combosMenu: some View {
        Menu {
            Button("Ctrl + Alt + Del (Bảo mật / Taskmgr)") {
                triggerHaptic()
                viewModel.tapPCShortcut(scancodes: [0x001D, 0x0038, 0xE053])
            }
            Button("Alt + F4 (Đóng ứng dụng)") {
                triggerHaptic()
                viewModel.tapPCShortcut(scancodes: [0x0038, 0x003E])
            }
            Button("Win + D (Hiện / Ẩn Desktop)") {
                triggerHaptic()
                viewModel.tapPCShortcut(scancodes: [0xE05B, 0x0020])
            }
            Button("Win + E (Mở File Explorer)") {
                triggerHaptic()
                viewModel.tapPCShortcut(scancodes: [0xE05B, 0x0012])
            }
            Button("Alt + Tab (Chuyển cửa sổ)") {
                triggerHaptic()
                viewModel.tapPCShortcut(scancodes: [0x0038, 0x000F])
            }
            Button("Win + R (Hộp thoại Run)") {
                triggerHaptic()
                viewModel.tapPCShortcut(scancodes: [0xE05B, 0x0013])
            }
        } label: {
            HStack(spacing: 3) {
                Image(systemName: "command")
                    .font(.system(size: 11, weight: .bold))
                Text("Combo")
                    .font(.system(size: 11, weight: .semibold))
            }
            .foregroundColor(.white.opacity(0.9))
            .frame(height: 36)
            .padding(.horizontal, 7)
            .background(
                RoundedRectangle(cornerRadius: 8)
                    .fill(Color.purple.opacity(0.35))
            )
            .overlay(
                RoundedRectangle(cornerRadius: 8)
                    .stroke(Color.purple.opacity(0.5), lineWidth: 1)
            )
        }
    }

    // MARK: - Reusable Key Buttons

    private func keyButton(label: String, scancode: UInt16) -> some View {
        Button(action: {
            triggerHaptic()
            viewModel.tapPCShortcut(scancodes: [scancode])
        }) {
            Text(label)
                .font(.system(size: 12, weight: .semibold))
                .foregroundColor(.white)
                .frame(minWidth: 32, minHeight: 36)
                .padding(.horizontal, 4)
                .background(
                    RoundedRectangle(cornerRadius: 8)
                        .fill(Color.white.opacity(0.18))
                )
        }
    }

    private func modifierButton(
        label: String,
        isActive: Bool,
        scancode: UInt16,
        toggleAction: @escaping () -> Void
    ) -> some View {
        Button(action: {
            triggerHaptic(style: .medium)
            toggleAction()
        }) {
            Text(label)
                .font(.system(size: 12, weight: .bold))
                .foregroundColor(isActive ? .black : .white)
                .frame(minWidth: 34, minHeight: 36)
                .padding(.horizontal, 4)
                .background(
                    RoundedRectangle(cornerRadius: 8)
                        .fill(isActive ? Color.yellow : Color.white.opacity(0.18))
                )
        }
    }

    // MARK: - Helpers

    private func functionKeyScancode(for num: Int) -> UInt16 {
        switch num {
        case 1:  return PCKeyScancode.f1.rawValue
        case 2:  return PCKeyScancode.f2.rawValue
        case 3:  return PCKeyScancode.f3.rawValue
        case 4:  return PCKeyScancode.f4.rawValue
        case 5:  return PCKeyScancode.f5.rawValue
        case 6:  return PCKeyScancode.f6.rawValue
        case 7:  return PCKeyScancode.f7.rawValue
        case 8:  return PCKeyScancode.f8.rawValue
        case 9:  return PCKeyScancode.f9.rawValue
        case 10: return PCKeyScancode.f10.rawValue
        case 11: return PCKeyScancode.f11.rawValue
        case 12: return PCKeyScancode.f12.rawValue
        default: return PCKeyScancode.f1.rawValue
        }
    }

    private func triggerHaptic(style: UIImpactFeedbackStyle = .light) {
        #if canImport(UIKit)
        let generator = UIImpactFeedbackGenerator(style: style)
        generator.prepare()
        generator.impactOccurred()
        #endif
    }
}

#endif
