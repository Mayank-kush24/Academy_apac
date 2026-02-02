import 'package:json_annotation/json_annotation.dart';

part 'dashboard_summary.g.dart';

@JsonSerializable()
class DashboardSummary {
  @JsonKey(name: 'total_users')
  final int totalUsers;
  
  @JsonKey(name: 'unique_organizations')
  final int uniqueOrganizations;
  
  @JsonKey(name: 'top_domain')
  final String topDomain;
  
  @JsonKey(name: 'top_city')
  final String topCity;
  
  @JsonKey(name: 'top_organization')
  final String? topOrganization;
  
  @JsonKey(name: 'unique_countries')
  final int? uniqueCountries;
  
  @JsonKey(name: 'users_with_github')
  final int? usersWithGithub;
  
  @JsonKey(name: 'users_with_linkedin')
  final int? usersWithLinkedin;
  
  @JsonKey(name: 'average_age')
  final int? averageAge;
  
  DashboardSummary({
    required this.totalUsers,
    required this.uniqueOrganizations,
    required this.topDomain,
    required this.topCity,
    this.topOrganization,
    this.uniqueCountries,
    this.usersWithGithub,
    this.usersWithLinkedin,
    this.averageAge,
  });
  
  factory DashboardSummary.fromJson(Map<String, dynamic> json) => _$DashboardSummaryFromJson(json);
  Map<String, dynamic> toJson() => _$DashboardSummaryToJson(this);
}
