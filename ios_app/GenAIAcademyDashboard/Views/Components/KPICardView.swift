//
//  KPICardView.swift
//  GenAIAcademyDashboard
//
//  Glassmorphism-style KPI card component
//

import SwiftUI

struct KPICardView: View {
    let title: String
    let value: String
    let subtitle: String?
    let gradientColors: [Color]
    
    @Environment(\.colorScheme) var colorScheme
    
    init(title: String, value: String, subtitle: String? = nil, gradientColors: [Color] = [.blue, .purple]) {
        self.title = title
        self.value = value
        self.subtitle = subtitle
        self.gradientColors = gradientColors
    }
    
    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text(title)
                .font(.system(size: 12, weight: .semibold))
                .foregroundColor(.secondary)
                .textCase(.uppercase)
                .tracking(0.5)
            
            Text(value)
                .font(.system(size: 32, weight: .bold, design: .rounded))
                .foregroundColor(.primary)
            
            if let subtitle = subtitle {
                Text(subtitle)
                    .font(.system(size: 13, weight: .medium))
                    .foregroundColor(.secondary)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(20)
        .background(
            RoundedRectangle(cornerRadius: 16)
                .fill(.ultraThinMaterial)
                .overlay(
                    RoundedRectangle(cornerRadius: 16)
                        .stroke(
                            LinearGradient(
                                colors: gradientColors,
                                startPoint: .topLeading,
                                endPoint: .bottomTrailing
                            ),
                            lineWidth: 1
                        )
                        .opacity(0.3)
                )
        )
        .shadow(color: .black.opacity(0.1), radius: 10, x: 0, y: 5)
    }
}

#Preview {
    HStack {
        KPICardView(
            title: "Total Users",
            value: "1,234",
            subtitle: "+12% this week"
        )
        KPICardView(
            title: "Organizations",
            value: "45",
            subtitle: "Active"
        )
    }
    .padding()
}
