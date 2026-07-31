#!/usr/bin/env python3
"""
Simple script to start the Flask backend server with proper environment setup.
Run this script to start your SmartQPGen backend server.
"""

import os
import sys

def main():
    # Set the environment variable for Firebase credentials
    os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = 'smartqpgen-amrutha-firebase-adminsdk-fbsvc-509c2b1cdd.json'
    
    # Add the current directory to Python path
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    
    # Import and run the Flask app
    from app import app
    
    print("=" * 50)
    print("Starting SmartQPGen Backend Server...")
    print("=" * 50)
    print("Server will be available at: http://localhost:5000")
    print("Press Ctrl+C to stop the server")
    print("=" * 50)
    
    try:
        app.run(host='0.0.0.0', port=5000, debug=True)
    except KeyboardInterrupt:
        print("\nServer stopped by user.")
    except Exception as e:
        print(f"Error starting server: {e}")

if __name__ == "__main__":
    main()

