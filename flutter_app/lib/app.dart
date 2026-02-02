import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'utils/theme.dart';
import 'viewmodels/login_viewmodel.dart';
import 'viewmodels/dashboard_viewmodel.dart';
import 'services/auth_service.dart';
import 'views/login_screen.dart';
import 'views/dashboard_screen.dart';

/// Main app widget
class GenAIAcademyApp extends StatefulWidget {
  const GenAIAcademyApp({Key? key}) : super(key: key);
  
  @override
  State<GenAIAcademyApp> createState() => _GenAIAcademyAppState();
}

class _GenAIAcademyAppState extends State<GenAIAcademyApp> {
  final _authService = AuthService();
  bool _isCheckingAuth = true;
  bool _isAuthenticated = false;
  
  @override
  void initState() {
    super.initState();
    _checkAuth();
  }
  
  Future<void> _checkAuth() async {
    final authenticated = await _authService.checkAutoLogin();
    setState(() {
      _isAuthenticated = authenticated;
      _isCheckingAuth = false;
    });
  }
  
  @override
  Widget build(BuildContext context) {
    return MultiProvider(
      providers: [
        ChangeNotifierProvider(create: (_) => LoginViewModel()),
        ChangeNotifierProvider(create: (_) => DashboardViewModel()),
      ],
      child: MaterialApp(
        title: 'Gen AI Academy Dashboard',
        debugShowCheckedModeBanner: false,
        theme: AppTheme.lightTheme,
        darkTheme: AppTheme.darkTheme,
        themeMode: ThemeMode.system,
        home: _isCheckingAuth
            ? Scaffold(
                body: Center(
                  child: CircularProgressIndicator(),
                ),
              )
            : _isAuthenticated
                ? DashboardScreen()
                : LoginScreen(),
      ),
    );
  }
}
