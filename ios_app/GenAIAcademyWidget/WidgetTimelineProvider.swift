//
//  WidgetTimelineProvider.swift
//  GenAIAcademyWidget
//
//  Timeline provider for widget data fetching
//

import WidgetKit
import Foundation

struct WidgetTimelineProvider: TimelineProvider {
    typealias Entry = WidgetEntry
    
    func placeholder(in context: Context) -> WidgetEntry {
        WidgetEntry(
            date: Date(),
            stats: WidgetStats(
                totalUsers: 1234,
                todaySignups: 45,
                activeUsers: 890,
                lastUpdated: Date().ISO8601Format()
            )
        )
    }
    
    func getSnapshot(in context: Context, completion: @escaping (WidgetEntry) -> Void) {
        let entry = placeholder(in: context)
        completion(entry)
    }
    
    func getTimeline(in context: Context, completion: @escaping (Timeline<WidgetEntry>) -> Void) {
        // Fetch data from API
        Task {
            let stats = await fetchWidgetStats()
            let entry = WidgetEntry(date: Date(), stats: stats)
            
            // Refresh every 30 minutes
            let nextUpdate = Calendar.current.date(byAdding: .minute, value: 30, to: Date())!
            let timeline = Timeline(entries: [entry], policy: .after(nextUpdate))
            
            completion(timeline)
        }
    }
    
    private func fetchWidgetStats() async -> WidgetStats {
        // Get token from shared App Group
        guard let token = getStoredToken() else {
            return defaultStats()
        }
        
        // Use same base URL as main app
        let baseURL = "http://localhost:3002/api"  // Update to match Constants.swift
        guard let url = URL(string: "\(baseURL)/dashboard/widget-stats") else {
            return defaultStats()
        }
        
        var request = URLRequest(url: url)
        request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        
        do {
            let (data, _) = try await URLSession.shared.data(for: request)
            let decoder = JSONDecoder()
            decoder.keyDecodingStrategy = .convertFromSnakeCase
            return try decoder.decode(WidgetStats.self, from: data)
        } catch {
            // Return cached data or default
            return getCachedStats() ?? defaultStats()
        }
    }
    
    private func getStoredToken() -> String? {
        // Read from App Group shared container
        let appGroupID = "group.com.genaiacademy.dashboard"
        guard let sharedDefaults = UserDefaults(suiteName: appGroupID) else {
            return nil
        }
        return sharedDefaults.string(forKey: "authToken")
    }
    
    private func getCachedStats() -> WidgetStats? {
        let appGroupID = "group.com.genaiacademy.dashboard"
        guard let sharedDefaults = UserDefaults(suiteName: appGroupID),
              let data = sharedDefaults.data(forKey: "widgetStats"),
              let stats = try? JSONDecoder().decode(WidgetStats.self, from: data) else {
            return nil
        }
        return stats
    }
    
    private func defaultStats() -> WidgetStats {
        let formatter = ISO8601DateFormatter()
        return WidgetStats(
            totalUsers: 0,
            todaySignups: 0,
            activeUsers: 0,
            lastUpdated: formatter.string(from: Date())
        )
    }
}

struct WidgetEntry: TimelineEntry {
    let date: Date
    let stats: WidgetStats
}
