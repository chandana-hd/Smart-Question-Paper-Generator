"""
Advanced Security Enhancements for SmartQPGen
============================================
This module provides enhanced security features including:
- JWT token validation with expiration
- Role-based access control (RBAC)
- Input sanitization and validation
- Advanced rate limiting
- Security headers
- Audit logging
"""

import time
import hashlib
import secrets
import bleach
import re
from functools import wraps
from flask import request, jsonify, g
from firebase_admin import auth
import firebase_admin
from datetime import datetime, timedelta
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class SecurityManager:
    def __init__(self):
        self.rate_limits = {}
        self.failed_attempts = {}
        self.blocked_ips = set()
        self.audit_logs = []
        
    def validate_token_with_expiry(self, id_token):
        """Enhanced token validation with expiration check"""
        try:
            decoded_token = auth.verify_id_token(id_token, check_revoked=True)
            
            # Check token expiration
            exp = decoded_token.get('exp', 0)
            if time.time() > exp:
                raise ValueError("Token expired")
                
            # Check token age (max 1 hour)
            iat = decoded_token.get('iat', 0)
            if time.time() - iat > 3600:
                raise ValueError("Token too old")
                
            return decoded_token
        except Exception as e:
            logger.warning(f"Token validation failed: {str(e)}")
            raise ValueError(f"Invalid token: {str(e)}")
    
    def sanitize_input(self, text, max_length=1000):
        """Sanitize user input to prevent XSS and injection attacks"""
        if not text:
            return ""
            
        # Remove HTML tags
        clean_text = bleach.clean(str(text), strip=True)
        
        # Remove potentially dangerous characters
        clean_text = re.sub(r'[<>"\']', '', clean_text)
        
        # Limit length
        return clean_text[:max_length]
    
    def validate_file_upload(self, file):
        """Enhanced file validation"""
        if not file:
            raise ValueError("No file provided")
            
        # Check file size (max 16MB)
        file.seek(0, 2)  # Seek to end
        file_size = file.tell()
        file.seek(0)  # Reset to beginning
        
        if file_size > 16 * 1024 * 1024:
            raise ValueError("File too large (max 16MB)")
            
        # Check file type
        allowed_extensions = {'docx', 'pdf'}
        if not file.filename.lower().endswith(tuple(allowed_extensions)):
            raise ValueError("Invalid file type")
            
        # Check for suspicious content
        content = file.read(1024)  # Read first 1KB
        file.seek(0)
        
        # Check for executable content
        if b'<script' in content.lower() or b'javascript:' in content.lower():
            raise ValueError("File contains potentially malicious content")
            
        return True
    
    def advanced_rate_limiting(self, max_requests=10, window=60, block_duration=300):
        """Advanced rate limiting with IP blocking"""
        client_ip = request.remote_addr
        current_time = time.time()
        
        # Check if IP is blocked
        if client_ip in self.blocked_ips:
            return False, "IP temporarily blocked"
            
        # Clean old attempts
        if client_ip in self.rate_limits:
            self.rate_limits[client_ip] = [
                attempt for attempt in self.rate_limits[client_ip] 
                if current_time - attempt < window
            ]
        else:
            self.rate_limits[client_ip] = []
            
        # Check rate limit
        if len(self.rate_limits[client_ip]) >= max_requests:
            # Block IP temporarily
            self.blocked_ips.add(client_ip)
            self.failed_attempts[client_ip] = self.failed_attempts.get(client_ip, 0) + 1
            
            # Log security event
            self.log_security_event('rate_limit_exceeded', {
                'ip': client_ip,
                'attempts': len(self.rate_limits[client_ip]),
                'block_duration': block_duration
            })
            
            # Auto-unblock after duration
            def unblock_ip():
                time.sleep(block_duration)
                self.blocked_ips.discard(client_ip)
                
            import threading
            threading.Thread(target=unblock_ip, daemon=True).start()
            
            return False, "Rate limit exceeded"
            
        # Record this attempt
        self.rate_limits[client_ip].append(current_time)
        return True, "OK"
    
    def log_security_event(self, event_type, details):
        """Log security events for audit trail"""
        log_entry = {
            'timestamp': datetime.utcnow().isoformat(),
            'event_type': event_type,
            'ip_address': request.remote_addr,
            'user_agent': request.headers.get('User-Agent', ''),
            'details': details
        }
        
        self.audit_logs.append(log_entry)
        logger.info(f"Security event: {event_type} - {details}")
        
        # Keep only last 1000 logs
        if len(self.audit_logs) > 1000:
            self.audit_logs = self.audit_logs[-1000:]

