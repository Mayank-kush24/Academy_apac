//
//  WidgetView.swift
//  GenAIAcademyWidget
//
//  Widget view for iOS Home Screen
//

import WidgetKit
import SwiftUI

struct GenAIAcademyWidgetEntryView: View {
    var entry: WidgetTimelineProvider.Entry
    @Environment(\.widgetFamily) var family
    
    var body: some View {
        switch family {
        case .systemSmall:
            SmallWidgetView(stats: entry.stats)
        case .systemMedium:
            MediumWidgetView(stats: entry.stats)
        default:
            SmallWidgetView(stats: entry.stats)
        }
    }
}

// MARK: - Small Widget
struct SmallWidgetView: View {
    let stats: WidgetStats
    
    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                Image(systemName: "chart.bar.fill")
                    .foregroundStyle(
                        LinearGradient(
                            colors: [.blue, .purple],
                            startPoint: .topLeading,
                            endPoint: .bottomTrailing
                        )
                    )
                Spacer()
            }
            
            VStack(alignment: .leading, spacing: 4) {
                Text("Total Users")
                    .font(.system(size: 12, weight: .medium))
                    .foregroundColor(.secondary)
                
                Text("\(stats.totalUsers)")
                    .font(.system(size: 28, weight: .bold, design: .rounded))
                    .foregroundColor(.primary)
            }
            
            HStack(spacing: 16) {
                VStack(alignment: .leading, spacing: 2) {
                    Text("Today")
                        .font(.system(size: 10))
                        .foregroundColor(.secondary)
                    Text("\(stats.todaySignups)")
                        .font(.system(size: 16, weight: .semibold))
                }
                
                VStack(alignment: .leading, spacing: 2) {
                    Text("Active")
                        .font(.system(size: 10))
                        .foregroundColor(.secondary)
                    Text("\(stats.activeUsers)")
                        .font(.system(size: 16, weight: .semibold))
                }
            }
            
            Spacer()
        }
        .padding()
        .background(
            LinearGradient(
                colors: [
                    Color(red: 0.95, green: 0.97, blue: 1.0),
                    Color(red: 0.98, green: 0.99, blue: 1.0)
                ],
                startPoint: .topLeading,
                endPoint: .bottomTrailing
            )
        )
    }
}

// MARK: - Medium Widget
struct MediumWidgetView: View {
    let stats: WidgetStats
    
    var body: some View {
        HStack(spacing: 20) {
            // Left side - Total Users
            VStack(alignment: .leading, spacing: 8) {
                HStack {
                    Image(systemName: "chart.bar.fill")
                        .foregroundStyle(
                            LinearGradient(
                                colors: [.blue, .purple],
                                startPoint: .topLeading,
                                endPoint: .bottomTrailing
                            )
                        )
                    Spacer()
                }
                
                Text("Total Users")
                    .font(.system(size: 12, weight: .medium))
                    .foregroundColor(.secondary)
                
                Text("\(stats.totalUsers)")
                    .font(.system(size: 36, weight: .bold, design: .rounded))
                    .foregroundColor(.primary)
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            
            Divider()
            
            // Right side - Today & Active
            VStack(alignment: .leading, spacing: 16) {
                VStack(alignment: .leading, spacing: 4) {
                    Text("Today's Signups")
                        .font(.system(size: 12, weight: .medium))
                        .foregroundColor(.secondary)
                    Text("\(stats.todaySignups)")
                        .font(.system(size: 24, weight: .bold, design: .rounded))
                }
                
                VStack(alignment: .leading, spacing: 4) {
                    Text("Active Users")
                        .font(.system(size: 12, weight: .medium))
                        .foregroundColor(.secondary)
                    Text("\(stats.activeUsers)")
                        .font(.system(size: 24, weight: .bold, design: .rounded))
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
        }
        .padding()
        .background(
            LinearGradient(
                colors: [
                    Color(red: 0.95, green: 0.97, blue: 1.0),
                    Color(red: 0.98, green: 0.99, blue: 1.0)
                ],
                startPoint: .topLeading,
                endPoint: .bottomTrailing
            )
        )
    }
}

#Preview(as: .systemSmall) {
    GenAIAcademyWidget()
} timeline: {
    WidgetEntry(
        date: Date(),
        stats: WidgetStats(
            totalUsers: 1234,
            todaySignups: 45,
            activeUsers: 890,
            lastUpdated: ISO8601DateFormatter().string(from: Date())
        )
    )
}

#Preview(as: .systemMedium) {
    GenAIAcademyWidget()
} timeline: {
    WidgetEntry(
        date: Date(),
        stats: WidgetStats(
            totalUsers: 1234,
            todaySignups: 45,
            activeUsers: 890,
            lastUpdated: ISO8601DateFormatter().string(from: Date())
        )
    )
}
