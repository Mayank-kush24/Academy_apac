# Flutter App Build Instructions

## Important: Generate JSON Serialization Code

Before running the app, you **must** generate the JSON serialization code for the models.

### Step 1: Install Dependencies

```bash
cd flutter_app
flutter pub get
```

### Step 2: Generate Code

```bash
flutter pub run build_runner build --delete-conflicting-outputs
```

This will generate the following files:
- `lib/models/user.g.dart`
- `lib/models/dashboard_summary.g.dart`
- `lib/models/dashboard_charts.g.dart`
- `lib/models/widget_stats.g.dart`

### Step 3: Configure API URL

Edit `lib/utils/constants.dart` and update the `baseURL`:

```dart
static const String baseURL = 'http://YOUR_SERVER_IP:3002/api';
```

### Step 4: Run the App

```bash
flutter run
```

## Troubleshooting

If you see errors about missing `.g.dart` files, make sure you've run the build_runner command above.

If you see import errors, ensure all dependencies are installed with `flutter pub get`.
