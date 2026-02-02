import 'package:flutter/material.dart';
import 'package:home_widget/home_widget.dart';
import 'app.dart';
import 'services/widget_service.dart';

void main() async {
  WidgetsFlutterBinding.ensureInitialized();
  
  // Initialize home widget
  await HomeWidget.setAppGroupId('group.com.genaiacademy.dashboard');
  
  // Update widget on app start
  final widgetService = WidgetService();
  widgetService.updateWidget();
  
  runApp(const GenAIAcademyApp());
}
