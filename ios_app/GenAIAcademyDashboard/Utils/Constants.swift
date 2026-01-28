//
//  Constants.swift
//  GenAIAcademyDashboard
//
//  Created for Gen AI Academy APAC Dashboard
//

import Foundation

struct Constants {
    // API Configuration
    static let baseURL = "http://localhost:3002/api"  // Change to production URL
    static let loginEndpoint = "/auth/login"
    static let dashboardSummaryEndpoint = "/dashboard/summary"
    static let dashboardChartsEndpoint = "/dashboard/charts"
    static let widgetStatsEndpoint = "/dashboard/widget-stats"
    static let userInfoEndpoint = "/auth/me"
    
    // Keychain
    static let keychainService = "com.genaiacademy.dashboard"
    static let tokenKey = "authToken"
    static let userKey = "userData"
    
    // App Groups (for widget)
    static let appGroupID = "group.com.genaiacademy.dashboard"
}
