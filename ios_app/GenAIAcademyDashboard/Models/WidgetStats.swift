//
//  WidgetStats.swift
//  GenAIAcademyDashboard
//
//  Widget statistics model for iOS Home Screen Widget
//

import Foundation

struct WidgetStats: Codable {
    let totalUsers: Int
    let todaySignups: Int
    let activeUsers: Int
    let lastUpdated: String
    
    enum CodingKeys: String, CodingKey {
        case totalUsers = "total_users"
        case todaySignups = "today_signups"
        case activeUsers = "active_users"
        case lastUpdated = "last_updated"
    }
}
