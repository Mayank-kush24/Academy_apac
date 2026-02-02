# Flutter Installation Guide for Windows

## Step 1: Download Flutter SDK

1. Go to [https://flutter.dev/docs/get-started/install/windows](https://flutter.dev/docs/get-started/install/windows)
2. Download the latest stable Flutter SDK (ZIP file)
3. Extract the ZIP file to a location like:
   - `C:\src\flutter` (recommended)
   - Or `D:\flutter`
   - **Important**: Do NOT install in `C:\Program Files\` (permissions issues)

## Step 2: Add Flutter to PATH

### Option A: Using System Environment Variables (Recommended)

1. Press `Win + X` and select "System"
2. Click "Advanced system settings"
3. Click "Environment Variables"
4. Under "User variables", find "Path" and click "Edit"
5. Click "New" and add: `C:\src\flutter\bin` (or your Flutter path)
6. Click "OK" on all dialogs
7. **Close and reopen** your terminal/PowerShell

### Option B: Using PowerShell (Temporary - for current session only)

```powershell
$env:Path += ";C:\src\flutter\bin"
```

## Step 3: Verify Installation

Open a **new** PowerShell window and run:

```powershell
flutter --version
```

You should see Flutter version information.

## Step 4: Run Flutter Doctor

```powershell
flutter doctor
```

This will check your setup and show what's missing.

### Common Issues and Fixes:

#### Missing Git
- Download Git from [https://git-scm.com/download/win](https://git-scm.com/download/win)
- Install and restart terminal

#### Missing Android Studio (for Android development)
- Download from [https://developer.android.com/studio](https://developer.android.com/studio)
- Install Android Studio
- Run `flutter doctor --android-licenses` and accept licenses

#### Missing VS Code / Android Studio (for development)
- VS Code: [https://code.visualstudio.com/](https://code.visualstudio.com/)
- Install Flutter extension in VS Code

## Step 5: Install Flutter Dependencies

Once Flutter is installed and in PATH:

```powershell
cd D:\Automation\academy_apac_python\flutter_app
flutter pub get
```

## Step 6: Generate JSON Code

```powershell
flutter pub run build_runner build --delete-conflicting-outputs
```

## Alternative: Use Flutter from Git (Advanced)

If you prefer to use Git:

```powershell
# Install Git first, then:
git clone https://github.com/flutter/flutter.git -b stable C:\src\flutter
```

Then add to PATH as described in Step 2.

## Quick Test

After installation, test Flutter:

```powershell
flutter doctor -v
flutter create test_app
cd test_app
flutter run
```

## Troubleshooting

### "flutter: command not found"
- Make sure you added Flutter to PATH
- **Close and reopen** your terminal
- Verify path: `echo $env:Path` (should include Flutter bin directory)

### "Unable to find git"
- Install Git from [https://git-scm.com/download/win](https://git-scm.com/download/win)
- Restart terminal

### Permission Errors
- Don't install Flutter in `C:\Program Files\`
- Use `C:\src\flutter` or `D:\flutter` instead

## Next Steps

After Flutter is installed:

1. Configure API URL in `lib/utils/constants.dart`
2. Run `flutter pub get`
3. Run `flutter pub run build_runner build --delete-conflicting-outputs`
4. Run `flutter run` to start the app
