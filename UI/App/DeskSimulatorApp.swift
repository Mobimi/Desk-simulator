//
//  DeskSimulatorApp.swift
//  UI/App
//
//  Main SwiftUI entry point for Desk Simulator on iOS (120Hz ProMotion ready).
//

import SwiftUI

@main
public struct DeskSimulatorApp: App {
    @StateObject private var homeViewModel = HomeViewModel()

    public init() {}

    public var body: some Scene {
        WindowGroup {
            HomeView(viewModel: homeViewModel)
                .preferredColorScheme(.dark)
                .onOpenURL { url in
                    homeViewModel.handleIncomingURL(url)
                }
        }
    }
}
