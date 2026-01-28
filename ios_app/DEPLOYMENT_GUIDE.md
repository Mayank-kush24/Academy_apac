# iOS App Deployment Guide

Complete step-by-step guide for deploying the Gen AI Academy Dashboard iOS app to your iPhone.

## Prerequisites

### Required Hardware
- **Mac Computer** (macOS 14.0 Sonoma or later)
  - If you don't have a Mac, consider:
    - Cloud Mac services (MacStadium, AWS Mac instances)
    - Renting/borrowing a Mac
    - Using a friend's Mac for initial setup
- **iPhone** (iOS 17.0 or later)
- **USB Cable** (Lightning or USB-C)

### Required Software
- **Xcode 15.0+** (free from Mac App Store)
- **Free Apple Developer Account** (uses your Apple ID)

## Step 1: Install Xcode

1. Open **App Store** on your Mac
2. Search for **"Xcode"**
3. Click **"Get"** or **"Install"**
4. Wait for installation (large download, ~15GB, may take 30-60 minutes)
5. Once installed, open Xcode from Applications
6. Accept license agreement if prompted
7. Install additional components if prompted

## Step 2: Create Apple Developer Account

1. Go to [developer.apple.com](https://developer.apple.com)
2. Click **"Account"** → **"Sign In"**
3. Use your existing **Apple ID** (the one you use for App Store)
4. Accept terms and conditions
5. **Note**: Free account works for testing on your own devices

## Step 3: Open Project in Xcode

1. Open **Xcode**
2. Click **File** → **Open** (or press `Cmd+O`)
3. Navigate to the `ios_app` folder
4. Select the folder and click **"Open"**
5. Wait for Xcode to index files (may take a few minutes)

**Important**: If you see "No such module" errors, wait for indexing to complete.

## Step 4: Configure Project Settings

### 4.1 Set Minimum iOS Version

1. Click on the project name in the left navigator (top item)
2. Select the **"GenAIAcademyDashboard"** target
3. Go to **"General"** tab
4. Under **"Minimum Deployments"**, set iOS to **17.0**

### 4.2 Configure Signing

1. Still in the target settings, go to **"Signing & Capabilities"** tab
2. Check **"Automatically manage signing"**
3. Under **"Team"**, select your Apple ID
4. Xcode will automatically create a provisioning profile

**If you see signing errors:**
- Make sure you're signed in with your Apple ID in Xcode → Settings → Accounts
- Try cleaning the build folder: `Cmd+Shift+K`

## Step 5: Configure App Groups (for Widget)

### For Main App:

1. In **"Signing & Capabilities"** tab
2. Click **"+ Capability"** button (top left)
3. Search for and add **"App Groups"**
4. Click **"+ Add"** next to App Groups
5. Enter: `group.com.genaiacademy.dashboard`
6. Check the box to enable it

### For Widget Extension:

1. Select **"GenAIAcademyWidget"** target
2. Go to **"Signing & Capabilities"**
3. Configure signing (same as main app)
4. Add **"App Groups"** capability
5. Add the same group: `group.com.genaiacademy.dashboard`
6. Make sure it's checked

## Step 6: Configure API URL

1. In Xcode navigator, find `GenAIAcademyDashboard/Utils/Constants.swift`
2. Open the file
3. Update the `baseURL`:

```swift
static let baseURL = "http://YOUR_MAC_IP:3002/api"
```

**To find your Mac's IP address:**
1. Open **System Settings** → **Network**
2. Click on your Wi-Fi connection
3. Note the IP address (e.g., `192.168.1.100`)
4. Use: `http://192.168.1.100:3002/api`

**Important**: 
- iPhone and Mac must be on the **same Wi-Fi network**
- Make sure your Flask server is running
- For production, use your production URL with HTTPS

## Step 7: Connect iPhone

1. **Unlock your iPhone**
2. Connect iPhone to Mac using USB cable
3. On iPhone, if prompted: **"Trust This Computer?"** → Tap **"Trust"**
4. Enter your iPhone passcode if prompted
5. In Xcode, look at the top toolbar
6. You should see your iPhone name in the device dropdown (next to the Play button)
7. Select your iPhone from the dropdown

**If iPhone doesn't appear:**
- Make sure iPhone is unlocked
- Try unplugging and reconnecting the cable
- Check if iPhone appears in Finder (should show up as a device)

## Step 8: Build and Run

1. In Xcode, click the **Play button (▶️)** or press `Cmd+R`
2. Xcode will:
   - Build the app
   - Install it on your iPhone
   - Launch it automatically

**First Launch on iPhone:**
1. You may see: **"Untrusted Developer"**
2. Go to: **Settings** → **General** → **VPN & Device Management**
3. Tap on your Apple ID email
4. Tap **"Trust [Your Name]"**
5. Tap **"Trust"** in the popup
6. Go back to the app and it should launch

## Step 9: Test the App

### Test Login:
1. Enter your email and password (same credentials as web app)
2. Tap **"Login"**
3. Should navigate to dashboard

### Test Dashboard:
1. Verify KPI cards show data
2. Try changing period (7d, 30d, 90d)
3. Pull down to refresh
4. Check if data updates

### Test Widget:
1. Go to iPhone home screen
2. **Long press** on empty area
3. Tap **"+"** button (top left)
4. Search for **"Gen AI Academy"**
5. Select widget size (Small or Medium)
6. Tap **"Add Widget"**
7. Widget should appear on home screen
8. Wait 30 minutes or manually refresh to see data update

## Step 10: Troubleshooting

### Build Errors

**"No such module" errors:**
- Clean build: `Cmd+Shift+K`
- Close and reopen Xcode
- Delete derived data: `~/Library/Developer/Xcode/DerivedData`

**Signing errors:**
- Make sure "Automatically manage signing" is checked
- Select correct Team
- Try removing and re-adding App Groups capability

### Runtime Errors

**"Invalid URL" error:**
- Check `Constants.swift` baseURL
- Ensure Flask server is running
- Verify Mac and iPhone are on same Wi-Fi
- Try pinging Mac IP from iPhone (use network tool app)

**"Unauthorized" error:**
- Token may have expired
- Try logging out and logging back in
- Check if Flask server is accepting requests

**Widget not showing data:**
- Check App Groups are configured for both app and widget
- Verify token is being saved (check UserDefaults in debugger)
- Widget refreshes every 30 minutes by default

### Network Issues

**Can't connect to localhost:**
- Use Mac's IP address, not "localhost"
- Ensure firewall allows connections on port 3002
- Check Flask CORS settings allow your iPhone's IP

**Connection timeout:**
- Verify Flask server is running: `python run.py`
- Check server logs for errors
- Try accessing API from Safari on iPhone: `http://YOUR_MAC_IP:3002/api/dashboard/summary`

## Step 11: Production Deployment (Optional)

For App Store distribution, you'll need:
1. **Paid Apple Developer Account** ($99/year)
2. Create App Store Connect listing
3. Archive and upload build
4. Submit for review

For now, the free account allows you to:
- Install on your own devices
- Test the app
- Use widgets
- Share with up to 100 testers via TestFlight (with free account)

## Additional Resources

- [Apple Developer Documentation](https://developer.apple.com/documentation/)
- [SwiftUI Tutorials](https://developer.apple.com/tutorials/swiftui)
- [WidgetKit Guide](https://developer.apple.com/documentation/widgetkit)

## Support

If you encounter issues:
1. Check Xcode console for error messages
2. Check Flask server logs
3. Verify all configuration steps
4. Review the README.md in ios_app folder

---

**Congratulations!** You've successfully deployed the iOS app to your iPhone. 🎉
