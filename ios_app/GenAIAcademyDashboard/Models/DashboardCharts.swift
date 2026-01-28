//
//  DashboardCharts.swift
//  GenAIAcademyDashboard
//
//  Dashboard charts model matching backend API response
//

import Foundation

struct ChartDataPoint: Codable {
    let label: String
    let value: Int
}

struct DashboardCharts: Codable {
    let registrationTrends: [ChartDataPoint]
    let genderDistribution: [ChartDataPoint]
    let topDomains: [ChartDataPoint]
    let topCities: [ChartDataPoint]
    let topOrganizations: [ChartDataPoint]
    
    enum CodingKeys: String, CodingKey {
        case registrationTrends = "registration_trends"
        case genderDistribution = "gender_distribution"
        case topDomains = "top_domains"
        case topCities = "top_cities"
        case topOrganizations = "top_organizations"
    }
}
