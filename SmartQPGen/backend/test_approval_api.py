"""
Test script to verify the approval API endpoint is working
"""
import requests
import json

def test_approval_api():
    """Test the approval API endpoint"""
    print("🧪 TESTING APPROVAL API ENDPOINT")
    print("=" * 40)
    
    base_url = "http://localhost:5000"
    
    # Test data for approval submission
    test_approval_data = {
        "paper_id": "test_paper_123",
        "comments": "This is a test approval submission"
    }
    
    print("📋 Test Data:")
    print(f"   Paper ID: {test_approval_data['paper_id']}")
    print(f"   Comments: {test_approval_data['comments']}")
    
    print("\n🔍 Testing API Endpoint: POST /submit_for_approval")
    
    try:
        # Note: This will fail without proper authentication
        # But we can test the endpoint structure
        response = requests.post(
            f"{base_url}/submit_for_approval",
            json=test_approval_data,
            headers={'Content-Type': 'application/json'},
            timeout=10
        )
        
        print(f"   Status Code: {response.status_code}")
        print(f"   Response: {response.text[:200]}...")
        
        if response.status_code == 401:
            print("   ✅ Expected: Authentication required (401)")
        elif response.status_code == 200:
            print("   ✅ Success: Approval submitted")
        else:
            print(f"   ⚠️  Unexpected status: {response.status_code}")
            
    except requests.exceptions.ConnectionError:
        print("   ❌ Error: Cannot connect to server")
        print("   💡 Make sure the backend server is running: python app.py")
    except requests.exceptions.Timeout:
        print("   ❌ Error: Request timed out")
    except Exception as e:
        print(f"   ❌ Error: {e}")
    
    print("\n🔧 API Endpoint Details:")
    print("   Method: POST")
    print("   URL: /submit_for_approval")
    print("   Headers: Content-Type: application/json, Authorization: Bearer <token>")
    print("   Body: { paper_id: string, comments: string }")
    
    print("\n📊 Expected Response (Success):")
    print("   Status: 200")
    print("   Body: {")
    print("     'message': 'Question paper submitted for approval successfully!',")
    print("     'approval_id': '<uuid>',")
    print("     'status': 'pending_approval'")
    print("   }")
    
    print("\n📊 Expected Response (Error):")
    print("   Status: 404/500")
    print("   Body: { 'error': '<error_message>' }")
    
    print("\n✅ API Test completed!")
    print("💡 To test with real data, ensure:")
    print("   1. Backend server is running")
    print("   2. User is authenticated")
    print("   3. Paper exists in Supabase or Firebase")
    print("   4. Supabase connection is working")

if __name__ == "__main__":
    test_approval_api()

