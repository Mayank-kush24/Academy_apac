import 'package:json_annotation/json_annotation.dart';

part 'widget_stats.g.dart';

@JsonSerializable()
class WidgetStats {
  @JsonKey(name: 'total_users')
  final int totalUsers;
  
  @JsonKey(name: 'today_signups')
  final int todaySignups;
  
  @JsonKey(name: 'active_users')
  final int activeUsers;
  
  @JsonKey(name: 'last_updated')
  final String lastUpdated;
  
  WidgetStats({
    required this.totalUsers,
    required this.todaySignups,
    required this.activeUsers,
    required this.lastUpdated,
  });
  
  factory WidgetStats.fromJson(Map<String, dynamic> json) => _$WidgetStatsFromJson(json);
  Map<String, dynamic> toJson() => _$WidgetStatsToJson(this);
}
