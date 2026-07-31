"""
Database Query Optimizer for SmartQPGen
======================================
This module provides:
- Optimized Firestore queries
- Query result pagination
- Batch operations
- Connection pooling
- Query performance monitoring
"""

import time
from typing import List, Dict, Any, Optional, Tuple
from firebase_admin import firestore
from google.cloud.firestore_v1.base_query import FieldFilter
import logging

logger = logging.getLogger(__name__)

class DatabaseOptimizer:
    def __init__(self, db_client):
        self.db = db_client
        self.query_stats = {
            'total_queries': 0,
            'total_time': 0,
            'cache_hits': 0,
            'cache_misses': 0
        }
    
    def monitor_query(self, query_name: str):
        """Decorator to monitor query performance"""
        def decorator(func):
            def wrapper(*args, **kwargs):
                start_time = time.time()
                try:
                    result = func(*args, **kwargs)
                    duration = time.time() - start_time
                    
                    self.query_stats['total_queries'] += 1
                    self.query_stats['total_time'] += duration
                    
                    logger.info(f"Query '{query_name}' completed in {duration:.3f}s")
                    return result
                except Exception as e:
                    duration = time.time() - start_time
                    logger.error(f"Query '{query_name}' failed after {duration:.3f}s: {e}")
                    raise
            return wrapper
        return decorator
    
    @monitor_query("get_user_questions_optimized")
    def get_user_questions_optimized(self, user_uid: str, source_file: str = None, 
                                   limit: int = 100, offset: int = 0) -> Tuple[List[Dict], int]:
        """Optimized query to get user questions with pagination"""
        questions_ref = self.db.collection('users').document(user_uid).collection('question_bank_pool')
        
        # Build query
        query = questions_ref
        
        if source_file:
            query = query.where('source_file', '==', source_file)
        
        # Get total count first (for pagination)
        total_count = len(list(query.stream()))
        
        # Apply pagination
        if offset > 0:
            # For offset > 0, we need to use cursor-based pagination
            # This is more efficient for large datasets
            query = query.order_by('uploaded_at', direction=firestore.Query.DESCENDING)
            docs = list(query.limit(limit).offset(offset).stream())
        else:
            # For first page, we can use simple limit
            query = query.order_by('uploaded_at', direction=firestore.Query.DESCENDING)
            docs = list(query.limit(limit).stream())
        
        questions = []
        for doc in docs:
            question_data = doc.to_dict()
            question_data['firestore_id'] = doc.id
            questions.append(question_data)
        
        return questions, total_count
    
    @monitor_query("get_latest_source_file")
    def get_latest_source_file(self, user_uid: str) -> Optional[str]:
        """Get the latest source file for a user (optimized)"""
        questions_ref = self.db.collection('users').document(user_uid).collection('question_bank_pool')
        
        # Get only the most recent document
        latest_doc = questions_ref.order_by('uploaded_at', direction=firestore.Query.DESCENDING).limit(1).get()
        
        if latest_doc:
            return latest_doc[0].to_dict().get('source_file')
        return None
    
    @monitor_query("batch_get_questions")
    def batch_get_questions(self, user_uid: str, question_ids: List[str]) -> List[Dict]:
        """Batch get multiple questions by IDs"""
        if not question_ids:
            return []
        
        questions = []
        batch_size = 10  # Firestore batch limit
        
        for i in range(0, len(question_ids), batch_size):
            batch_ids = question_ids[i:i + batch_size]
            
            # Create batch query
            questions_ref = self.db.collection('users').document(user_uid).collection('question_bank_pool')
            query = questions_ref.where('__name__', 'in', batch_ids)
            
            docs = query.stream()
            for doc in docs:
                question_data = doc.to_dict()
                question_data['firestore_id'] = doc.id
                questions.append(question_data)
        
        return questions
    
    @monitor_query("get_user_papers_paginated")
    def get_user_papers_paginated(self, user_uid: str, paper_type: str = 'generated_papers',
                                limit: int = 20, offset: int = 0) -> Tuple[List[Dict], int]:
        """Get user papers with pagination"""
        papers_ref = self.db.collection('users').document(user_uid).collection(paper_type)
        
        # Get total count
        total_count = len(list(papers_ref.stream()))
        
        # Get paginated results
        query = papers_ref.order_by('created_at', direction=firestore.Query.DESCENDING)
        docs = list(query.limit(limit).offset(offset).stream())
        
        papers = []
        for doc in docs:
            paper_data = doc.to_dict()
            paper_data['firestore_id'] = doc.id
            papers.append(paper_data)
        
        return papers, total_count
    
    @monitor_query("search_questions")
    def search_questions(self, user_uid: str, search_term: str, 
                        source_file: str = None, limit: int = 50) -> List[Dict]:
        """Search questions by text content"""
        questions_ref = self.db.collection('users').document(user_uid).collection('question_bank_pool')
        
        # Build query
        query = questions_ref
        
        if source_file:
            query = query.where('source_file', '==', source_file)
        
        # Note: Firestore doesn't support full-text search natively
        # This is a basic implementation - for production, consider using
        # Algolia, Elasticsearch, or Firestore with Cloud Functions
        docs = list(query.stream())
        
        # Filter by search term (client-side filtering)
        matching_questions = []
        search_lower = search_term.lower()
        
        for doc in docs:
            question_data = doc.to_dict()
            question_text = question_data.get('question_text', '').lower()
            
            if search_lower in question_text:
                question_data['firestore_id'] = doc.id
                matching_questions.append(question_data)
                
                if len(matching_questions) >= limit:
                    break
        
        return matching_questions
    
    @monitor_query("get_approval_stats")
    def get_approval_stats(self, hod_uid: str) -> Dict[str, int]:
        """Get approval statistics for HOD dashboard"""
        stats = {
            'pending': 0,
            'approved': 0,
            'rejected': 0,
            'total': 0
        }
        
        # Get all faculty users
        users_ref = self.db.collection('users')
        faculty_docs = users_ref.where('role', '==', 'faculty').stream()
        
        for faculty_doc in faculty_docs:
            faculty_uid = faculty_doc.id
            
            # Get papers for this faculty
            papers_ref = self.db.collection('users').document(faculty_uid).collection('generated_papers')
            papers = papers_ref.where('approval_status', '!=', 'draft').stream()
            
            for paper in papers:
                paper_data = paper.to_dict()
                status = paper_data.get('approval_status', 'pending')
                
                if status in stats:
                    stats[status] += 1
                stats['total'] += 1
        
        return stats
    
    def batch_write_questions(self, user_uid: str, questions: List[Dict]) -> bool:
        """Batch write multiple questions efficiently"""
        try:
            batch = self.db.batch()
            questions_ref = self.db.collection('users').document(user_uid).collection('question_bank_pool')
            
            for question in questions:
                doc_ref = questions_ref.document()
                batch.set(doc_ref, question)
            
            batch.commit()
            logger.info(f"Batch wrote {len(questions)} questions for user {user_uid}")
            return True
            
        except Exception as e:
            logger.error(f"Batch write failed: {e}")
            return False
    
    def batch_update_papers(self, user_uid: str, paper_updates: List[Tuple[str, Dict]]) -> bool:
        """Batch update multiple papers"""
        try:
            batch = self.db.batch()
            papers_ref = self.db.collection('users').document(user_uid).collection('generated_papers')
            
            for paper_id, update_data in paper_updates:
                doc_ref = papers_ref.document(paper_id)
                batch.update(doc_ref, update_data)
            
            batch.commit()
            logger.info(f"Batch updated {len(paper_updates)} papers for user {user_uid}")
            return True
            
        except Exception as e:
            logger.error(f"Batch update failed: {e}")
            return False
    
    def get_performance_stats(self) -> Dict:
        """Get database performance statistics"""
        avg_query_time = 0
        if self.query_stats['total_queries'] > 0:
            avg_query_time = self.query_stats['total_time'] / self.query_stats['total_queries']
        
        return {
            'total_queries': self.query_stats['total_queries'],
            'total_time': round(self.query_stats['total_time'], 3),
            'average_query_time': round(avg_query_time, 3),
            'cache_hit_rate': round(
                self.query_stats['cache_hits'] / 
                (self.query_stats['cache_hits'] + self.query_stats['cache_misses']) * 100, 2
            ) if (self.query_stats['cache_hits'] + self.query_stats['cache_misses']) > 0 else 0
        }

# Connection pooling for better performance
class ConnectionPool:
    def __init__(self, max_connections=10):
        self.max_connections = max_connections
        self.connections = []
        self.active_connections = 0
    
    def get_connection(self):
        """Get a database connection from the pool"""
        if self.connections:
            return self.connections.pop()
        elif self.active_connections < self.max_connections:
            self.active_connections += 1
            return firestore.client()
        else:
            # Wait for a connection to become available
            time.sleep(0.1)
            return self.get_connection()
    
    def return_connection(self, connection):
        """Return a connection to the pool"""
        if len(self.connections) < self.max_connections:
            self.connections.append(connection)
        else:
            self.active_connections -= 1

# Global database optimizer instance
db_optimizer = None

def initialize_db_optimizer(db_client):
    """Initialize the global database optimizer"""
    global db_optimizer
    db_optimizer = DatabaseOptimizer(db_client)
    return db_optimizer
