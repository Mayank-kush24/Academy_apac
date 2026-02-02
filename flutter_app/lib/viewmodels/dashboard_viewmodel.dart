import 'package:flutter/foundation.dart';
import '../models/dashboard_summary.dart';
import '../models/dashboard_charts.dart';
import '../services/network_service.dart';
import '../utils/constants.dart';

/// ViewModel for dashboard screen (MVVM pattern)
class DashboardViewModel extends ChangeNotifier {
  final _networkService = NetworkService();
  
  DashboardSummary? _summary;
  DashboardCharts? _charts;
  bool _isLoading = false;
  String? _errorMessage;
  Period _selectedPeriod = Period.thirtyDays;
  
  DashboardSummary? get summary => _summary;
  DashboardCharts? get charts => _charts;
  bool get isLoading => _isLoading;
  String? get errorMessage => _errorMessage;
  Period get selectedPeriod => _selectedPeriod;
  
  /// Time period enum
  enum Period {
    sevenDays('7d', 'Last 7 Days'),
    thirtyDays('30d', 'Last 30 Days'),
    ninetyDays('90d', 'Last 90 Days');
    
    final String value;
    final String displayName;
    const Period(this.value, this.displayName);
  }
  
  /// Load dashboard summary data
  Future<void> loadSummary() async {
    try {
      final endpoint = '${Constants.dashboardSummaryEndpoint}?period=${_selectedPeriod.value}';
      _summary = await _networkService.get<DashboardSummary>(
        endpoint,
        (json) => DashboardSummary.fromJson(json),
      );
      _errorMessage = null;
      notifyListeners();
    } catch (e) {
      _errorMessage = e.toString().replaceAll('NetworkError: ', '');
      notifyListeners();
    }
  }
  
  /// Load dashboard charts data
  Future<void> loadCharts() async {
    try {
      final endpoint = '${Constants.dashboardChartsEndpoint}?period=${_selectedPeriod.value}';
      _charts = await _networkService.get<DashboardCharts>(
        endpoint,
        (json) => DashboardCharts.fromJson(json),
      );
    } catch (e) {
      // Charts are optional, don't show error if they fail
      print('Failed to load charts: $e');
    }
  }
  
  /// Load all dashboard data
  Future<void> loadDashboardData() async {
    _isLoading = true;
    _errorMessage = null;
    notifyListeners();
    
    await Future.wait([
      loadSummary(),
      loadCharts(),
    ]);
    
    _isLoading = false;
    notifyListeners();
  }
  
  /// Refresh dashboard data
  Future<void> refresh() async {
    await loadDashboardData();
  }
  
  /// Change time period and reload data
  Future<void> changePeriod(Period period) async {
    _selectedPeriod = period;
    await loadDashboardData();
  }
}
