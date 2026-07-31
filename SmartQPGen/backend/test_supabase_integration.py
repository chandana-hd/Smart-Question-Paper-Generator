"""
Test script for Supabase integration
"""
import sys
sys.path.append('.')
from supabase_service import supabase_service
import json

def test_supabase_integration():
    print("🧪 Testing Supabase Integration...")
    
    # Test 1: Create a test user
    print("\n1. Testing user creation...")
    test_user = supabase_service.create_user(
        firebase_uid="test_firebase_uid_123",
        email="test@example.com",
        name="Test User",
        role="faculty"
    )
    
    if test_user:
        print(f"✅ User created successfully: {test_user['id']}")
        user_id = test_user['id']
    else:
        print("❌ Failed to create user")
        return
    
    # Test 2: Save a test question paper
    print("\n2. Testing question paper save...")
    test_paper_data = {
        'firebase_paper_id': 'test_firebase_paper_123',
        'paper_name': 'Test Question Paper',
        'subject': 'Test Subject',
        'pattern': 'standard',
        'total_marks': 100,
        'question_count': 2,
        'questions': [
            {
                'main_question': 'Q1',
                'module': '1',
                'sub_questions': [
                    {'part': 'a', 'text': 'Test question 1a', 'marks': 25},
                    {'part': 'b', 'text': 'Test question 1b', 'marks': 25}
                ]
            },
            {
                'main_question': 'Q2',
                'module': '2',
                'sub_questions': [
                    {'part': 'a', 'text': 'Test question 2a', 'marks': 25},
                    {'part': 'b', 'text': 'Test question 2b', 'marks': 25}
                ]
            }
        ],
        'metadata': {'test': True},
        'status': 'draft',
        'tags': ['test', 'sample']
    }
    
    saved_paper = supabase_service.save_question_paper(user_id, test_paper_data)
    
    if saved_paper:
        print(f"✅ Question paper saved successfully: {saved_paper['id']}")
        paper_id = saved_paper['id']
    else:
        print("❌ Failed to save question paper")
        return
    
    # Test 3: Retrieve saved papers
    print("\n3. Testing question paper retrieval...")
    saved_papers = supabase_service.get_saved_question_papers(user_id)
    
    if saved_papers:
        print(f"✅ Retrieved {len(saved_papers)} saved papers")
        for paper in saved_papers:
            print(f"   - {paper['paper_name']} ({paper['status']})")
    else:
        print("❌ Failed to retrieve saved papers")
    
    # Test 4: Submit for approval
    print("\n4. Testing approval submission...")
    approval = supabase_service.submit_for_approval(paper_id, user_id, "Test approval submission")
    
    if approval:
        print(f"✅ Approval submitted successfully: {approval['id']}")
    else:
        print("❌ Failed to submit for approval")
    
    # Test 5: Get pending approvals
    print("\n5. Testing pending approvals retrieval...")
    pending_approvals = supabase_service.get_pending_approvals(user_id)
    
    if pending_approvals is not None:
        print(f"✅ Retrieved {len(pending_approvals)} pending approvals")
    else:
        print("❌ Failed to retrieve pending approvals")
    
    print("\n🎉 Supabase integration test completed!")

if __name__ == "__main__":
    test_supabase_integration()
