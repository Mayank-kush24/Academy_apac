//
//  LoginViewModel.swift
//  GenAIAcademyDashboard
//
//  ViewModel for login screen
//

import Foundation
import SwiftUI

@MainActor
class LoginViewModel: ObservableObject {
    @Published var email = ""
    @Published var password = ""
    @Published var isLoading = false
    @Published var errorMessage: String?
    
    private let authService = AuthService.shared
    
    /// Validate email format
    func isValidEmail() -> Bool {
        let emailRegex = "[A-Z0-9a-z._%+-]+@[A-Za-z0-9.-]+\\.[A-Za-z]{2,64}"
        let emailPredicate = NSPredicate(format: "SELF MATCHES %@", emailRegex)
        return emailPredicate.evaluate(with: email)
    }
    
    /// Validate form before submission
    func validateForm() -> Bool {
        if email.isEmpty {
            errorMessage = "Email is required"
            return false
        }
        
        if !isValidEmail() {
            errorMessage = "Please enter a valid email address"
            return false
        }
        
        if password.isEmpty {
            errorMessage = "Password is required"
            return false
        }
        
        if password.count < 3 {
            errorMessage = "Password must be at least 3 characters"
            return false
        }
        
        return true
    }
    
    /// Perform login
    func login() async {
        // Clear previous errors
        errorMessage = nil
        
        // Validate form
        guard validateForm() else {
            return
        }
        
        isLoading = true
        
        do {
            try await authService.login(email: email, password: password)
            // Success - authentication state will be updated by AuthService
        } catch let error as NetworkError {
            errorMessage = error.errorDescription
        } catch {
            errorMessage = "An unexpected error occurred. Please try again."
        }
        
        isLoading = false
    }
}
