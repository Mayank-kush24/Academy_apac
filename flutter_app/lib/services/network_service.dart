import 'dart:convert';
import 'package:http/http.dart' as http;
import '../utils/constants.dart';
import 'storage_service.dart';

/// Network error types
class NetworkError implements Exception {
  final String message;
  final int? statusCode;
  
  NetworkError(this.message, [this.statusCode]);
  
  @override
  String toString() => message;
}

/// Service for making HTTP requests (replaces NetworkManager.swift)
class NetworkService {
  static final NetworkService _instance = NetworkService._internal();
  factory NetworkService() => _instance;
  NetworkService._internal();
  
  final _storageService = StorageService();
  
  /// Make authenticated GET request
  Future<T> get<T>(String endpoint, T Function(Map<String, dynamic>) fromJson) async {
    return _request('GET', endpoint, null, fromJson);
  }
  
  /// Make authenticated POST request
  Future<T> post<T>(String endpoint, Map<String, dynamic>? body, T Function(Map<String, dynamic>) fromJson) async {
    return _request('POST', endpoint, body, fromJson);
  }
  
  /// Make request without authentication (for login)
  Future<T> postWithoutAuth<T>(String endpoint, Map<String, dynamic> body, T Function(Map<String, dynamic>) fromJson) async {
    final url = Uri.parse('${Constants.baseURL}$endpoint');
    
    try {
      final response = await http.post(
        url,
        headers: {'Content-Type': 'application/json'},
        body: body != null ? jsonEncode(body) : null,
      );
      
      return _handleResponse<T>(response, fromJson);
    } catch (e) {
      throw NetworkError('Network error: ${e.toString()}');
    }
  }
  
  /// Internal request method with authentication
  Future<T> _request<T>(
    String method,
    String endpoint,
    Map<String, dynamic>? body,
    T Function(Map<String, dynamic>) fromJson,
  ) async {
    final url = Uri.parse('${Constants.baseURL}$endpoint');
    final token = await _storageService.getToken();
    
    final headers = <String, String>{
      'Content-Type': 'application/json',
    };
    
    if (token != null) {
      headers['Authorization'] = 'Bearer $token';
    }
    
    try {
      http.Response response;
      
      switch (method.toUpperCase()) {
        case 'GET':
          response = await http.get(url, headers: headers);
          break;
        case 'POST':
          response = await http.post(
            url,
            headers: headers,
            body: body != null ? jsonEncode(body) : null,
          );
          break;
        default:
          throw NetworkError('Unsupported HTTP method: $method');
      }
      
      return _handleResponse<T>(response, fromJson);
    } catch (e) {
      throw NetworkError('Network error: ${e.toString()}');
    }
  }
  
  /// Handle HTTP response
  T _handleResponse<T>(http.Response response, T Function(Map<String, dynamic>) fromJson) {
    if (response.statusCode == 401) {
      // Unauthorized - clear token
      _storageService.deleteToken();
      throw NetworkError('Unauthorized. Please login again.', 401);
    }
    
    if (response.statusCode < 200 || response.statusCode >= 300) {
      throw NetworkError(
        'Server error: ${response.statusCode}',
        response.statusCode,
      );
    }
    
    try {
      final jsonData = jsonDecode(response.body) as Map<String, dynamic>;
      return fromJson(jsonData);
    } catch (e) {
      throw NetworkError('Failed to decode response: ${e.toString()}');
    }
  }
}
