"""
API Enhancements Module
======================

This module provides enhanced API functionality including:
- Standardized response formats
- Advanced error handling
- API versioning
- Rate limiting
- Request/response logging
- API documentation generation
"""

import time
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List, Callable
from functools import wraps
from flask import request, jsonify, g, current_app
from enum import Enum
import hashlib

# Configure logging
logger = logging.getLogger(__name__)

class APIResponseStatus(Enum):
    """Standard API response statuses"""
    SUCCESS = "success"
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"

class APIErrorCode(Enum):
    """Standard API error codes"""
    # Authentication errors
    AUTH_REQUIRED = "AUTH_REQUIRED"
    AUTH_INVALID = "AUTH_INVALID"
    AUTH_EXPIRED = "AUTH_EXPIRED"
    AUTH_INSUFFICIENT_PERMISSIONS = "AUTH_INSUFFICIENT_PERMISSIONS"
    
    # Validation errors
    VALIDATION_ERROR = "VALIDATION_ERROR"
    INVALID_INPUT = "INVALID_INPUT"
    MISSING_REQUIRED_FIELD = "MISSING_REQUIRED_FIELD"
    
    # Resource errors
    RESOURCE_NOT_FOUND = "RESOURCE_NOT_FOUND"
    RESOURCE_ALREADY_EXISTS = "RESOURCE_ALREADY_EXISTS"
    RESOURCE_CONFLICT = "RESOURCE_CONFLICT"
    
    # System errors
    INTERNAL_ERROR = "INTERNAL_ERROR"
    SERVICE_UNAVAILABLE = "SERVICE_UNAVAILABLE"
    RATE_LIMIT_EXCEEDED = "RATE_LIMIT_EXCEEDED"
    QUOTA_EXCEEDED = "QUOTA_EXCEEDED"
    
    # Business logic errors
    BUSINESS_RULE_VIOLATION = "BUSINESS_RULE_VIOLATION"
    OPERATION_NOT_ALLOWED = "OPERATION_NOT_ALLOWED"

