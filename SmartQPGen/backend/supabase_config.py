"""
Supabase configuration and client setup
"""
import os
from supabase import create_client, Client

# Supabase configuration
SUPABASE_URL = "https://okhempjtwtfmwxunkmcj.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Im9raGVtcGp0d3RmbXd4dW5rbWNqIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NTc3NzYwMTksImV4cCI6MjA3MzM1MjAxOX0._M5VzJjpCRECtsAovNlrOFmel84_-BxygU8F6Q1nXv8"

# Create Supabase client
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# Database table names
TABLES = {
    'users': 'users',
    'saved_question_papers': 'saved_question_papers',
    'approvals': 'approvals',
    'question_banks': 'question_banks'
}

def get_supabase_client():
    """Get the Supabase client instance"""
    return supabase

def test_connection():
    """Test Supabase connection"""
    try:
        # Try to fetch from a simple table or create a test query
        result = supabase.table('users').select('*').limit(1).execute()
        print("✅ Supabase connection successful!")
        return True
    except Exception as e:
        print(f"❌ Supabase connection failed: {e}")
        return False

if __name__ == "__main__":
    test_connection()
