import 'package:flutter/foundation.dart';
import '../services/auth_service.dart';

/// ViewModel for login screen (MVVM pattern)
class LoginViewModel extends ChangeNotifier {
  final _authService = AuthService();
  
  bool _isLoading = false;
  String? _errorMessage;
  bool _isAuthenticated = false;
  
  bool get isLoading => _isLoading;
  String? get errorMessage => _errorMessage;
  bool get isAuthenticated => _isAuthenticated;
  
  /// Validate email format
  bool isValidEmail(String email) {
    return RegExp(r'^[\w-\.]+@([\w-]+\.)+[\w-]{2,4}$').hasMatch(email);
  }
  
  /// Validate password (minimum 6 characters)
  bool isValidPassword(String password) {
    return password.length >= 6;
  }
  
  /// Login with email and password
  Future<bool> login(String email, String password) async {
    // Validation
    if (!isValidEmail(email)) {
      _errorMessage = 'Please enter a valid email address';
      notifyListeners();
      return false;
    }
    
    if (!isValidPassword(password)) {
      _errorMessage = 'Password must be at least 6 characters';
      notifyListeners();
      return false;
    }
    
    _isLoading = true;
    _errorMessage = null;
    notifyListeners();
    
    try {
      await _authService.login(email, password);
      _isAuthenticated = true;
      _isLoading = false;
      _errorMessage = null;
      notifyListeners();
      return true;
    } catch (e) {
      _isLoading = false;
      _errorMessage = e.toString().replaceAll('Exception: ', '');
      _isAuthenticated = false;
      notifyListeners();
      return false;
    }
  }
  
  /// Clear error message
  void clearError() {
    _errorMessage = null;
    notifyListeners();
  }
}
