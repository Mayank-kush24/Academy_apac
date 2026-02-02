"""
Test API endpoints to verify they're working
"""
import requests
import json
import sys

BASE_URL = "http://localhost:3002"

def test_api():
    """Test dashboard API endpoints"""
    print("=" * 60)
    print("API ENDPOINT TEST")
    print("=" * 60)
    
    # First, try to login to get a token
    print("\n1. Testing login endpoint...")
    try:
        login_response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={
                "email": "admin@example.com",  # Change if needed
                "password": "admin123"  # Change if needed
            },
            headers={"Content-Type": "application/json"}
        )
        
        if login_response.status_code == 200:
            data = login_response.json()
            token = data.get('token')
            print(f"[OK] Login successful")
            print(f"    Token: {token[:20]}...")
        else:
            print(f"[ERROR] Login failed: {login_response.status_code}")
            print(f"    Response: {login_response.text}")
            print("\n   Note: You may need to create an admin user first:")
            print("   Run: python setup_admin.py")
            return
    except requests.exceptions.ConnectionError:
        print(f"[ERROR] Cannot connect to {BASE_URL}")
        print("   Make sure Flask server is running:")
        print("   Run: python server/app.py")
        return
    except Exception as e:
        print(f"[ERROR] Login error: {str(e)}")
        return
    
    # Test dashboard summary endpoint
    print("\n2. Testing dashboard summary endpoint...")
    try:
        summary_response = requests.get(
            f"{BASE_URL}/api/dashboard/summary?period=30d",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json"
            }
        )
        
        if summary_response.status_code == 200:
            summary = summary_response.json()
            print(f"[OK] Summary endpoint working")
            print(f"    Total Users: {summary.get('total_users', 0)}")
            print(f"    Organizations: {summary.get('unique_organizations', 0)}")
            print(f"    Top Domain: {summary.get('top_domain', 'N/A')}")
            print(f"    Top City: {summary.get('top_city', 'N/A')}")
        else:
            print(f"[ERROR] Summary endpoint failed: {summary_response.status_code}")
            print(f"    Response: {summary_response.text}")
    except Exception as e:
        print(f"[ERROR] Summary endpoint error: {str(e)}")
    
    # Test dashboard charts endpoint
    print("\n3. Testing dashboard charts endpoint...")
    try:
        charts_response = requests.get(
            f"{BASE_URL}/api/dashboard/charts?period=30d",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json"
            }
        )
        
        if charts_response.status_code == 200:
            charts = charts_response.json()
            print(f"[OK] Charts endpoint working")
            print(f"    Registration Trends: {len(charts.get('registration_trends', []))} data points")
            print(f"    Gender Distribution: {len(charts.get('gender_distribution', []))} categories")
            print(f"    Top Domains: {len(charts.get('top_domains', []))} items")
            print(f"    Top Cities: {len(charts.get('top_cities', []))} items")
            print(f"    Top Organizations: {len(charts.get('top_organizations', []))} items")
        else:
            print(f"[ERROR] Charts endpoint failed: {charts_response.status_code}")
            print(f"    Response: {charts_response.text}")
    except Exception as e:
        print(f"[ERROR] Charts endpoint error: {str(e)}")
    
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print("\nIf API tests pass but dashboard still shows no data:")
    print("  1. Open browser DevTools (F12)")
    print("  2. Check Console tab for JavaScript errors")
    print("  3. Check Network tab for failed API requests")
    print("  4. Verify localStorage has 'token' key")
    print("  5. Check if CORS is blocking requests")

if __name__ == '__main__':
    test_api()
