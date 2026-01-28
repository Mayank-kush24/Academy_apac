# Gen AI Academy Dashboard - iOS App

Native iOS application for the Gen AI Academy APAC Dashboard, built with SwiftUI.

## Features

- 🔐 JWT-based authentication with secure token storage
- 📊 Dashboard with KPI cards showing key metrics
- 🔄 Pull-to-refresh functionality
- ⏱️ Time period selection (7d, 30d, 90d)
- 📱 iOS Home Screen Widget
- 🌓 Dark mode support
- 🎨 Modern glassmorphism UI design

## Requirements

- iOS 17.0+
- Xcode 15.0+
- macOS 14.0+ (for development)
- Free Apple Developer account (for device testing)

## Project Structure

```
GenAIAcademyDashboard/
├── GenAIAcademyDashboard/          # Main app
│   ├── App/                        # App entry point
│   ├── Views/                      # SwiftUI views
│   ├── ViewModels/                 # MVVM view models
│   ├── Models/                     # Data models
│   ├── Services/                   # Network, Auth, Keychain
│   └── Utils/                      # Constants and utilities
└── GenAIAcademyWidget/             # Widget extension
    ├── WidgetTimelineProvider.swift
    ├── WidgetView.swift
    └── GenAIAcademyWidget.swift
```

## Setup Instructions

### 1. Open in Xcode

1. Open Xcode
2. File → Open → Select the `ios_app` folder
3. Wait for Xcode to index files

### 2. Configure API URL

Edit `GenAIAcademyDashboard/Utils/Constants.swift`:

```swift
static let baseURL = "http://YOUR_SERVER_IP:3002/api"
```

For localhost testing on iPhone:
- Ensure iPhone and Mac are on the same Wi-Fi network
- Find your Mac's IP address: System Settings → Network
- Use: `http://192.168.1.XXX:3002/api`

### 3. Configure Signing

1. Select project in navigator
2. Select target "GenAIAcademyDashboard"
3. Go to "Signing & Capabilities"
4. Check "Automatically manage signing"
5. Select your Team (Apple ID)

### 4. Configure App Groups (for Widget)

1. In "Signing & Capabilities" for main app
2. Click "+ Capability"
3. Add "App Groups"
4. Create: `group.com.genaiacademy.dashboard`
5. Repeat for Widget target

### 5. Build and Run

1. Connect iPhone via USB
2. Select iPhone from device dropdown
3. Click Play (▶️) or press Cmd+R
4. First launch: Settings → General → VPN & Device Management → Trust developer

## Widget Setup

1. After installing app, long press on home screen
2. Tap "+" to add widget
3. Search for "Gen AI Academy"
4. Select size (Small or Medium)
5. Add to home screen

## API Endpoints Used

- `POST /api/auth/login` - User authentication
- `GET /api/auth/me` - Get current user info
- `GET /api/dashboard/summary?period=30d` - Dashboard summary
- `GET /api/dashboard/charts?period=30d` - Chart data
- `GET /api/dashboard/widget-stats` - Widget statistics

## Architecture

- **MVVM**: ViewModels manage business logic
- **Services**: NetworkManager, AuthService, KeychainService
- **SwiftUI**: Modern declarative UI framework
- **WidgetKit**: iOS Home Screen Widgets

## Security

- JWT tokens stored securely in iOS Keychain
- No sensitive data in UserDefaults
- HTTPS recommended for production

## Troubleshooting

### "Invalid URL" Error
- Check `Constants.swift` baseURL
- Ensure Flask server is running
- Verify network connectivity

### Widget Not Updating
- Check App Groups configuration
- Verify token is stored in shared container
- Check widget refresh policy (30 minutes)

### Build Errors
- Clean build folder: Cmd+Shift+K
- Delete derived data
- Restart Xcode

## Future Enhancements

- [ ] Real-time updates with polling
- [ ] Push notifications
- [ ] Offline caching
- [ ] Charts visualization
- [ ] Role-based dashboard views

## License

Created for Gen AI Academy APAC Edition
