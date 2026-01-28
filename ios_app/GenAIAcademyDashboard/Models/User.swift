//
//  User.swift
//  GenAIAcademyDashboard
//
//  User model matching backend API response
//

import Foundation

struct User: Codable, Identifiable {
    let id: String
    let name: String
    let email: String
    let role: String
    let status: String
}

struct LoginResponse: Codable {
    let token: String
    let user: User
}

struct UserInfoResponse: Codable {
    let user: User
}
