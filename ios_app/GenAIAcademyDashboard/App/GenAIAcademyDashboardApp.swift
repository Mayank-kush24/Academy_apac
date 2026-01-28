//
//  GenAIAcademyDashboardApp.swift
//  GenAIAcademyDashboard
//
//  App entry point
//

import SwiftUI

@main
struct GenAIAcademyDashboardApp: App {
    @StateObject private var authService = AuthService.shared
    
    var body: some Scene {
        WindowGroup {
            Group {
                if authService.isAuthenticated {
                    DashboardView()
                } else {
                    LoginView()
                }
            }
            .environmentObject(authService)
        }
    }
}
