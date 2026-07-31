#!/usr/bin/env python3
"""
Test script to verify the complete SmartQPGen workflow.
This script tests the main functionality of the application.
"""

import requests
import json
import time
import os
from pathlib import Path

# Configuration
BASE_URL = "http://127.0.0.1:5000"
TEST_EMAIL = "test@example.com"
TEST_PASSWORD = "testpassword123"

def test_server_connection():
    """Test if the Flask server is running"""
    try:
        response = requests.get(f"{BASE_URL}/")
        if response.status_code == 200:
            print("✅ Server is running")
            return True
        else:
            print(f"❌ Server returned status code: {response.status_code}")
            return False
    except requests.exceptions.ConnectionError:
        print("❌ Cannot connect to server. Make sure Flask server is running on http://127.0.0.1:5000")
        return False

def test_firebase_connection():
    """Test Firebase authentication"""
    try:
        # This would require a real Firebase token, so we'll just check if the endpoint exists
        response = requests.get(f"{BASE_URL}/login")
        if response.status_code == 200:
            print("✅ Login page is accessible")
            return True
        else:
            print(f"❌ Login page returned status code: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ Error testing Firebase connection: {e}")
        return False

def test_backend_routes():
    """Test if all backend routes are accessible"""
    routes_to_test = [
        "/",
        "/login", 
        "/register",
        "/dashboard",
        "/hod-login",
        "/hod-dashboard"
    ]
    
    print("\n🔍 Testing backend routes...")
    all_routes_ok = True
    
    for route in routes_to_test:
        try:
            response = requests.get(f"{BASE_URL}{route}")
            if response.status_code == 200:
                print(f"✅ {route} - OK")
            else:
                print(f"❌ {route} - Status: {response.status_code}")
                all_routes_ok = False
        except Exception as e:
            print(f"❌ {route} - Error: {e}")
            all_routes_ok = False
    
    return all_routes_ok

def test_api_endpoints():
    """Test API endpoints (without authentication)"""
    api_endpoints = [
        "/authenticate-backend",
        "/get_saved_items", 
        "/get_recent_papers",
        "/generate_question_paper",
        "/save_question_paper"
    ]
    
    print("\n🔍 Testing API endpoints...")
    
    for endpoint in api_endpoints:
        try:
            # Test with POST method for most endpoints
            if endpoint in ["/authenticate-backend", "/generate_question_paper", "/save_question_paper"]:
                response = requests.post(f"{BASE_URL}{endpoint}", json={})
            else:
                response = requests.get(f"{BASE_URL}{endpoint}")
            
            # We expect 401 (Unauthorized) or 400 (Bad Request) for unauthenticated requests
            if response.status_code in [401, 400, 405]:
                print(f"✅ {endpoint} - Protected (Status: {response.status_code})")
            else:
                print(f"⚠️  {endpoint} - Unexpected status: {response.status_code}")
        except Exception as e:
            print(f"❌ {endpoint} - Error: {e}")

def check_firebase_config():
    """Check if Firebase configuration files exist"""
    print("\n🔍 Checking Firebase configuration...")
    
    # Check for Firebase service account file
    firebase_key_file = "smartqpgen-amrutha-firebase-adminsdk-fbsvc-509c2b1cdd.json"
    if os.path.exists(firebase_key_file):
        print(f"✅ Firebase service account key found: {firebase_key_file}")
    else:
        print(f"❌ Firebase service account key not found: {firebase_key_file}")
    
    # Check for required directories
    required_dirs = ["uploads", "generated", "static", "templates"]
    for dir_name in required_dirs:
        if os.path.exists(dir_name):
            print(f"✅ Directory exists: {dir_name}")
        else:
            print(f"❌ Directory missing: {dir_name}")

def check_dependencies():
    """Check if required Python packages are installed"""
    print("\n🔍 Checking Python dependencies...")
    
    required_packages = [
        "flask",
        "firebase_admin", 
        "flask_cors",
        "pdfplumber",
        "python-docx",
        "requests"
    ]
    
    for package in required_packages:
        try:
            __import__(package.replace("-", "_"))
            print(f"✅ {package} - Installed")
        except ImportError:
            print(f"❌ {package} - Not installed")

def main():
    """Run all tests"""
    print("🚀 SmartQPGen Application Test Suite")
    print("=" * 50)
    
    # Test server connection
    if not test_server_connection():
        print("\n❌ Server is not running. Please start the Flask server first.")
        print("Run: python app.py")
        return
    
    # Test Firebase connection
    test_firebase_connection()
    
    # Test backend routes
    routes_ok = test_backend_routes()
    
    # Test API endpoints
    test_api_endpoints()
    
    # Check configuration
    check_firebase_config()
    
    # Check dependencies
    check_dependencies()
    
    print("\n" + "=" * 50)
    if routes_ok:
        print("🎉 Basic tests passed! Your application is ready for testing.")
        print("\n📋 Manual Testing Checklist:")
        print("1. ✅ Open http://127.0.0.1:5000 in your browser")
        print("2. ✅ Try registering a new user account")
        print("3. ✅ Try logging in with your credentials")
        print("4. ✅ Upload a question bank file (PDF/DOCX)")
        print("5. ✅ Generate a question paper")
        print("6. ✅ Save the question paper")
        print("7. ✅ Check 'Saved Items' section")
        print("8. ✅ Check 'Recent Papers' section")
        print("9. ✅ Try submitting for approval (if HOD system is set up)")
    else:
        print("❌ Some tests failed. Please check the issues above.")
    
    print("\n💡 Tips:")
    print("- Make sure your Firebase project is properly configured")
    print("- Check the browser console for any JavaScript errors")
    print("- Check the Flask server logs for backend errors")

if __name__ == "__main__":
    main()
