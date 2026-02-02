# Gen AI Academy Dashboard - Flutter App

Cross-platform mobile application for the Gen AI Academy APAC Dashboard, built with Flutter for iOS and Android.

## Features

- 🔐 JWT-based authentication with secure token storage
- 📊 Dashboard with KPI cards showing key metrics
- 🔄 Pull-to-refresh functionality
- ⏱️ Time period selection (7d, 30d, 90d)
- 📱 Home Screen Widget (iOS and Android)
- 🌓 Dark mode support
- 🎨 Modern glassmorphism UI design

## Requirements

- Flutter SDK 3.0.0 or higher
- Dart SDK 3.0.0 or higher (included with Flutter)
- iOS 12.0+ (for iOS development - requires macOS)
- Android SDK 21+ (Android 5.0+)
- For iOS: macOS with Xcode (for building iOS app)
- For Android: Can develop on Windows/Mac/Linux

**Note**: If Flutter is not installed, see `FLUTTER_INSTALLATION.md` for installation instructions.

## Project Structure

```
flutter_app/
├── lib/
│   ├── main.dart                    # App entry point
│   ├── app.dart                     # Main app widget
│   ├── models/                      # Data models
│   │   ├── user.dart
│   │   ├── dashboard_summary.dart
│   │   ├── dashboard_charts.dart
│   │   └── widget_stats.dart
│   ├── services/                    # Business logic services
│   │   ├── auth_service.dart
│   │   ├── network_service.dart
│   │   ├── storage_service.dart
│   │   └── widget_service.dart
│   ├── viewmodels/                  # MVVM view models
│   │   ├── login_viewmodel.dart
│   │   └── dashboard_viewmodel.dart
│   ├── views/                       # UI screens
│   │   ├── login_screen.dart
│   │   ├── dashboard_screen.dart
│   │   └── widgets/                 # Reusable components
│   │       ├── kpi_card.dart
│   │       ├── loading_indicator.dart
│   │       └── error_view.dart
│   └── utils/
│       ├── constants.dart
│       └── theme.dart
├── android/                         # Android-specific config
├── ios/                             # iOS-specific config
└── pubspec.yaml                     # Dependencies
```

## Setup Instructions

### 1. Install Flutter

1. Download Flutter SDK from [flutter.dev](https://flutter.dev/docs/get-started/install)
2. Extract and add to PATH
3. Run `flutter doctor` to check installation

### 2. Configure API URL

Edit `lib/utils/constants.dart`:

```dart
static const String baseURL = 'http://YOUR_SERVER_IP:3002/api';
```

For localhost testing:
- **Android Emulator**: Use `http://10.0.2.2:3002/api`
- **iOS Simulator**: Use `http://localhost:3002/api`
- **Physical Device**: Use your computer's IP address (e.g., `http://192.168.1.XXX:3002/api`)

### 3. Install Dependencies

```bash
cd flutter_app
flutter pub get
```

### 4. Generate JSON Serialization Code

```bash
flutter pub run build_runner build --delete-conflicting-outputs
```

This generates the `.g.dart` files for models.

### 5. Configure Widget (Optional)

#### iOS Widget
1. Open `ios/Runner.xcworkspace` in Xcode
2. Add Widget Extension target
3. Configure App Groups: `group.com.genaiacademy.dashboard`

#### Android Widget
1. Widget is configured via `home_widget` package
2. Add widget provider in `AndroidManifest.xml`

### 6. Run the App

#### Android
```bash
flutter run
```

#### iOS
```bash
flutter run
```

Or open in Xcode:
```bash
open ios/Runner.xcworkspace
```

## API Endpoints

The app uses the following Flask API endpoints:

- `POST /api/auth/login` - User authentication
- `GET /api/auth/me` - Get current user info
- `GET /api/dashboard/summary?period=30d` - Dashboard summary
- `GET /api/dashboard/charts?period=30d` - Chart data
- `GET /api/dashboard/widget-stats` - Widget statistics

## Architecture

- **MVVM Pattern**: ViewModels manage business logic
- **Provider**: State management
- **Services**: NetworkManager, AuthService, StorageService
- **Flutter**: Cross-platform UI framework

## Security

- JWT tokens stored securely using `flutter_secure_storage`
- Tokens also shared via `shared_preferences` for widget access
- HTTPS recommended for production

## Building for Release

### Android
```bash
flutter build apk --release
# or
flutter build appbundle --release
```

### iOS
```bash
flutter build ios --release
```

Then open in Xcode to archive and upload to App Store.

## Troubleshooting

### "Invalid URL" Error
- Check `constants.dart` baseURL
- Ensure Flask server is running
- Verify network connectivity
- For Android emulator, use `10.0.2.2` instead of `localhost`

### Widget Not Updating
- Check App Groups configuration (iOS)
- Verify token is stored in shared preferences
- Check widget refresh policy (30 minutes)

### Build Errors
- Run `flutter clean`
- Run `flutter pub get`
- Run `flutter pub run build_runner build --delete-conflicting-outputs`
- Delete `build/` folder and rebuild

### JSON Serialization Errors
- Ensure you've run `build_runner` to generate `.g.dart` files
- Check that all models have `part` directives

## Development Tips

- Use `flutter run` with hot reload for faster development
- Check `flutter doctor` for any missing dependencies
- Use `flutter analyze` to check for code issues
- Test on both iOS and Android devices/emulators

## Future Enhancements

- [ ] Real-time updates with polling
- [ ] Push notifications
- [ ] Offline caching
- [ ] Charts visualization
- [ ] Role-based dashboard views
- [ ] Biometric authentication

## License

Created for Gen AI Academy APAC Edition
