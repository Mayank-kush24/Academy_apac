import 'dart:convert';
import 'package:http/http.dart' as http;
import 'package:shared_preferences/shared_preferences.dart';
import 'package:home_widget/home_widget.dart';
import '../models/widget_stats.dart';
import '../utils/constants.dart';
import 'storage_service.dart';

/// Service for home screen widget data (replaces WidgetTimelineProvider.swift)
class WidgetService {
  static final WidgetService _instance = WidgetService._internal();
  factory WidgetService() => _instance;
  WidgetService._internal();
  
  final _storageService = StorageService();
  
  /// Fetch widget stats from API and update widget
  Future<void> updateWidget() async {
    try {
      final token = await _storageService.getTokenForWidget();
      if (token == null) {
        await _setDefaultWidgetData();
        return;
      }
      
      final url = Uri.parse('${Constants.baseURL}${Constants.widgetStatsEndpoint}');
      final response = await http.get(
        url,
        headers: {
          'Authorization': 'Bearer $token',
          'Content-Type': 'application/json',
        },
      );
      
      if (response.statusCode == 200) {
        final jsonData = jsonDecode(response.body) as Map<String, dynamic>;
        final stats = WidgetStats.fromJson(jsonData);
        await _updateWidgetData(stats);
        
        // Cache stats
        final prefs = await SharedPreferences.getInstance();
        await prefs.setString('widgetStats', jsonEncode(stats.toJson()));
      } else {
        // Use cached data if available
        await _loadCachedWidgetData();
      }
    } catch (e) {
      print('Error updating widget: $e');
      // Use cached data or default
      await _loadCachedWidgetData();
    }
  }
  
  /// Update widget with stats data
  Future<void> _updateWidgetData(WidgetStats stats) async {
    try {
      await HomeWidget.saveWidgetData<String>(
        Constants.widgetTotalUsersKey,
        stats.totalUsers.toString(),
      );
      await HomeWidget.saveWidgetData<String>(
        Constants.widgetTodaySignupsKey,
        stats.todaySignups.toString(),
      );
      await HomeWidget.saveWidgetData<String>(
        Constants.widgetActiveUsersKey,
        stats.activeUsers.toString(),
      );
      await HomeWidget.saveWidgetData<String>(
        Constants.widgetLastUpdatedKey,
        stats.lastUpdated,
      );
      
      // Update widget UI
      await HomeWidget.updateWidget(
        name: 'GenAIAcademyWidget',
        iOSName: 'GenAIAcademyWidget',
      );
    } catch (e) {
      print('Error saving widget data: $e');
    }
  }
  
  /// Load cached widget data
  Future<void> _loadCachedWidgetData() async {
    try {
      final prefs = await SharedPreferences.getInstance();
      final cachedJson = prefs.getString('widgetStats');
      if (cachedJson != null) {
        final stats = WidgetStats.fromJson(jsonDecode(cachedJson));
        await _updateWidgetData(stats);
      } else {
        await _setDefaultWidgetData();
      }
    } catch (e) {
      await _setDefaultWidgetData();
    }
  }
  
  /// Set default widget data
  Future<void> _setDefaultWidgetData() async {
    final defaultStats = WidgetStats(
      totalUsers: 0,
      todaySignups: 0,
      activeUsers: 0,
      lastUpdated: DateTime.now().toIso8601String(),
    );
    await _updateWidgetData(defaultStats);
  }
}
