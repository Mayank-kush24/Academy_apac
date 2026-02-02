import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../viewmodels/dashboard_viewmodel.dart';
import '../services/auth_service.dart';
import '../utils/theme.dart';
import 'widgets/kpi_card.dart';
import 'widgets/loading_indicator.dart';
import 'widgets/error_view.dart';
import 'login_screen.dart';

/// Dashboard screen with KPI cards and period selection
class DashboardScreen extends StatefulWidget {
  const DashboardScreen({Key? key}) : super(key: key);
  
  @override
  State<DashboardScreen> createState() => _DashboardScreenState();
}

class _DashboardScreenState extends State<DashboardScreen> {
  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      context.read<DashboardViewModel>().loadDashboardData();
    });
  }
  
  Future<void> _handleLogout() async {
    final authService = AuthService();
    await authService.logout();
    if (mounted) {
      Navigator.of(context).pushReplacement(
        MaterialPageRoute(builder: (_) => LoginScreen()),
      );
    }
  }
  
  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: Text('Dashboard'),
        elevation: 0,
        actions: [
          PopupMenuButton(
            icon: Icon(Icons.more_vert),
            itemBuilder: (context) => [
              PopupMenuItem(
                child: Row(
                  children: [
                    Icon(Icons.refresh, size: 20),
                    SizedBox(width: 8),
                    Text('Refresh'),
                  ],
                ),
                onTap: () {
                  Future.delayed(Duration.zero, () {
                    context.read<DashboardViewModel>().refresh();
                  });
                },
              ),
              PopupMenuDivider(),
              PopupMenuItem(
                child: Row(
                  children: [
                    Icon(Icons.logout, size: 20, color: Colors.red),
                    SizedBox(width: 8),
                    Text('Logout', style: TextStyle(color: Colors.red)),
                  ],
                ),
                onTap: _handleLogout,
              ),
            ],
          ),
        ],
      ),
      body: Consumer<DashboardViewModel>(
        builder: (context, viewModel, child) {
          if (viewModel.isLoading && viewModel.summary == null) {
            return LoadingIndicator(message: 'Loading dashboard...');
          }
          
          if (viewModel.errorMessage != null && viewModel.summary == null) {
            return ErrorView(
              message: viewModel.errorMessage!,
              onRetry: () => viewModel.loadDashboardData(),
            );
          }
          
          return RefreshIndicator(
            onRefresh: () => viewModel.refresh(),
            child: SingleChildScrollView(
              physics: AlwaysScrollableScrollPhysics(),
              padding: EdgeInsets.all(16),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  // Period Selector
                  _buildPeriodSelector(viewModel),
                  SizedBox(height: 24),
                  
                  // KPI Cards Grid
                  if (viewModel.summary != null)
                    _buildKPICards(viewModel.summary!),
                ],
              ),
            ),
          );
        },
      ),
    );
  }
  
  Widget _buildPeriodSelector(DashboardViewModel viewModel) {
    return Row(
      mainAxisAlignment: MainAxisAlignment.center,
      children: DashboardViewModel.Period.values.map((period) {
        final isSelected = viewModel.selectedPeriod == period;
        return Padding(
          padding: EdgeInsets.symmetric(horizontal: 6),
          child: ElevatedButton(
            onPressed: () => viewModel.changePeriod(period),
            style: ElevatedButton.styleFrom(
              padding: EdgeInsets.symmetric(horizontal: 20, vertical: 10),
              backgroundColor: isSelected ? null : Colors.transparent,
              foregroundColor: isSelected ? Colors.white : AppTheme.textPrimary,
              elevation: isSelected ? 4 : 0,
              shape: RoundedRectangleBorder(
                borderRadius: BorderRadius.circular(20),
                side: BorderSide(
                  color: isSelected
                      ? Colors.transparent
                      : Colors.grey.withOpacity(0.3),
                ),
              ),
            ).copyWith(
              backgroundColor: isSelected
                  ? MaterialStateProperty.all<Color>(AppTheme.primaryColor)
                  : MaterialStateProperty.all<Color>(Colors.transparent),
            ),
            child: Text(
              period.displayName,
              style: TextStyle(
                fontSize: 13,
                fontWeight: isSelected ? FontWeight.bold : FontWeight.normal,
              ),
            ),
          ),
        );
      }).toList(),
    );
  }
  
  Widget _buildKPICards(dynamic summary) {
    return GridView.count(
      crossAxisCount: 2,
      shrinkWrap: true,
      physics: NeverScrollableScrollPhysics(),
      crossAxisSpacing: 16,
      mainAxisSpacing: 16,
      childAspectRatio: 1.1,
      children: [
        KPICard(
          title: 'Total Users',
          value: '${summary.totalUsers}',
          gradientColors: AppTheme.blueGradient,
        ),
        KPICard(
          title: 'Organizations',
          value: '${summary.uniqueOrganizations}',
          gradientColors: AppTheme.purpleGradient,
        ),
        KPICard(
          title: 'Top Domain',
          value: summary.topDomain,
          subtitle: 'Primary sector',
          gradientColors: AppTheme.orangeGradient,
        ),
        KPICard(
          title: 'Top City',
          value: summary.topCity,
          subtitle: 'Leading region',
          gradientColors: AppTheme.greenGradient,
        ),
      ],
    );
  }
}
