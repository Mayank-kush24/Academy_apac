import '../models/user.dart';
import '../utils/constants.dart';
import 'network_service.dart';
import 'storage_service.dart';

/// Authentication service (replaces AuthService.swift)
class AuthService {
  static final AuthService _instance = AuthService._internal();
  factory AuthService() => _instance;
  AuthService._internal();
  
  final _networkService = NetworkService();
  final _storageService = StorageService();
  
  bool _isAuthenticated = false;
  User? _currentUser;
  
  bool get isAuthenticated => _isAuthenticated;
  User? get currentUser => _currentUser;
  
  /// Login with email and password
  Future<void> login(String email, String password) async {
    try {
      final body = {
        'email': email,
        'password': password,
      };
      
      final response = await _networkService.postWithoutAuth<LoginResponse>(
        Constants.loginEndpoint,
        body,
        (json) => LoginResponse.fromJson(json),
      );
      
      // Save token
      final tokenSaved = await _storageService.saveToken(response.token);
      if (!tokenSaved) {
        throw Exception('Failed to save token');
      }
      
      // Save user data
      await _storageService.saveUser(response.user);
      
      // Update state
      _currentUser = response.user;
      _isAuthenticated = true;
    } catch (e) {
      _isAuthenticated = false;
      _currentUser = null;
      rethrow;
    }
  }
  
  /// Logout and clear all stored data
  Future<void> logout() async {
    await _storageService.clearAll();
    _currentUser = null;
    _isAuthenticated = false;
  }
  
  /// Check if user is already logged in (auto-login)
  Future<bool> checkAutoLogin() async {
    final token = await _storageService.getToken();
    if (token == null) {
      _isAuthenticated = false;
      return false;
    }
    
    try {
      // Validate token by fetching user info
      final response = await _networkService.get<UserInfoResponse>(
        Constants.userInfoEndpoint,
        (json) => UserInfoResponse.fromJson(json),
      );
      
      _currentUser = response.user;
      _isAuthenticated = true;
      return true;
    } catch (e) {
      // Token is invalid, clear it
      await logout();
      return false;
    }
  }
  
  /// Get stored token
  Future<String?> getToken() async {
    return await _storageService.getToken();
  }
}
