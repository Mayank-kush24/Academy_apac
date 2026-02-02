/// Constants for API endpoints and storage keys
class Constants {
  // Base API URL - Update this to your server IP
  static const String baseURL = 'http://YOUR_SERVER_IP:3002/api';
  
  // API Endpoints
  static const String loginEndpoint = '/auth/login';
  static const String userInfoEndpoint = '/auth/me';
  static const String dashboardSummaryEndpoint = '/dashboard/summary';
  static const String dashboardChartsEndpoint = '/dashboard/charts';
  static const String widgetStatsEndpoint = '/dashboard/widget-stats';
  
  // Storage Keys
  static const String tokenKey = 'authToken';
  static const String userKey = 'userData';
  
  // Widget Keys
  static const String widgetTotalUsersKey = 'totalUsers';
  static const String widgetTodaySignupsKey = 'todaySignups';
  static const String widgetActiveUsersKey = 'activeUsers';
  static const String widgetLastUpdatedKey = 'lastUpdated';
}
