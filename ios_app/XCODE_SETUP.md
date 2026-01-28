# Xcode Project Setup Instructions

Since you don't have a Mac yet, here are the steps to create the Xcode project structure when you get access to one.

## Quick Start

1. **Open Xcode**
2. **File → New → Project**
3. Select **iOS → App**
4. Configure:
   - Product Name: `GenAIAcademyDashboard`
   - Team: (Select your Apple ID)
   - Organization Identifier: `com.genaiacademy`
   - Interface: **SwiftUI**
   - Language: **Swift**
   - Storage: None
   - Include Tests: (Optional)
5. Click **Next** and save to a location

## Add Widget Extension

1. **File → New → Target**
2. Select **iOS → Widget Extension**
3. Configure:
   - Product Name: `GenAIAcademyWidget`
   - Include Configuration Intent: **No**
4. Click **Finish**
5. When prompted, click **Activate** for the scheme

## Copy Files

Copy all files from the `ios_app` folder into your Xcode project:

1. **Drag and drop** the folders into Xcode's Project Navigator
2. Make sure **"Copy items if needed"** is checked
3. Select your app target for main app files
4. Select widget target for widget files

## File Organization

Organize files in Xcode like this:

```
GenAIAcademyDashboard (Project)
├── GenAIAcademyDashboard (App Target)
│   ├── App
│   │   └── GenAIAcademyDashboardApp.swift
│   ├── Views
│   │   ├── LoginView.swift
│   │   ├── DashboardView.swift
│   │   └── Components
│   │       ├── KPICardView.swift
│   │       ├── LoadingView.swift
│   │       └── ErrorView.swift
│   ├── ViewModels
│   │   ├── LoginViewModel.swift
│   │   └── DashboardViewModel.swift
│   ├── Models
│   │   ├── User.swift
│   │   ├── DashboardSummary.swift
│   │   ├── DashboardCharts.swift
│   │   └── WidgetStats.swift
│   ├── Services
│   │   ├── NetworkManager.swift
│   │   ├── AuthService.swift
│   │   └── KeychainService.swift
│   └── Utils
│       └── Constants.swift
└── GenAIAcademyWidget (Widget Target)
    ├── GenAIAcademyWidget.swift
    ├── WidgetTimelineProvider.swift
    ├── WidgetView.swift
    └── Models
        └── WidgetStats.swift (shared with app)
```

## Configure Targets

### Main App Target

1. Select project → **GenAIAcademyDashboard** target
2. **General** tab:
   - Minimum Deployments: iOS 17.0
3. **Signing & Capabilities**:
   - Enable App Groups: `group.com.genaiacademy.dashboard`

### Widget Target

1. Select **GenAIAcademyWidget** target
2. **Signing & Capabilities**:
   - Enable App Groups: `group.com.genaiacademy.dashboard`
   - Same team as main app

## Build Settings

1. Select project in navigator
2. Go to **Build Settings**
3. Search for "Swift Language Version"
4. Set to **Swift 5.9** or latest

## Info.plist Configuration

For localhost testing, you may need to add:

```xml
<key>NSAppTransportSecurity</key>
<dict>
    <key>NSAllowsArbitraryLoads</key>
    <true/>
</dict>
```

**Note**: Only for development. Remove in production.

## Next Steps

After setup, follow the **DEPLOYMENT_GUIDE.md** for:
- Connecting iPhone
- Building and running
- Testing the app and widget