class APIResponse:
    """Standardized API response class"""
    
    def __init__(self, status: APIResponseStatus, data: Any = None, 
                 message: str = "", error_code: Optional[APIErrorCode] = None,
                 metadata: Optional[Dict[str, Any]] = None):
        self.status = status
        self.data = data
        self.message = message
        self.error_code = error_code
        self.metadata = metadata or {}
        self.timestamp = datetime.now().isoformat()
        self.request_id = getattr(g, 'request_id', None)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert response to dictionary"""
        response = {
            'status': self.status.value,
            'timestamp': self.timestamp,
            'request_id': self.request_id
        }
        
        if self.data is not None:
            response['data'] = self.data
        
        if self.message:
            response['message'] = self.message
        
        if self.error_code:
            response['error_code'] = self.error_code.value
        
        if self.metadata:
            response['metadata'] = self.metadata
        
        return response
    
    def to_json_response(self, status_code: int = 200) -> tuple:
        """Convert to Flask JSON response"""
        return jsonify(self.to_dict()), status_code

# Response helper functions
def success_response(data: Any = None, message: str = "Operation completed successfully", 
                    metadata: Optional[Dict[str, Any]] = None) -> tuple:
    """Create a success response"""
    response = APIResponse(APIResponseStatus.SUCCESS, data, message, metadata=metadata)
    return response.to_json_response(200)

def error_response(message: str, error_code: APIErrorCode, 
                  data: Any = None, status_code: int = 400,
                  metadata: Optional[Dict[str, Any]] = None) -> tuple:
    """Create an error response"""
    response = APIResponse(APIResponseStatus.ERROR, data, message, error_code, metadata)
    return response.to_json_response(status_code)

def validation_error_response(message: str, validation_errors: List[str] = None) -> tuple:
    """Create a validation error response"""
    metadata = {'validation_errors': validation_errors} if validation_errors else None
    return error_response(message, APIErrorCode.VALIDATION_ERROR, 
                         status_code=422, metadata=metadata)

def not_found_response(message: str = "Resource not found") -> tuple:
    """Create a not found response"""
    return error_response(message, APIErrorCode.RESOURCE_NOT_FOUND, status_code=404)

def unauthorized_response(message: str = "Authentication required") -> tuple:
    """Create an unauthorized response"""
    return error_response(message, APIErrorCode.AUTH_REQUIRED, status_code=401)

def forbidden_response(message: str = "Insufficient permissions") -> tuple:
    """Create a forbidden response"""
    return error_response(message, APIErrorCode.AUTH_INSUFFICIENT_PERMISSIONS, status_code=403)

def rate_limit_response(message: str = "Rate limit exceeded") -> tuple:
    """Create a rate limit response"""
    return error_response(message, APIErrorCode.RATE_LIMIT_EXCEEDED, status_code=429)

def internal_error_response(message: str = "Internal server error") -> tuple:
    """Create an internal error response"""
    return error_response(message, APIErrorCode.INTERNAL_ERROR, status_code=500)

class RateLimiter:
    """Simple in-memory rate limiter"""
    
    def __init__(self):
        self.requests = {}
        self.cleanup_interval = 300  # 5 minutes
        self.last_cleanup = time.time()
    
    def is_allowed(self, key: str, limit: int, window: int) -> bool:
        """Check if request is allowed based on rate limit"""
        current_time = time.time()
        
        # Cleanup old entries periodically
        if current_time - self.last_cleanup > self.cleanup_interval:
            self._cleanup_old_entries(current_time)
            self.last_cleanup = current_time
        
        # Get or create request history for this key
        if key not in self.requests:
            self.requests[key] = []
        
        # Remove old requests outside the window
        cutoff_time = current_time - window
        self.requests[key] = [req_time for req_time in self.requests[key] if req_time > cutoff_time]
        
        # Check if under limit
        if len(self.requests[key]) < limit:
            self.requests[key].append(current_time)
            return True
        
        return False
    
    def _cleanup_old_entries(self, current_time: float):
        """Clean up old rate limit entries"""
        cutoff_time = current_time - 3600  # 1 hour
        keys_to_remove = []
        
        for key, requests in self.requests.items():
            if not requests or max(requests) < cutoff_time:
                keys_to_remove.append(key)
        
        for key in keys_to_remove:
            del self.requests[key]

# Global rate limiter instance
rate_limiter = RateLimiter()

def rate_limit(limit: int = 100, window: int = 3600, per: str = 'ip'):
    """Rate limiting decorator"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Determine rate limit key
            if per == 'ip':
                key = request.remote_addr
            elif per == 'user':
                key = getattr(g, 'user_id', request.remote_addr)
            else:
                key = f"{per}_{request.remote_addr}"
            
            # Check rate limit
            if not rate_limiter.is_allowed(key, limit, window):
                return rate_limit_response(f"Rate limit exceeded: {limit} requests per {window} seconds")
            
            return func(*args, **kwargs)
        return wrapper
    return decorator

class APIValidator:
    """API request validation"""
    
    @staticmethod
    def validate_required_fields(data: Dict[str, Any], required_fields: List[str]) -> List[str]:
        """Validate required fields are present"""
        missing_fields = []
        for field in required_fields:
            if field not in data or data[field] is None or data[field] == "":
                missing_fields.append(field)
        return missing_fields
    
    @staticmethod
    def validate_email(email: str) -> bool:
        """Validate email format"""
        import re
        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        return re.match(pattern, email) is not None
    
    @staticmethod
    def validate_password_strength(password: str) -> List[str]:
        """Validate password strength"""
        errors = []
        if len(password) < 8:
            errors.append("Password must be at least 8 characters long")
        if not any(c.isupper() for c in password):
            errors.append("Password must contain at least one uppercase letter")
        if not any(c.islower() for c in password):
            errors.append("Password must contain at least one lowercase letter")
        if not any(c.isdigit() for c in password):
            errors.append("Password must contain at least one digit")
        return errors

