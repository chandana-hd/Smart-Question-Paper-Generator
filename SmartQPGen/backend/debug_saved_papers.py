"""
Debug script to check saved papers
"""
import sys
sys.path.append('.')
from supabase_service import supabase_service

def debug_saved_papers():
    print('🔍 Checking Supabase saved papers...')
    
    # Get all users first
    try:
        users_result = supabase_service.supabase.table('users').select('*').execute()
        print(f"Found {len(users_result.data)} users in Supabase:")
        for user in users_result.data:
            print(f"  - {user['email']} (Firebase UID: {user['firebase_uid']})")
            
        # Check papers for each user
        for user in users_result.data:
            user_id = user['id']
            papers = supabase_service.get_saved_question_papers(user_id, limit=10)
            print(f"\nPapers for {user['email']}: {len(papers)} found")
            for paper in papers:
                print(f"  - {paper['paper_name']} (ID: {paper['id']})")
                
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    debug_saved_papers()
