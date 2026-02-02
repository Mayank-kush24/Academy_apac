import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'dart:convert';
import '../models/user.dart';
import '../utils/constants.dart';

/// Service for secure storage (replaces iOS Keychain)
class StorageService {
  static final StorageService _instance = StorageService._internal();
  factory StorageService() => _instance;
  StorageService._internal();
  
  final _secureStorage = FlutterSecureStorage(
    aOptions: AndroidOptions(
      encryptedSharedPreferences: true,
    ),
    iOptions: IOSOptions(
      accessibility: IOSAccessibility.first_unlock_this_device,
    ),
  );
  
  /// Save JWT token securely
  Future<bool> saveToken(String token) async {
    try {
      await _secureStorage.write(key: Constants.tokenKey, value: token);
      // Also save to shared preferences for widget access
      final prefs = await SharedPreferences.getInstance();
      await prefs.setString(Constants.tokenKey, token);
      return true;
    } catch (e) {
      print('Error saving token: $e');
      return false;
    }
  }
  
  /// Get JWT token
  Future<String?> getToken() async {
    try {
      return await _secureStorage.read(key: Constants.tokenKey);
    } catch (e) {
      print('Error reading token: $e');
      return null;
    }
  }
  
  /// Delete token
  Future<void> deleteToken() async {
    try {
      await _secureStorage.delete(key: Constants.tokenKey);
      final prefs = await SharedPreferences.getInstance();
      await prefs.remove(Constants.tokenKey);
    } catch (e) {
      print('Error deleting token: $e');
    }
  }
  
  /// Save user data
  Future<bool> saveUser(User user) async {
    try {
      final userJson = jsonEncode(user.toJson());
      await _secureStorage.write(key: Constants.userKey, value: userJson);
      return true;
    } catch (e) {
      print('Error saving user: $e');
      return false;
    }
  }
  
  /// Get user data
  Future<User?> getUser() async {
    try {
      final userJson = await _secureStorage.read(key: Constants.userKey);
      if (userJson == null) return null;
      final userMap = jsonDecode(userJson) as Map<String, dynamic>;
      return User.fromJson(userMap);
    } catch (e) {
      print('Error reading user: $e');
      return null;
    }
  }
  
  /// Clear all stored data
  Future<void> clearAll() async {
    try {
      await _secureStorage.deleteAll();
      final prefs = await SharedPreferences.getInstance();
      await prefs.clear();
    } catch (e) {
      print('Error clearing storage: $e');
    }
  }
  
  /// Get token from shared preferences (for widget)
  Future<String?> getTokenForWidget() async {
    try {
      final prefs = await SharedPreferences.getInstance();
      return prefs.getString(Constants.tokenKey);
    } catch (e) {
      return null;
    }
  }
}
