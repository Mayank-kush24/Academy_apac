//
//  AuthService.swift
//  GenAIAcademyDashboard
//
//  Authentication service for login, logout, and token management
//

import Foundation

@MainActor
class AuthService: ObservableObject {
    static let shared = AuthService()
    
    @Published var isAuthenticated = false
    @Published var currentUser: User?
    
    private let networkManager = NetworkManager.shared
    private let keychainService = KeychainService.shared
    
    private init() {
        checkAutoLogin()
    }
    
    /// Login with email and password
    func login(email: String, password: String) async throws {
        let body: [String: Any] = [
            "email": email,
            "password": password
        ]
        
        do {
            let response: LoginResponse = try await networkManager.requestWithoutAuth(
                endpoint: Constants.loginEndpoint,
                method: .POST,
                body: body,
                responseType: LoginResponse.self
            )
            
            // Save token to Keychain
            let saved = keychainService.save(response.token, forKey: Constants.tokenKey)
            guard saved else {
                throw NetworkError.unknown(NSError(domain: "KeychainError", code: -1))
            }
            
            // Also save token to App Group for widget access
            if let sharedDefaults = UserDefaults(suiteName: Constants.appGroupID) {
                sharedDefaults.set(response.token, forKey: Constants.tokenKey)
                sharedDefaults.synchronize()
            }
            
            // Save user data
            if let userData = try? JSONEncoder().encode(response.user),
               let userString = String(data: userData, encoding: .utf8) {
                keychainService.save(userString, forKey: Constants.userKey)
            }
            
            // Update state
            currentUser = response.user
            isAuthenticated = true
        } catch {
            throw error
        }
    }
    
    /// Logout and clear all stored data
    func logout() {
        keychainService.clearAll()
        
        // Also clear from App Group
        if let sharedDefaults = UserDefaults(suiteName: Constants.appGroupID) {
            sharedDefaults.removeObject(forKey: Constants.tokenKey)
            sharedDefaults.removeObject(forKey: "widgetStats")
            sharedDefaults.synchronize()
        }
        
        currentUser = nil
        isAuthenticated = false
    }
    
    /// Check if user is already logged in (auto-login)
    func checkAutoLogin() {
        guard let token = keychainService.get(forKey: Constants.tokenKey) else {
            isAuthenticated = false
            return
        }
        
        // Validate token by fetching user info
        Task {
            do {
                let response: UserInfoResponse = try await networkManager.request(
                    endpoint: Constants.userInfoEndpoint,
                    responseType: UserInfoResponse.self
                )
                
                await MainActor.run {
                    currentUser = response.user
                    isAuthenticated = true
                }
            } catch {
                // Token is invalid, clear it
                await MainActor.run {
                    logout()
                }
            }
        }
    }
    
    /// Get stored token
    func getToken() -> String? {
        return keychainService.get(forKey: Constants.tokenKey)
    }
}