# Global security manager instance
security_manager = SecurityManager()

def enhanced_auth_required(roles=None):
    """Enhanced authentication decorator with role-based access control"""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            # Rate limiting check
            allowed, message = security_manager.advanced_rate_limiting()
            if not allowed:
                return jsonify({
                    'message': message,
                    'error_type': 'rate_limit_exceeded'
                }), 429
            
            # Get authorization header
            auth_header = request.headers.get('Authorization')
            if not auth_header:
                security_manager.log_security_event('missing_auth_header', {})
                return jsonify({'message': 'Authorization header is missing!'}), 401
            
            try:
                # Extract token
                id_token = auth_header.split(' ')[1]
                
                # Enhanced token validation
                decoded_token = security_manager.validate_token_with_expiry(id_token)
                
                # Attach user info to request
                request.current_user_uid = decoded_token['uid']
                request.current_user_email = decoded_token.get('email')
                request.current_user_role = decoded_token.get('role', 'faculty')
                
                # Role-based access control
                if roles and request.current_user_role not in roles:
                    security_manager.log_security_event('unauthorized_role_access', {
                        'user_id': request.current_user_uid,
                        'required_roles': roles,
                        'user_role': request.current_user_role
                    })
                    return jsonify({'message': 'Insufficient permissions'}), 403
                
                return f(*args, **kwargs)
                
            except ValueError as e:
                security_manager.log_security_event('invalid_token', {
                    'error': str(e)
                })
                return jsonify({'message': str(e)}), 401
            except Exception as e:
                security_manager.log_security_event('auth_error', {
                    'error': str(e)
                })
                return jsonify({'message': f'Authentication error: {str(e)}'}), 500
                
        return decorated_function
    return decorator

def hod_required(f):
    """Decorator for HOD-only endpoints"""
    return enhanced_auth_required(roles=['hod'])(f)

def faculty_required(f):
    """Decorator for faculty-only endpoints"""
    return enhanced_auth_required(roles=['faculty'])(f)

def validate_and_sanitize_input(data, schema):
    """Validate and sanitize input data based on schema"""
    sanitized_data = {}
    
    for field, rules in schema.items():
        value = data.get(field)
        
        if rules.get('required') and not value:
            raise ValueError(f"Field '{field}' is required")
            
        if value:
            # Sanitize string fields
            if rules.get('type') == 'string':
                value = security_manager.sanitize_input(
                    value, 
                    max_length=rules.get('max_length', 1000)
                )
            
            # Validate specific field types
            if field == 'email' and not re.match(r'^[^@]+@[^@]+\.[^@]+$', value):
                raise ValueError("Invalid email format")
                
            if field == 'subject' and len(value) > 100:
                raise ValueError("Subject too long")
                
        sanitized_data[field] = value
        
    return sanitized_data

# Security headers middleware
def add_security_headers(response):
    """Add security headers to responses"""
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
    response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self' 'unsafe-inline' https://www.gstatic.com https://www.googleapis.com; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; font-src 'self' https://fonts.gstatic.com; img-src 'self' data: https:; connect-src 'self' https://identitytoolkit.googleapis.com https://securetoken.googleapis.com"
    return response
