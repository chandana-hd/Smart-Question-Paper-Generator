"""
Supabase service class for database operations
"""
from datetime import datetime
from typing import List, Dict, Optional, Any
from supabase_config import get_supabase_client, TABLES
import json

class SupabaseService:
    def __init__(self):
        self.supabase = get_supabase_client()
    
    def create_user(self, firebase_uid: str, email: str, name: str = None, role: str = 'faculty', department: str = None) -> Dict:
        """Create or update user in Supabase"""
        try:
            # Check if user exists
            existing_user = self.supabase.table(TABLES['users']).select('*').eq('firebase_uid', firebase_uid).execute()
            
            if existing_user.data:
                # Update existing user
                user_data = {
                    'email': email,
                    'name': name,
                    'role': role,
                    'department': department,
                    'updated_at': datetime.utcnow().isoformat()
                }
                result = self.supabase.table(TABLES['users']).update(user_data).eq('firebase_uid', firebase_uid).execute()
                return result.data[0] if result.data else None
            else:
                # Create new user
                user_data = {
                    'firebase_uid': firebase_uid,
                    'email': email,
                    'name': name,
                    'role': role,
                    'department': department
                }
                result = self.supabase.table(TABLES['users']).insert(user_data).execute()
                return result.data[0] if result.data else None
        except Exception as e:
            print(f"Error creating/updating user: {e}")
            return None
    
    def get_user_by_firebase_uid(self, firebase_uid: str) -> Optional[Dict]:
        """Get user by Firebase UID"""
        try:
            result = self.supabase.table(TABLES['users']).select('*').eq('firebase_uid', firebase_uid).execute()
            return result.data[0] if result.data else None
        except Exception as e:
            print(f"Error getting user: {e}")
            return None
    
    def save_question_paper(self, user_id: str, paper_data: Dict) -> Optional[Dict]:
        """Save question paper to Supabase"""
        try:
            # Prepare data for Supabase
            supabase_data = {
                'user_id': user_id,
                'firebase_paper_id': paper_data.get('firebase_paper_id'),
                'paper_name': paper_data.get('paper_name', 'Untitled Question Paper'),
                'subject': paper_data.get('subject', 'Unknown Subject'),
                'pattern': paper_data.get('pattern', 'standard'),
                'total_marks': paper_data.get('total_marks', 100),
                'question_count': paper_data.get('question_count', 0),
                'questions': paper_data.get('questions', []),
                'metadata': paper_data.get('metadata', {}),
                'status': paper_data.get('status', 'draft'),
                'tags': paper_data.get('tags', [])
            }
            
            result = self.supabase.table(TABLES['saved_question_papers']).insert(supabase_data).execute()
            return result.data[0] if result.data else None
        except Exception as e:
            print(f"Error saving question paper: {e}")
            return None
    
    def get_saved_question_papers(self, user_id: str, limit: int = 50, offset: int = 0) -> List[Dict]:
        """Get saved question papers for a user"""
        try:
            result = self.supabase.table(TABLES['saved_question_papers'])\
                .select('*')\
                .eq('user_id', user_id)\
                .order('created_at', desc=True)\
                .range(offset, offset + limit - 1)\
                .execute()
            return result.data or []
        except Exception as e:
            print(f"Error getting saved papers: {e}")
            return []
    
    def get_question_paper_by_id(self, paper_id: str, user_id: str) -> Optional[Dict]:
        """Get a specific question paper by ID"""
        try:
            result = self.supabase.table(TABLES['saved_question_papers'])\
                .select('*')\
                .eq('id', paper_id)\
                .eq('user_id', user_id)\
                .execute()
            return result.data[0] if result.data else None
        except Exception as e:
            print(f"Error getting question paper: {e}")
            return None
    
    def update_question_paper(self, paper_id: str, user_id: str, update_data: Dict) -> Optional[Dict]:
        """Update a question paper"""
        try:
            result = self.supabase.table(TABLES['saved_question_papers'])\
                .update(update_data)\
                .eq('id', paper_id)\
                .eq('user_id', user_id)\
                .execute()
            return result.data[0] if result.data else None
        except Exception as e:
            print(f"Error updating question paper: {e}")
            return None
    
    def delete_question_paper(self, paper_id: str, user_id: str) -> bool:
        """Delete a question paper"""
        try:
            result = self.supabase.table(TABLES['saved_question_papers'])\
                .delete()\
                .eq('id', paper_id)\
                .eq('user_id', user_id)\
                .execute()
            return True
        except Exception as e:
            print(f"Error deleting question paper: {e}")
            return False
    
    def submit_for_approval(self, paper_id: str, user_id: str, comments: str = '') -> Optional[Dict]:
        """Submit a question paper for HOD approval"""
        try:
            # Update paper status
            self.supabase.table(TABLES['saved_question_papers'])\
                .update({'status': 'submitted'})\
                .eq('id', paper_id)\
                .eq('user_id', user_id)\
                .execute()
            
            # Create approval record
            approval_data = {
                'paper_id': paper_id,
                'submitted_by': user_id,
                'comments': comments,
                'status': 'pending'
            }
            
            result = self.supabase.table(TABLES['approvals']).insert(approval_data).execute()
            return result.data[0] if result.data else None
        except Exception as e:
            print(f"Error submitting for approval: {e}")
            return None
    
    def get_pending_approvals(self, hod_user_id: str) -> List[Dict]:
        """Get pending approvals for HOD"""
        try:
            # Get all pending approvals
            approvals_result = self.supabase.table(TABLES['approvals'])\
                .select('*')\
                .eq('status', 'pending')\
                .execute()
            
            if not approvals_result.data:
                return []
            
            # For each approval, get the paper and user details separately
            formatted_approvals = []
            for approval in approvals_result.data:
                # Get paper details
                paper_result = self.supabase.table(TABLES['saved_question_papers'])\
                    .select('*')\
                    .eq('id', approval['paper_id'])\
                    .execute()
                
                # Get user details
                user_result = self.supabase.table(TABLES['users'])\
                    .select('*')\
                    .eq('id', approval['submitted_by'])\
                    .execute()
                
                # Combine the data
                paper_data = paper_result.data[0] if paper_result.data else {}
                user_data = user_result.data[0] if user_result.data else {}
                
                formatted_approval = {
                    **approval,
                    'saved_question_papers': paper_data,
                    'users': user_data
                }
                formatted_approvals.append(formatted_approval)
            
            return formatted_approvals
        except Exception as e:
            print(f"Error getting pending approvals: {e}")
            return []
    
    def approve_paper(self, approval_id: str, hod_user_id: str, hod_comments: str = '') -> bool:
        """Approve a question paper"""
        try:
            # Update approval
            self.supabase.table(TABLES['approvals'])\
                .update({
                    'status': 'approved',
                    'reviewed_by': hod_user_id,
                    'hod_comments': hod_comments,
                    'reviewed_at': datetime.utcnow().isoformat()
                })\
                .eq('id', approval_id)\
                .execute()
            
            # Get paper ID and update paper status
            approval = self.supabase.table(TABLES['approvals']).select('paper_id').eq('id', approval_id).execute()
            if approval.data:
                paper_id = approval.data[0]['paper_id']
                self.supabase.table(TABLES['saved_question_papers'])\
                    .update({'status': 'approved'})\
                    .eq('id', paper_id)\
                    .execute()
            
            return True
        except Exception as e:
            print(f"Error approving paper: {e}")
            return False
    
    def reject_paper(self, approval_id: str, hod_user_id: str, hod_comments: str = '') -> bool:
        """Reject a question paper"""
        try:
            # Update approval
            self.supabase.table(TABLES['approvals'])\
                .update({
                    'status': 'rejected',
                    'reviewed_by': hod_user_id,
                    'hod_comments': hod_comments,
                    'reviewed_at': datetime.utcnow().isoformat()
                })\
                .eq('id', approval_id)\
                .execute()
            
            # Get paper ID and update paper status
            approval = self.supabase.table(TABLES['approvals']).select('paper_id').eq('id', approval_id).execute()
            if approval.data:
                paper_id = approval.data[0]['paper_id']
                self.supabase.table(TABLES['saved_question_papers'])\
                    .update({'status': 'rejected'})\
                    .eq('id', paper_id)\
                    .execute()
            
            return True
        except Exception as e:
            print(f"Error rejecting paper: {e}")
            return False
    
    def create_approval(self, user_id: str, approval_data: Dict) -> Optional[Dict]:
        """Create a new approval request"""
        try:
            # Ensure submitted_by is set (it should already be in approval_data)
            if 'submitted_by' not in approval_data:
                approval_data['submitted_by'] = user_id
            
            result = self.supabase.table(TABLES['approvals'])\
                .insert(approval_data)\
                .execute()
            return result.data[0] if result.data else None
        except Exception as e:
            print(f"Error creating approval: {e}")
            return None
    
    def update_question_paper_status(self, paper_id: str, status: str, approval_id: str = None) -> bool:
        """Update question paper status"""
        try:
            update_data = {'status': status}
            if approval_id:
                update_data['approval_id'] = approval_id
            
            result = self.supabase.table(TABLES['saved_question_papers'])\
                .update(update_data)\
                .eq('id', paper_id)\
                .execute()
            return True
        except Exception as e:
            print(f"Error updating question paper status: {e}")
            return False

# Global instance
supabase_service = SupabaseService()
