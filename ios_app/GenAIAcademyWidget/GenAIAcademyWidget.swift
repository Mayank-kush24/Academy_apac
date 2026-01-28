//
//  GenAIAcademyWidget.swift
//  GenAIAcademyWidget
//
//  Widget entry point and configuration
//

import WidgetKit
import SwiftUI

@main
struct GenAIAcademyWidget: Widget {
    let kind: String = "GenAIAcademyWidget"
    
    var body: some WidgetConfiguration {
        StaticConfiguration(kind: kind, provider: WidgetTimelineProvider()) { entry in
            GenAIAcademyWidgetEntryView(entry: entry)
                .containerBackground(.fill.tertiary, for: .widget)
        }
        .configurationDisplayName("Gen AI Academy Dashboard")
        .description("View key statistics from your dashboard")
        .supportedFamilies([.systemSmall, .systemMedium])
    }
}
