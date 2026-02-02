import 'package:flutter/material.dart';

/// App theme and colors
class AppTheme {
  // Primary colors matching web app
  static const Color primaryColor = Color(0xFF6366F1);
  static const Color primaryDark = Color(0xFF4F46E5);
  
  // Gradient colors for cards
  static const List<Color> blueGradient = [Color(0xFF3B82F6), Color(0xFF06B6D4)];
  static const List<Color> purpleGradient = [Color(0xFF8B5CF6), Color(0xFFEC4899)];
  static const List<Color> orangeGradient = [Color(0xFFF97316), Color(0xFFEF4444)];
  static const List<Color> greenGradient = [Color(0xFF10B981), Color(0xFF34D399)];
  
  // Glassmorphism colors
  static const Color glassBackground = Color(0x40FFFFFF);
  static const Color glassBorder = Color(0x30FFFFFF);
  
  // Text colors
  static const Color textPrimary = Color(0xFF1F2937);
  static const Color textSecondary = Color(0xFF6B7280);
  
  // Light theme
  static ThemeData lightTheme = ThemeData(
    useMaterial3: true,
    colorScheme: ColorScheme.light(
      primary: primaryColor,
      secondary: primaryDark,
      surface: Colors.white,
      background: Color(0xFFF9FAFB),
    ),
    scaffoldBackgroundColor: Color(0xFFF9FAFB),
    fontFamily: 'Inter',
  );
  
  // Dark theme
  static ThemeData darkTheme = ThemeData(
    useMaterial3: true,
    colorScheme: ColorScheme.dark(
      primary: primaryColor,
      secondary: primaryDark,
      surface: Color(0xFF1F2937),
      background: Color(0xFF111827),
    ),
    scaffoldBackgroundColor: Color(0xFF111827),
    fontFamily: 'Inter',
  );
}
