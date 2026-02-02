import 'package:json_annotation/json_annotation.dart';

part 'dashboard_charts.g.dart';

@JsonSerializable()
class DashboardCharts {
  final Map<String, int>? registrationTrend;
  final Map<String, int>? genderDistribution;
  final List<Map<String, dynamic>>? topDomains;
  final List<Map<String, dynamic>>? topCities;
  final List<Map<String, dynamic>>? topOrganizations;
  
  DashboardCharts({
    this.registrationTrend,
    this.genderDistribution,
    this.topDomains,
    this.topCities,
    this.topOrganizations,
  });
  
  factory DashboardCharts.fromJson(Map<String, dynamic> json) => _$DashboardChartsFromJson(json);
  Map<String, dynamic> toJson() => _$DashboardChartsToJson(this);
}
