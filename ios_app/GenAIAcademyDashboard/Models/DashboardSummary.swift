//
//  DashboardSummary.swift
//  GenAIAcademyDashboard
//
//  Dashboard summary model matching backend API response
//

import Foundation

struct DashboardSummary: Codable {
    let totalUsers: Int
    let uniqueOrganizations: Int
    let topDomain: String
    let topCity: String
    let topOrganization: String?
    let uniqueCountries: Int?
    let usersWithGithub: Int?
    let usersWithLinkedin: Int?
    let averageAge: Int?
    
    enum CodingKeys: String, CodingKey {
        case totalUsers = "total_users"
        case uniqueOrganizations = "unique_organizations"
        case topDomain = "top_domain"
        case topCity = "top_city"
        case topOrganization = "top_organization"
        case uniqueCountries = "unique_countries"
        case usersWithGithub = "users_with_github"
        case usersWithLinkedin = "users_with_linkedin"
        case averageAge = "average_age"
    }
}
