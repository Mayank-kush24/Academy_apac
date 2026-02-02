# Flutter App Deployment Guide

## Prerequisites

1. **Flutter SDK**: Install Flutter 3.0.0 or higher
2. **Dependencies**: Run `flutter pub get` in the `flutter_app` directory
3. **Code Generation**: Run `flutter pub run build_runner build --delete-conflicting-outputs`

## Configuration

### 1. Update API URL

Edit `lib/utils/constants.dart`:

```dart
static const String baseURL = 'http://YOUR_SERVER_IP:3002/api';
```

**Important URLs:**
- **Android Emulator**: `http://10.0.2.2:3002/api`
- **iOS Simulator**: `http://localhost:3002/api`
- **Physical Device**: `http://YOUR_COMPUTER_IP:3002/api`

### 2. Generate JSON Code

```bash
cd flutter_app
flutter pub run build_runner build --delete-conflicting-outputs
```

## Running the App

### Development Mode

```bash
flutter run
```

### Android

```bash
# Debug
flutter run -d android

# Release APK
flutter build apk --release

# Release App Bundle (for Play Store)
flutter build appbundle --release
```

### iOS

```bash
# Debug
flutter run -d ios

# Release (requires macOS and Xcode)
flutter build ios --release
```

Then open `ios/Runner.xcworkspace` in Xcode to archive and upload.

## Widget Setup

### iOS Widget

1. Open `ios/Runner.xcworkspace` in Xcode
2. File → New → Target → Widget Extension
3. Configure App Groups: `group.com.genaiacademy.dashboard`
4. Build and run

### Android Widget

The `home_widget` package handles Android widgets automatically. No additional setup required.

## Testing Checklist

- [ ] Login with valid credentials
- [ ] Auto-login on app restart
- [ ] Dashboard loads with KPI cards
- [ ] Period selector works (7d, 30d, 90d)
- [ ] Pull-to-refresh works
- [ ] Logout functionality
- [ ] Widget displays on home screen (iOS/Android)
- [ ] Widget updates with latest data

## Troubleshooting

### Build Errors

```bash
flutter clean
flutter pub get
flutter pub run build_runner build --delete-conflicting-outputs
```

### Missing Generated Files

Ensure you've run the build_runner command to generate `.g.dart` files.

### Network Errors

- Check API URL in `constants.dart`
- Ensure Flask server is running
- Verify network connectivity
- For Android emulator, use `10.0.2.2` instead of `localhost`

### Widget Not Working

- Check App Groups configuration (iOS)
- Verify token is stored in shared preferences
- Check widget permissions in device settings
