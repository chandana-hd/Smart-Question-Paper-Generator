from supabase_service import SupabaseService

# Initialize Supabase service
supabase_service = SupabaseService()

try:
    # Check if the paper exists
    paper_id = 'oWobgubSu37xCbi4oky3'
    print(f'Checking paper ID: {paper_id}')
    
    # Try to find the paper in saved_question_papers
    paper_result = supabase_service.supabase.table('saved_question_papers').select('*').eq('id', paper_id).execute()
    if paper_result.data:
        paper = paper_result.data[0]
        print(f'Paper found in Supabase:')
        print(f'  Name: {paper.get("paper_name", "N/A")}')
        print(f'  Subject: {paper.get("subject", "N/A")}')
        print(f'  User ID: {paper.get("user_id", "N/A")}')
        print(f'  Status: {paper.get("status", "N/A")}')
    else:
        print('Paper not found in Supabase saved_question_papers')
        
        # Check if it's a Firebase paper ID by looking for firebase_paper_id
        firebase_result = supabase_service.supabase.table('saved_question_papers').select('*').eq('firebase_paper_id', paper_id).execute()
        if firebase_result.data:
            paper = firebase_result.data[0]
            print(f'Paper found with Firebase ID:')
            print(f'  Name: {paper.get("paper_name", "N/A")}')
            print(f'  Subject: {paper.get("subject", "N/A")}')
            print(f'  User ID: {paper.get("user_id", "N/A")}')
        else:
            print('Paper not found with Firebase ID either')
            
    # Check all papers to see what's available
    all_papers = supabase_service.supabase.table('saved_question_papers').select('id, paper_name, subject, user_id, firebase_paper_id').limit(10).execute()
    print(f'\nRecent papers in Supabase:')
    for paper in all_papers.data:
        print(f'  {paper["id"]}: {paper.get("paper_name", "N/A")} - {paper.get("subject", "N/A")} (Firebase: {paper.get("firebase_paper_id", "None")})')
        
except Exception as e:
    print(f'Error: {e}')