def validate_request(required_fields: List[str] = None, 
                    optional_fields: List[str] = None,
                    custom_validators: Dict[str, Callable] = None):
    """Request validation decorator"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Get request data
            if request.is_json:
                data = request.get_json() or {}
            else:
                data = request.form.to_dict()
            
            # Validate required fields
            if required_fields:
                missing_fields = APIValidator.validate_required_fields(data, required_fields)
                if missing_fields:
                    return validation_error_response(
                        f"Missing required fields: {', '.join(missing_fields)}",
                        missing_fields
                    )
            
            # Validate optional fields if provided
            if optional_fields:
                for field in optional_fields:
                    if field in data and data[field] is not None:
                        # Add field-specific validation here if needed
                        pass
            
            # Run custom validators
            if custom_validators:
                for field, validator in custom_validators.items():
                    if field in data:
                        try:
                            result = validator(data[field])
                            if result is not True and result is not None:
                                return validation_error_response(f"Validation failed for field '{field}': {result}")
                        except Exception as e:
                            return validation_error_response(f"Validation error for field '{field}': {str(e)}")
            
            # Store validated data in g for use in the function
            g.validated_data = data
            return func(*args, **kwargs)
        return wrapper
    return decorator

class APILogger:
    """API request/response logging"""
    
    def __init__(self):
        self.logger = logging.getLogger('api')
    
    def log_request(self, endpoint: str, method: str, user_id: str = None, 
                   request_data: Dict[str, Any] = None):
        """Log API request"""
        log_data = {
            'type': 'request',
            'endpoint': endpoint,
            'method': method,
            'user_id': user_id,
            'ip': request.remote_addr,
            'user_agent': request.headers.get('User-Agent'),
            'timestamp': datetime.now().isoformat()
        }
        
        if request_data:
            # Sanitize sensitive data
            sanitized_data = self._sanitize_data(request_data)
            log_data['data'] = sanitized_data
        
        self.logger.info(f"API Request: {json.dumps(log_data)}")
    
    def log_response(self, endpoint: str, status_code: int, response_time: float,
                    user_id: str = None, error: str = None):
        """Log API response"""
        log_data = {
            'type': 'response',
            'endpoint': endpoint,
            'status_code': status_code,
            'response_time': response_time,
            'user_id': user_id,
            'timestamp': datetime.now().isoformat()
        }
        
        if error:
            log_data['error'] = error
        
        self.logger.info(f"API Response: {json.dumps(log_data)}")
    
    def _sanitize_data(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Sanitize sensitive data for logging"""
        sensitive_fields = ['password', 'token', 'secret', 'key', 'auth']
        sanitized = data.copy()
        
        for key, value in sanitized.items():
            if any(sensitive in key.lower() for sensitive in sensitive_fields):
                sanitized[key] = '***REDACTED***'
        
        return sanitized

# Global API logger instance
api_logger = APILogger()

def log_api_call(endpoint_name: str = None):
    """API call logging decorator"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            start_time = time.time()
            endpoint = endpoint_name or f"{request.endpoint}_{request.method}"
            user_id = getattr(g, 'user_id', None)
            
            # Log request
            request_data = None
            if request.is_json:
                request_data = request.get_json()
            elif request.form:
                request_data = request.form.to_dict()
            
            api_logger.log_request(endpoint, request.method, user_id, request_data)
            
            try:
                result = func(*args, **kwargs)
                response_time = time.time() - start_time
                
                # Log successful response
                status_code = 200
                if isinstance(result, tuple) and len(result) == 2:
                    status_code = result[1]
                
                api_logger.log_response(endpoint, status_code, response_time, user_id)
                return result
                
            except Exception as e:
                response_time = time.time() - start_time
                api_logger.log_response(endpoint, 500, response_time, user_id, str(e))
                raise
        
        return wrapper
    return decorator

class APIVersionManager:
    """API version management"""
    
    def __init__(self):
        self.versions = {}
        self.default_version = 'v1'
    
    def register_version(self, version: str, prefix: str = None):
        """Register a new API version"""
        if prefix is None:
            prefix = f"/api/{version}"
        self.versions[version] = prefix
        return prefix
 