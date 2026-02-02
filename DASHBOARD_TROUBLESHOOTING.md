# Dashboard Data Not Showing - Troubleshooting Guide

## Problem
Dashboard shows all zeros and "No data available" messages even though the database has 705 records.

## Root Cause
The frontend JavaScript is making API calls to `/api/dashboard/summary` and `/api/dashboard/charts`, but these calls are likely failing due to:
1. **Not logged in** - No authentication token in browser
2. **Flask server not running** - Backend API is not accessible
3. **API authentication errors** - Token expired or invalid

## Quick Fix Steps

### Step 1: Verify Flask Server is Running
```bash
# Check if server is running on port 3002
# If not, start it:
python server/app.py
# OR
python run.py
```

### Step 2: Verify You're Logged In
1. Open browser DevTools (F12)
2. Go to **Application** tab (Chrome) or **Storage** tab (Firefox)
3. Check **Local Storage** for `http://localhost:3002`
4. Verify you have:
   - `token` - Should be a long string
   - `user` - Should be a JSON object

**If missing:**
- Go to `/login` page
- Log in with your credentials
- If you don't have credentials, create an admin user:
  ```bash
  python setup_admin.py
  ```

### Step 3: Check Browser Console for Errors
1. Open DevTools (F12)
2. Go to **Console** tab
3. Look for red error messages
4. Common errors:
   - `Failed to load dashboard data` - API call failed
   - `Not authenticated` - No token in localStorage
   - `401 Unauthorized` - Token expired or invalid
   - `Network error` - Flask server not running

### Step 4: Check Network Requests
1. Open DevTools (F12)
2. Go to **Network** tab
3. Refresh the dashboard page
4. Look for requests to:
   - `/api/dashboard/summary?period=30d`
   - `/api/dashboard/charts?period=30d`
5. Check the status:
   - **200 OK** = Request successful (but might return empty data)
   - **401 Unauthorized** = Authentication failed
   - **500 Internal Server Error** = Backend error
   - **Failed/Blocked** = Server not running or CORS issue

### Step 5: Test API Endpoints Directly
Run the diagnostic script:
```bash
python test_api.py
```

This will test:
- Login endpoint
- Dashboard summary endpoint
- Dashboard charts endpoint

## Database Status
✅ **Database Connection**: Working
✅ **Tables**: Created (users, user_pii)
✅ **Data**: 705 records in user_pii table

## Common Solutions

### Solution 1: Re-login
If token expired:
1. Go to `/login`
2. Log in again
3. Dashboard should refresh automatically

### Solution 2: Clear Browser Cache
1. Open DevTools (F12)
2. Right-click refresh button
3. Select "Empty Cache and Hard Reload"

### Solution 3: Check Flask Server Logs
When running `python server/app.py`, you should see:
- `[OK] Database tables initialized`
- API request logs when you access the dashboard

If you see errors, check:
- Database connection string in `.env`
- PostgreSQL is running
- Database `academy_apac` exists

### Solution 4: Verify API Endpoints Work
Test manually with curl (if you have a token):
```bash
# Get token first by logging in
curl -X POST http://localhost:3002/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"your-email","password":"your-password"}'

# Then test dashboard endpoint (replace TOKEN with actual token)
curl http://localhost:3002/api/dashboard/summary?period=30d \
  -H "Authorization: Bearer TOKEN"
```

## Expected Behavior

When everything works:
1. Dashboard loads
2. KPI cards show numbers (not zeros)
3. Charts display data
4. No "No data available" messages

## Still Not Working?

1. **Check Flask server is running** on port 3002
2. **Verify you're logged in** (check localStorage)
3. **Check browser console** for JavaScript errors
4. **Check Network tab** for failed API requests
5. **Run diagnostic scripts**:
   ```bash
   python check_database.py  # Check database
   python test_api.py        # Test API endpoints
   ```

## Next Steps
If data still doesn't show after following these steps, the issue might be:
- Date filtering (all 705 records might be outside the selected period)
- Data format issues in the database
- Backend query errors

Check the Flask server console for any error messages when accessing the dashboard.
