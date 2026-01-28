//
//  NetworkManager.swift
//  GenAIAcademyDashboard
//
//  Generic networking layer with JWT token handling
//

import Foundation

enum HTTPMethod: String {
    case GET = "GET"
    case POST = "POST"
    case PUT = "PUT"
    case DELETE = "DELETE"
}

enum NetworkError: LocalizedError {
    case invalidURL
    case noData
    case decodingError
    case unauthorized
    case serverError(Int)
    case unknown(Error)
    
    var errorDescription: String? {
        switch self {
        case .invalidURL:
            return "Invalid URL"
        case .noData:
            return "No data received"
        case .decodingError:
            return "Failed to decode response"
        case .unauthorized:
            return "Unauthorized. Please login again."
        case .serverError(let code):
            return "Server error: \(code)"
        case .unknown(let error):
            return error.localizedDescription
        }
    }
}

class NetworkManager {
    static let shared = NetworkManager()
    private let session = URLSession.shared
    private let keychainService = KeychainService.shared
    
    private init() {}
    
    /// Make a network request with automatic JWT token injection
    func request<T: Decodable>(
        endpoint: String,
        method: HTTPMethod = .GET,
        body: [String: Any]? = nil,
        responseType: T.Type
    ) async throws -> T {
        // Build URL
        guard let url = URL(string: Constants.baseURL + endpoint) else {
            throw NetworkError.invalidURL
        }
        
        // Create request
        var request = URLRequest(url: url)
        request.httpMethod = method.rawValue
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        
        // Add JWT token if available
        if let token = keychainService.get(forKey: Constants.tokenKey) {
            request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        }
        
        // Add body for POST/PUT requests
        if let body = body {
            do {
                request.httpBody = try JSONSerialization.data(withJSONObject: body)
            } catch {
                throw NetworkError.unknown(error)
            }
        }
        
        // Perform request
        do {
            let (data, response) = try await session.data(for: request)
            
            // Check HTTP status
            if let httpResponse = response as? HTTPURLResponse {
                switch httpResponse.statusCode {
                case 200...299:
                    break // Success
                case 401:
                    // Unauthorized - clear token
                    keychainService.delete(forKey: Constants.tokenKey)
                    throw NetworkError.unauthorized
                default:
                    throw NetworkError.serverError(httpResponse.statusCode)
                }
            }
            
            // Decode response
            guard !data.isEmpty else {
                throw NetworkError.noData
            }
            
            do {
                let decoder = JSONDecoder()
                decoder.keyDecodingStrategy = .convertFromSnakeCase
                return try decoder.decode(T.self, from: data)
            } catch {
                print("Decoding error: \(error)")
                throw NetworkError.decodingError
            }
        } catch let error as NetworkError {
            throw error
        } catch {
            throw NetworkError.unknown(error)
        }
    }
    
    /// Make a request without authentication (for login)
    func requestWithoutAuth<T: Decodable>(
        endpoint: String,
        method: HTTPMethod = .POST,
        body: [String: Any]?,
        responseType: T.Type
    ) async throws -> T {
        guard let url = URL(string: Constants.baseURL + endpoint) else {
            throw NetworkError.invalidURL
        }
        
        var request = URLRequest(url: url)
        request.httpMethod = method.rawValue
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        
        if let body = body {
            do {
                request.httpBody = try JSONSerialization.data(withJSONObject: body)
            } catch {
                throw NetworkError.unknown(error)
            }
        }
        
        do {
            let (data, response) = try await session.data(for: request)
            
            if let httpResponse = response as? HTTPURLResponse {
                switch httpResponse.statusCode {
                case 200...299:
                    break
                case 401:
                    throw NetworkError.unauthorized
                default:
                    throw NetworkError.serverError(httpResponse.statusCode)
                }
            }
            
            guard !data.isEmpty else {
                throw NetworkError.noData
            }
            
            let decoder = JSONDecoder()
            decoder.keyDecodingStrategy = .convertFromSnakeCase
            return try decoder.decode(T.self, from: data)
        } catch let error as NetworkError {
            throw error
        } catch {
            throw NetworkError.unknown(error)
        }
    }
}
