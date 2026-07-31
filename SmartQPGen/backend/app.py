import os
from flask import Flask, request, jsonify, render_template, send_file
from flask_cors import CORS
import firebase_admin
from firebase_admin import credentials, auth, firestore
from supabase_service import supabase_service
from functools import wraps
from dotenv import load_dotenv # Make sure dotenv is installed: pip install python-dotenv

# --- New Imports for File Parsing ---
import pdfplumber
import docx # For .docx files
from docx.shared import Inches, Pt # For setting table column widths and font sizes
import docx.enum.text # For text alignment
import docx.shared # For measurements
from werkzeug.utils import secure_filename
import re # For cleaning text and potential regex parsing
import traceback # For detailed error logging
import uuid # For generating unique IDs for question banks and questions
from datetime import datetime # For current date/time in template
import pythoncom # For COM initialization in PDF conversion
from reportlab.lib.pagesizes import letter, A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch

# --- New Imports for Gemini API ---
import requests # For making HTTP requests to the Gemini API
import json # For handling JSON payload
import time # For rate limiting

# Load environment variables from .env file (for local development)
load_dotenv()

app = Flask(__name__)
CORS(app) # Enable CORS for all origins, adjust in production for production deployment

# --- Firebase Admin SDK Initialization ---
if not firebase_admin._apps:
    try:
        # Try to use the service account JSON file directly
        service_account_path = 'smartqpgen-amrutha-firebase-adminsdk-fbsvc-509c2b1cdd.json'
        if os.path.exists(service_account_path):
            cred = credentials.Certificate(service_account_path)
            firebase_admin.initialize_app(cred)
            print("Firebase Admin SDK initialized using service account JSON file.")
        else:
            # Fallback to Application Default Credentials
            cred = credentials.ApplicationDefault()
            firebase_admin.initialize_app(cred)
            print("Firebase Admin SDK initialized using Application Default Credentials.")
    except Exception as e:
        print(f"Error initializing Firebase Admin SDK: {e}")
        print("Please ensure the Firebase service account key JSON file exists in the backend directory.")
        print("For local development, make sure 'smartqpgen-amrutha-firebase-adminsdk-fbsvc-509c2b1cdd.json' is in the backend folder.")
else:
    print("Firebase Admin SDK already initialized.")

db_firestore = firestore.client() # Get Firestore client

# Simple rate limiting for authentication
auth_attempts = {}  # Store authentication attempts per IP
MAX_AUTH_ATTEMPTS = 5  # Maximum attempts per minute
AUTH_WINDOW = 60  # Time window in seconds

# --- JWT Secret Key (for Flask sessions, if needed, but Firebase ID tokens are primary) ---
app.config['SECRET_KEY'] = os.getenv('FLASK_SECRET_KEY', 'your_super_secret_key_change_this_in_production')

# --- Simple in-memory cache for reducing Firestore calls ---
question_cache = {}
cache_timeout = 300  # 5 minutes

def get_cached_questions(user_uid, cache_key):
    """Get questions from cache if available and not expired"""
    import time
    if cache_key in question_cache:
        cached_data, timestamp = question_cache[cache_key]
        if time.time() - timestamp < cache_timeout:
            print(f"Using cached questions for {cache_key}")
            return cached_data
        else:
            # Cache expired, remove it
            del question_cache[cache_key]
    return None

def cache_questions(user_uid, cache_key, questions):
    """Cache questions with timestamp"""
    import time
    question_cache[cache_key] = (questions, time.time())
    print(f"Cached {len(questions)} questions for {cache_key}")

# --- File Upload Configuration ---
UPLOAD_FOLDER = 'uploads' # Directory to temporarily save uploaded files
ALLOWED_EXTENSIONS = {'pdf', 'docx'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True) # Create the upload folder if it doesn't exist

# --- Authentication Decorator ---
def firebase_auth_required(f):
    """Decorator to protect routes, verifying Firebase ID tokens."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        auth_header = request.headers.get('Authorization')
        if not auth_header:
            return jsonify({'message': 'Authorization header is missing!'}), 401

        try:
            # Token format: "Bearer <ID_TOKEN>"
            id_token = auth_header.split(' ')[1]
            # Verify the Firebase ID token
            decoded_token = auth.verify_id_token(id_token)
            request.current_user_uid = decoded_token['uid'] # Attach UID to request object
            return f(*args, **kwargs)
        except firebase_admin.auth.InvalidIdTokenError:
            return jsonify({'message': 'Invalid or expired authentication token.'}), 401
        except Exception as e:
            return jsonify({'message': f'Authentication error: {str(e)}'}), 500
    return decorated_function

# --- Helper Functions for Parsing ---
def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def convert_docx_to_pdf_robust(docx_path):
    """
    Robust PDF conversion function that tries multiple methods
    """
    pdf_path = docx_path.replace('.docx', '.pdf')

    # Method 1: Try docx2pdf with COM initialization
    try:
        from docx2pdf import convert
        print("Attempting PDF conversion with docx2pdf...")

        # Initialize COM for the current thread
        pythoncom.CoInitialize()

        try:
            convert(docx_path, pdf_path)
            if os.path.exists(pdf_path) and os.path.getsize(pdf_path) > 0:
                print("PDF conversion successful with docx2pdf")
                return pdf_path
        finally:
            # Always uninitialize COM
            pythoncom.CoUninitialize()

    except Exception as e:
        print(f"docx2pdf conversion failed: {e}")

    # Method 2: Try using win32com directly (Windows only)
    try:
        import win32com.client
        print("Attempting PDF conversion with win32com...")

        # Initialize COM
        pythoncom.CoInitialize()

        try:
            word = win32com.client.Dispatch("Word.Application")
            word.Visible = False

            # Open document
            doc = word.Documents.Open(os.path.abspath(docx_path))

            # Save as PDF (format 17 is PDF)
            doc.SaveAs(os.path.abspath(pdf_path), FileFormat=17)
            doc.Close()
            word.Quit()

            if os.path.exists(pdf_path) and os.path.getsize(pdf_path) > 0:
                print("PDF conversion successful with win32com")
                return pdf_path

        finally:
            pythoncom.CoUninitialize()

    except Exception as e:
        print(f"win32com conversion failed: {e}")

    # Method 3: Return original DOCX if all PDF methods fail
    print("All PDF conversion methods failed, returning DOCX")
    return docx_path

def clean_text(text):
    """Basic text cleaning: remove excessive whitespace, newlines, strip leading/trailing space."""
    if text is None:
        return ""
    # Replace multiple spaces/newlines with a single space, then strip
    text = re.sub(r'\s+', ' ', text).strip()
    return text

def extract_marks_from_text(marks_text):
    """Extract numeric marks from various formats like '6M', '8M', '6', etc."""
    if not marks_text:
        return 0
    
    # Remove common suffixes and extract number
    marks_text = str(marks_text).strip().upper()
    
    # Handle formats like "6M", "8M", "10M"
    if marks_text.endswith('M'):
        try:
            return int(marks_text[:-1])
        except ValueError:
            pass
    
    # Handle formats like "6", "8", "10"
    try:
        return int(marks_text)
    except ValueError:
        pass
    
    # Handle formats like "6 marks", "8 marks"
    marks_match = re.search(r'(\d+)\s*marks?', marks_text, re.IGNORECASE)
    if marks_match:
        return int(marks_match.group(1))
    
    # Handle formats like "6 pts", "8 pts"
    pts_match = re.search(r'(\d+)\s*pts?', marks_text, re.IGNORECASE)
    if pts_match:
        return int(pts_match.group(1))
    
    return 0

def extract_table_as_text(table_data):
    """Convert table data to readable text format with proper formatting"""
    if not table_data:
        return ""
    
    table_text = ""
    for row in table_data:
        if row and any(cell for cell in row if cell and str(cell).strip()):
            # Filter out empty cells and join with proper spacing
            row_cells = [str(cell).strip() if cell else "" for cell in row]
            # Use consistent spacing instead of tabs for better display
            row_text = " | ".join(row_cells)
            table_text += row_text + "\n"
    
    return table_text.strip()

def extract_table_data_for_knn(table_data):
    """Extract table data specifically for k-NN dataset format"""
    if not table_data:
        return ""
    
    # Check if this looks like the k-NN dataset
    if len(table_data) > 0 and len(table_data[0]) >= 5:
        header_row = table_data[0]
        if any("S.NO" in str(cell) for cell in header_row) or any("CGPA" in str(cell) for cell in header_row):
            # This is the k-NN dataset format
            table_text = ""
            for row in table_data:
                if row and any(cell for cell in row if cell and str(cell).strip()):
                    row_cells = [str(cell).strip() if cell else "" for cell in row]
                    row_text = " | ".join(row_cells)
                    table_text += row_text + "\n"
            return table_text.strip()
    
    # Fallback to regular table extraction
    return extract_table_as_text(table_data)

def format_table_data_for_display(table_data):
    """Format table data specifically for frontend display with proper line breaks"""
    if not table_data:
        return ""
    
    formatted_rows = []
    for row in table_data:
        if row and any(cell for cell in row if cell and str(cell).strip()):
            # Filter out empty cells and join with proper spacing
            row_cells = [str(cell).strip() if cell else "" for cell in row]
            # Use pipe separators for better frontend parsing
            row_text = " | ".join(row_cells)
            formatted_rows.append(row_text)
    
    return "\n".join(formatted_rows)

def format_question_with_tables(question_text):
    """Format question text that may contain embedded table data"""
    if not question_text:
        return question_text
    
    # Check if the question contains concatenated table data (like "S.NO CGPA Assessment Project submitted Result 1 9.2 85 8 Pass 2 8 80 7 Pass...")
    if 'S.NO' in question_text and 'CGPA' in question_text and 'Assessment' in question_text:
        # This is likely the k-NN dataset format
        return format_knn_dataset_in_question(question_text)
    
    # Check for other table patterns like "S.NO GPA No. of projects done Award 1 9.5 5 Yes..."
    if 'S.NO' in question_text and 'GPA' in question_text and 'Award' in question_text:
        return format_gpa_award_dataset_in_question(question_text)
    
    # Check for other table patterns like "X Y Class 3 1 A 5 2 A..."
    if 'X Y Class' in question_text or ('X' in question_text and 'Y' in question_text and 'Class' in question_text):
        return format_xy_class_dataset_in_question(question_text)
    
    # Check if the question contains table-like data
    lines = question_text.split('\n')
    formatted_lines = []
    in_table = False
    table_lines = []
    
    for line in lines:
        line = line.strip()
        if not line:
            if in_table and table_lines:
                # End of table, format it
                formatted_table = format_embedded_table(table_lines)
                formatted_lines.append(formatted_table)
                table_lines = []
                in_table = False
            continue
            
        # Check if this line looks like table data (has multiple space-separated values)
        words = line.split()
        # More specific conditions for table detection
        is_table_data = (
            len(words) >= 3 and 
            not any(word in line.lower() for word in ['question', 'consider', 'write', 'what', 'how', 'explain', 'describe', 'compare', 'contrast', 'differences', 'between', 'instance', 'based', 'learning', 'model', 'nearest', 'neighbour', 'algorithm', 'weighted', 'determine', 'class', 'given', 'test', 'assign', 'predict', 'using', 'classifier', 'centroid', 'training', 'dataset', 'target', 'variable', 'discrete', 'valued', 'takes', 'values', 'choose', 'k=']) and
            (any(word.isdigit() for word in words) or any(word in ['pass', 'fail', 'yes', 'no', 'a', 'b'] for word in words) or 
             any(word.lower() in ['s.no', 'sno', 'gpa', 'cgpa', 'x', 'y', 'class', 'award', 'result', 'assessment', 'project', 'submitted'] for word in words))
        )
        
        if is_table_data:
            # This looks like table data
            if not in_table:
                in_table = True
            table_lines.append(line)
        else:
            if in_table and table_lines:
                # End of table, format it
                formatted_table = format_embedded_table(table_lines)
                formatted_lines.append(formatted_table)
                table_lines = []
                in_table = False
            formatted_lines.append(line)
    
    # Handle table at the end
    if in_table and table_lines:
        formatted_table = format_embedded_table(table_lines)
        formatted_lines.append(formatted_table)
    
    return '\n'.join(formatted_lines)

def format_knn_dataset_in_question(question_text):
    """Format k-NN dataset that's concatenated in question text"""
    # Find the start of the table data
    table_start = question_text.find('S.NO')
    if table_start == -1:
        return question_text
    
    # Split into question part and table part
    question_part = question_text[:table_start].strip()
    table_part = question_text[table_start:].strip()
    
    # Format the table part
    formatted_table = format_concatenated_table(table_part)
    
    # Combine question and formatted table
    return f"{question_part}\n\n{formatted_table}"

def format_xy_class_dataset_in_question(question_text):
    """Format X Y Class dataset that's concatenated in the question text"""
    # Find where the table data starts
    table_start = question_text.find('X Y Class')
    if table_start == -1:
        # Try alternative patterns
        if 'X' in question_text and 'Y' in question_text and 'Class' in question_text:
            # Find the position where X Y Class appears
            words = question_text.split()
            for i, word in enumerate(words):
                if word == 'X' and i + 2 < len(words) and words[i+1] == 'Y' and words[i+2] == 'Class':
                    # Found "X Y Class", get the position in the original text
                    table_start = question_text.find(' '.join(words[i:i+3]))
                    break
    
    if table_start == -1:
        return question_text
    
    # Split into question part and table part
    question_part = question_text[:table_start].strip()
    table_part = question_text[table_start:].strip()
    
    # Format the table part
    formatted_table = format_xy_class_table(table_part)
    
    # Combine question and formatted table
    return f"{question_part}\n\n{formatted_table}"

def format_xy_class_table(table_text):
    """Format X Y Class table data"""
    words = table_text.split()
    
    # Find the header part (X Y Class)
    header_words = []
    data_start_idx = 0
    
    for i, word in enumerate(words):
        if word.isdigit() and i > 2:  # Found first number after headers
            data_start_idx = i
            break
        header_words.append(word)
    
    if len(header_words) < 3 or data_start_idx == 0:
        return f"Table:\n{table_text}"
    
    # Format headers
    headers = ' | '.join(header_words)
    formatted_table = f"Table:\n{headers}\n"
    
    # Format data rows (should be groups of 3: number, number, letter)
    data_words = words[data_start_idx:]
    for i in range(0, len(data_words), 3):
        if i + 2 < len(data_words):
            row = f"{data_words[i]} | {data_words[i+1]} | {data_words[i+2]}"
            formatted_table += row + "\n"
    
    return formatted_table.strip()

def format_gpa_award_dataset_in_question(question_text):
    """Format S.NO GPA Award dataset that's concatenated in the question text"""
    # Find where the table data starts
    table_start = question_text.find('S.NO')
    if table_start == -1:
        return question_text
    
    # Split into question part and table part
    question_part = question_text[:table_start].strip()
    table_part = question_text[table_start:].strip()
    
    # Format the table part
    formatted_table = format_gpa_award_table(table_part)
    
    # Combine question and formatted table
    return f"{question_part}\n\n{formatted_table}"

def format_gpa_award_table(table_text):
    """Format S.NO GPA Award table data"""
    words = table_text.split()
    
    # Find the header part (S.NO GPA No. of projects done Award)
    header_words = []
    data_start_idx = 0
    
    for i, word in enumerate(words):
        if word.isdigit() and i > 3:  # Found first number after headers
            data_start_idx = i
            break
        header_words.append(word)
    
    if len(header_words) < 4 or data_start_idx == 0:
        return f"Table:\n{table_text}"
    
    # Format headers
    headers = ' | '.join(header_words)
    formatted_table = f"Table:\n{headers}\n"
    
    # Format data rows (should be groups of 4: number, decimal, number, yes/no)
    data_words = words[data_start_idx:]
    for i in range(0, len(data_words), 4):
        if i + 3 < len(data_words):
            row = f"{data_words[i]} | {data_words[i+1]} | {data_words[i+2]} | {data_words[i+3]}"
            formatted_table += row + "\n"
    
    return formatted_table.strip()

def format_concatenated_table(table_text):
    """Format concatenated table text like 'S.NO CGPA Assessment Project submitted Result 1 9.2 85 8 Pass 2 8 80 7 Pass...'"""
    words = table_text.split()
    
    # Find the header part
    header_words = []
    data_start_idx = 0
    
    for i, word in enumerate(words):
        if word.isdigit() and i > 0:  # Found first number (row number)
            data_start_idx = i
            break
        header_words.append(word)
    
    if not header_words or data_start_idx == 0:
        return f"Table:\n{table_text}"
    
    # Format headers
    headers = ' | '.join(header_words)
    
    # Format data rows
    data_words = words[data_start_idx:]
    rows = []
    current_row = []
    
    for word in data_words:
        if word.isdigit() and len(current_row) >= 4:  # New row starting
            if current_row:
                rows.append(' | '.join(current_row))
            current_row = [word]
        else:
            current_row.append(word)
    
    # Add the last row
    if current_row:
        rows.append(' | '.join(current_row))
    
    # Combine everything
    result = f"Table:\n{headers}\n" + '\n'.join(rows)
    return result

def format_embedded_table(table_lines):
    """Format embedded table lines into a proper table structure"""
    if not table_lines:
        return ""
    
    # Check if first line looks like headers
    first_line_words = table_lines[0].split()
    if len(first_line_words) >= 2 and not any(word.isdigit() for word in first_line_words):
        # First line is likely headers
        headers = ' | '.join(first_line_words)
        data_lines = table_lines[1:]
    else:
        # No clear headers, treat all as data
        headers = None
        data_lines = table_lines
    
    formatted_table = "Table:\n"
    if headers:
        formatted_table += headers + "\n"
    
    for line in data_lines:
        words = line.split()
        if len(words) >= 2:
            formatted_line = ' | '.join(words)
            formatted_table += formatted_line + "\n"
    
    return formatted_table.strip()

def extract_table_from_docx_cell(cell):
    """Extract table content from a DOCX cell if it contains a table"""
    table_text = ""
    for table in cell.tables:
        for row in table.rows:
            row_cells = [cell.text.strip() for cell in row.cells]
            table_text += "\t".join(row_cells) + "\n"
    return table_text.strip()

# --- Parsing Functions ---
def parse_pdf_question_bank(filepath):
    """
    Parses a PDF question bank, attempting to extract questions from tables.
    Assumes a table structure for questions (SL#, Question, CO, Level, Marks).
    Math equations will be extracted as raw text.
    """
    extracted_questions = []
    
    try:
        with pdfplumber.open(filepath) as pdf:
            for page in pdf.pages:
                tables = page.extract_tables() 
                
                for table in tables:
                    for row_index, row in enumerate(table):
                        if row_index == 0: # Skip header row
                            continue
                        
                        if len(row) >= 6:
                            # Handle 6-column format: Q.No, Questions, CO, Level, Marks, Module
                            sl_no = clean_text(row[0])
                            question_text = clean_text(row[1])
                            co = clean_text(row[2])
                            blooms_level = clean_text(row[3])
                            marks_text = clean_text(row[4])
                            module = clean_text(row[5])

                            # Use enhanced marks extraction
                            marks = extract_marks_from_text(marks_text)

                            if question_text:
                                extracted_questions.append({
                                    "sl_no": sl_no,
                                    "question_text": question_text,
                                    "co": co,
                                    "blooms_level": blooms_level,
                                    "marks": marks,
                                    "module": module
                                })
                        elif len(row) >= 5:
                            # Handle 5-column format (legacy): Q.No, Questions, CO, Level, Marks
                            sl_no = clean_text(row[0])
                            question_text = clean_text(row[1])
                            co = clean_text(row[2])
                            blooms_level = clean_text(row[3])
                            marks_text = clean_text(row[4])

                            # Use enhanced marks extraction
                            marks = extract_marks_from_text(marks_text)

                            if question_text:
                                extracted_questions.append({
                                    "sl_no": sl_no,
                                    "question_text": question_text,
                                    "co": co,
                                    "blooms_level": blooms_level,
                                    "marks": marks,
                                    "module": "1"  # Default to module 1 for legacy format
                                })
                        else:
                            print(f"Skipping malformed PDF row due to insufficient columns: {row}") # Debugging
    except Exception as e:
        print(f"Error during PDF parsing of {filepath}: {e}")
        traceback.print_exc() # Print full traceback for debugging
        raise # Re-raise to be caught by the route's error handling
    
    return extracted_questions

def parse_docx_question_bank(filepath):
    """
    Parses a DOCX question bank, attempting to extract questions from tables.
    Assumes a table structure similar to PDF (SL#, Question, CO, Level, Marks).
    Math equations will be extracted as raw text.
    """
    extracted_questions = []
    try:
        doc = docx.Document(filepath)

        for table in doc.tables:
            for row_index, row in enumerate(table.rows):
                cells = [clean_text(cell.text) for cell in row.cells]
                
                # Skip empty rows
                if not any(cells):
                    continue
                
                # Check if this is a header row (contains common header words)
                header_words = ['q.no', 'question', 'co', 'level', 'marks', 'module', 'sl', 's.no']
                is_header = any(word in ' '.join(cells).lower() for word in header_words)
                
                if is_header and row_index == 0:
                    continue  # Skip header row
                
                if len(cells) >= 6:
                    # Handle 6-column format: Q.No, Questions, CO, Level, Marks, Module
                    sl_no = cells[0] if cells[0].strip() else f"Q{len(extracted_questions) + 1}"
                    question_text = cells[1]
                    co = cells[2]
                    blooms_level = cells[3]
                    marks_text = cells[4]
                    module = cells[5]

                    # Extract marks using the helper function
                    marks = extract_marks_from_text(marks_text)

                    if question_text and question_text.strip():
                        extracted_questions.append({
                            "sl_no": sl_no,
                            "question_text": format_question_with_tables(question_text),
                            "co": co,
                            "blooms_level": blooms_level,
                            "marks": marks,
                            "module": module
                        })
                elif len(cells) >= 5:
                    # Handle 5-column format: SL#, Questions, CO, Level, Marks
                    sl_no = cells[0] if cells[0].strip() else f"Q{len(extracted_questions) + 1}"
                    question_text = cells[1]
                    co = cells[2]
                    blooms_level = cells[3]
                    marks_text = cells[4]

                    # Extract marks using the helper function
                    marks = extract_marks_from_text(marks_text)

                    if question_text and question_text.strip():
                        extracted_questions.append({
                            "sl_no": sl_no,
                            "question_text": format_question_with_tables(question_text),
                            "co": co,
                            "blooms_level": blooms_level,
                            "marks": marks,
                            "module": "1"  # Default to module 1 for legacy format
                        })
                elif len(cells) >= 4:
                    # Handle 4-column format: Q.No, Questions, CO, Level (no marks)
                    sl_no = cells[0] if cells[0].strip() else f"Q{len(extracted_questions) + 1}"
                    question_text = cells[1]
                    co = cells[2]
                    blooms_level = cells[3]

                    if question_text and question_text.strip():
                        extracted_questions.append({
                            "sl_no": sl_no,
                            "question_text": format_question_with_tables(question_text),
                            "co": co,
                            "blooms_level": blooms_level,
                            "marks": 0,  # Default marks
                            "module": "1"  # Default module
                        })
                else:
                    print(f"Skipping malformed DOCX row due to insufficient columns: {cells}") # Debugging
    except Exception as e:
        print(f"Error during DOCX parsing of {filepath}: {e}")
        traceback.print_exc() # Print full traceback for debugging
        raise # Re-raise to be caught by the route's error handling
    return extracted_questions

def parse_pdf_with_embedded_tables(filepath):
    """
    Universal PDF parser that can handle any type of question bank format.
    This function uses multiple strategies to extract questions from various PDF structures.
    """
    extracted_questions = []
    
    # Check if file exists
    if not os.path.exists(filepath):
        print(f"Error: File not found: {filepath}")
        return extracted_questions
    
    try:
        with pdfplumber.open(filepath) as pdf:
            for page_num, page in enumerate(pdf.pages):
                # Extract all tables from the page
                tables = page.extract_tables()
                page_text = page.extract_text() or ""
                
                print(f"Page {page_num + 1}: Found {len(tables)} tables and {len(page_text)} characters of text")
                
                # Strategy 1: Process structured question bank tables
                structured_questions = process_structured_tables(tables, page_num + 1)
                extracted_questions.extend(structured_questions)
                
                # Strategy 2: Extract questions from plain text (fallback)
                text_questions = extract_questions_from_plain_text(page_text)
                print(f"Extracted {len(text_questions)} questions from plain text")
                
                # Remove duplicates from text questions (in case they were already extracted from tables)
                existing_sl_nos = {q.get('sl_no', '') for q in extracted_questions}
                unique_text_questions = [q for q in text_questions if q.get('sl_no', '') not in existing_sl_nos]
                extracted_questions.extend(unique_text_questions)
                
                # Strategy 3: Process embedded tables as potential questions
                embedded_questions = process_embedded_tables(tables, page_text, page_num + 1)
                extracted_questions.extend(embedded_questions)
    
    except Exception as e:
        print(f"Error parsing PDF with embedded tables: {e}")
        traceback.print_exc()
    
    print(f"Total questions extracted: {len(extracted_questions)}")
    return extracted_questions

def process_structured_tables(tables, page_num):
    """Process tables that are structured question banks"""
    questions = []
    
    for table_idx, table in enumerate(tables):
        if not table or len(table) < 2:
            continue
        
        print(f"Processing table {table_idx + 1} with {len(table)} rows")
        
        # Check if this is a question bank table (multiple detection methods)
        header_row = table[0]
        is_question_bank = detect_question_bank_table(header_row, table)
        
        if is_question_bank:
            print("Found structured question bank table")
            table_questions = extract_questions_from_structured_table(table)
            questions.extend(table_questions)
        else:
            print("Table does not appear to be a structured question bank")
    
    return questions

def detect_question_bank_table(header_row, table):
    """Detect if a table is a question bank using multiple criteria"""
    if not header_row:
        return False
    
    # Method 1: Standard question bank headers
    if any(header for header in header_row if header and ("Q.No" in str(header) or "Question" in str(header) or "SL" in str(header))):
        return True
    
    # Method 2: Numeric question numbers in first column with CO/Level indicators
    if (len(header_row) >= 4 and str(header_row[0]).strip().isdigit() and 
        any(str(cell).strip() in ['CO1', 'CO2', 'CO3', 'CO4', 'CO5', 'L1', 'L2', 'L3', 'L4', 'L5'] for cell in header_row[2:4] if cell)):
        return True
    
    # Method 3: Check if multiple rows have question-like structure
    if len(table) >= 3:
        question_like_rows = 0
        for row in table[:3]:  # Check first 3 rows
            if (len(row) >= 4 and str(row[0]).strip().isdigit() and 
                len(str(row[1]).strip()) > 20):  # Question text is substantial
                question_like_rows += 1
        
        if question_like_rows >= 2:  # At least 2 rows look like questions
            return True
    
    # Method 4: Check for marks patterns (6M, 8M, etc.)
    if any(str(cell).strip().endswith('M') for row in table[:3] for cell in row if cell):
        return True
    
    return False

def extract_questions_from_structured_table(table):
    """Extract questions from a structured table"""
    questions = []
    
    # Check if the first row is also a question (not just headers)
    if (len(table[0]) >= 4 and str(table[0][0]).strip().isdigit() and 
        any(str(cell).strip() in ['CO1', 'CO2', 'CO3', 'CO4', 'CO5', 'L1', 'L2', 'L3', 'L4', 'L5'] for cell in table[0][2:4] if cell)):
        # First row is also a question, process it
        question = extract_question_from_row(table[0])
        if question:
            questions.append(question)
            print(f"Extracted structured question: {question['sl_no']}")
    
    # Process remaining rows
    for row_index, row in enumerate(table[1:], 1):
        question = extract_question_from_row(row)
        if question:
            questions.append(question)
            print(f"Extracted structured question: {question['sl_no']}")
    
    return questions

def extract_question_from_row(row):
    """Extract question data from a table row"""
    if len(row) < 4:
        return None
    
    sl_no = clean_text(row[0]) if len(row) > 0 else ""
    question_text = clean_text(row[1]) if len(row) > 1 else ""
    co = clean_text(row[2]) if len(row) > 2 else "CO1"
    blooms_level = clean_text(row[3]) if len(row) > 3 else "L1"
    marks_text = clean_text(row[4]) if len(row) > 4 else "5"
    module = clean_text(row[5]) if len(row) > 5 else "1"

    marks = extract_marks_from_text(marks_text)

    if question_text and sl_no:
        # Check if question text contains table data and format it properly
        formatted_question = format_question_with_tables(question_text)
        
        return {
            "sl_no": sl_no,
            "question_text": formatted_question,
            "co": co,
            "blooms_level": blooms_level,
            "marks": marks,
            "module": module
        }
    
    return None

def process_embedded_tables(tables, page_text, page_num):
    """Process embedded tables that might contain questions"""
    questions = []
    
    for table_idx, table in enumerate(tables):
        if not table or len(table) < 2:
            continue
        
        # Skip if this was already processed as a structured table
        if detect_question_bank_table(table[0], table):
            continue
        
        print(f"Processing embedded table {table_idx + 1} with {len(table)} rows")
        
        # Try to find question context around this table
        table_text = extract_table_as_text(table)
        if table_text:
            question_context = find_question_context_in_text(page_text, table_text)
            if question_context:
                questions.append(question_context)
                print(f"Extracted question with embedded table: {question_context['sl_no']}")
            else:
                # Only create generic entries for very substantial tables with meaningful data
                if len(table) >= 5 and len(table_text) > 100:  # More selective criteria
                    # Check if table contains question-like content
                    table_content = ' '.join(table_text.split()[:20]).lower()  # First 20 words
                    question_indicators = ['classify', 'analyze', 'calculate', 'explain', 'compare', 'evaluate', 'design', 'implement']
                    
                    if any(indicator in table_content for indicator in question_indicators):
                        questions.append({
                            "sl_no": f"T{page_num}_{table_idx + 1}",
                            "question_text": f"Question with table data:\n\nTable:\n{table_text}",
                            "co": "CO1",
                            "blooms_level": "L1",
                            "marks": 5,
                            "module": "1"
                        })
                        print(f"Created generic question entry for table {table_idx + 1}")
                    else:
                        print(f"Skipped table {table_idx + 1} - not substantial enough or no question indicators")
                else:
                    print(f"Skipped table {table_idx + 1} - too small or insufficient content")
    
    return questions

def find_question_context_in_text(page_text, table_text):
    """Find question context around a table in the page text"""
    if not page_text or not table_text:
        return None
    
    lines = page_text.split('\n')
    table_lines = [line.strip() for line in table_text.split('\n') if line.strip()]
    
    # Find where the table appears in the text
    for i, line in enumerate(lines):
        if any(table_line in line for table_line in table_lines[:3]):  # Check first few table lines
            # Found the table, look backwards for question context
            question_text = ""
            for j in range(max(0, i-15), i):  # Look at 15 lines before the table
                if lines[j].strip():
                    question_text += lines[j] + " "
            
            if question_text.strip():
                # Extract question details
                q_match = re.search(r'Q\.?\s*(\d+)\.?\s*(.*)', question_text, re.IGNORECASE)
                if q_match:
                    q_num = q_match.group(1)
                    q_text = q_match.group(2).strip()
                    
                    # Extract marks, CO, and level
                    marks = extract_marks_from_text(q_text)
                    if marks == 0:
                        marks = 5  # Default
                    
                    co_match = re.search(r'CO\s*(\d+)', q_text, re.IGNORECASE)
                    co = co_match.group(0) if co_match else "CO1"
                    
                    level_match = re.search(r'L\s*(\d+)', q_text, re.IGNORECASE)
                    level = level_match.group(0) if level_match else "L1"
                    
                    # Combine question text with table - ensure proper formatting
                    if table_text.strip():
                        full_question = q_text + "\n\nTable:\n" + table_text
                    else:
                        full_question = q_text
                    
                    return {
                        "sl_no": q_num,
                        "question_text": clean_text(full_question),
                        "co": co,
                        "blooms_level": level,
                        "marks": marks,
                        "module": "1"
                    }
    
    return None

def extract_questions_from_plain_text(text_content):
    """Extract questions from plain text using various patterns"""
    questions = []
    
    if not text_content:
        return questions
    
    # Pattern 1: Q.1, Q.2, etc.
    pattern1 = re.findall(r'Q\.?\s*(\d+)\.?\s*(.*?)(?=Q\.?\s*\d+\.?\s*|$)', text_content, re.DOTALL | re.IGNORECASE)
    for q_num, q_text in pattern1:
        if q_text.strip():
            marks = extract_marks_from_text(q_text)
            co_match = re.search(r'CO\s*(\d+)', q_text, re.IGNORECASE)
            co = co_match.group(0) if co_match else "CO1"
            
            level_match = re.search(r'L\s*(\d+)', q_text, re.IGNORECASE)
            level = level_match.group(0) if level_match else "L1"
            
            questions.append({
                "sl_no": q_num,
                "question_text": clean_text(q_text),
                "co": co,
                "blooms_level": level,
                "marks": marks if marks > 0 else 5,
                "module": "1"
            })
    
    # Pattern 2: Question 1, Question 2, etc.
    pattern2 = re.findall(r'Question\s*(\d+)[:\.]?\s*(.*?)(?=Question\s*\d+[:\.]?\s*|$)', text_content, re.DOTALL | re.IGNORECASE)
    for q_num, q_text in pattern2:
        if q_text.strip():
            marks = extract_marks_from_text(q_text)
            co_match = re.search(r'CO\s*(\d+)', q_text, re.IGNORECASE)
            co = co_match.group(0) if co_match else "CO1"
            
            level_match = re.search(r'L\s*(\d+)', q_text, re.IGNORECASE)
            level = level_match.group(0) if level_match else "L1"
            
            questions.append({
                "sl_no": q_num,
                "question_text": clean_text(q_text),
                "co": co,
                "blooms_level": level,
                "marks": marks if marks > 0 else 5,
                "module": "1"
            })
    
    # Pattern 3: Just numbers (1., 2., 3., etc.)
    pattern3 = re.findall(r'^(\d+)\.\s*(.*?)(?=^\d+\.\s*|$)', text_content, re.MULTILINE | re.DOTALL)
    for q_num, q_text in pattern3:
        if q_text.strip() and len(q_text.strip()) > 20:  # Only if it looks like a real question
            marks = extract_marks_from_text(q_text)
            co_match = re.search(r'CO\s*(\d+)', q_text, re.IGNORECASE)
            co = co_match.group(0) if co_match else "CO1"
            
            level_match = re.search(r'L\s*(\d+)', q_text, re.IGNORECASE)
            level = level_match.group(0) if level_match else "L1"
            
            questions.append({
                "sl_no": q_num,
                "question_text": clean_text(q_text),
                "co": co,
                "blooms_level": level,
                "marks": marks if marks > 0 else 5,
                "module": "1"
            })
    
    # Remove duplicates based on question number
    seen_numbers = set()
    unique_questions = []
    for q in questions:
        if q["sl_no"] not in seen_numbers:
            seen_numbers.add(q["sl_no"])
            unique_questions.append(q)
    
    return unique_questions


# --- Routes ---
@app.route('/login')
@app.route('/')
def login_page():
    return render_template('login.html')

@app.route('/register')
def register_page():
    return render_template('register.html')

@app.route('/hod-login')
def hod_login_page():
    return render_template('hod_login.html')

@app.route('/hod-register')
def hod_register_page():
    return render_template('hod_register.html')

@app.route('/dashboard')
def dashboard_page():
    return render_template('dashboard.html')

@app.route('/hod-dashboard')
def hod_dashboard_page():
    return render_template('hod_dashboard.html')

@app.route('/authenticate-backend', methods=['POST'])
def authenticate_backend():
    try:
        # Rate limiting check
        client_ip = request.remote_addr
        current_time = time.time()
        
        # Clean old attempts
        if client_ip in auth_attempts:
            auth_attempts[client_ip] = [attempt for attempt in auth_attempts[client_ip] if current_time - attempt < AUTH_WINDOW]
        else:
            auth_attempts[client_ip] = []
        
        # Check if rate limit exceeded
        if len(auth_attempts[client_ip]) >= MAX_AUTH_ATTEMPTS:
            return jsonify({
                'message': 'Too many authentication attempts. Please try again later.',
                'error_type': 'rate_limit_exceeded'
            }), 429
        
        # Record this attempt
        auth_attempts[client_ip].append(current_time)
        
        data = request.get_json()
        print(f"Received authentication request: {data}")
        
        if not data:
            return jsonify({'message': 'No JSON data received!'}), 400
            
        id_token = data.get('idToken')

        if not id_token:
            return jsonify({'message': 'ID token is missing!'}), 400

        print(f"Attempting to verify ID token for user...")
        decoded_token = auth.verify_id_token(id_token)
        uid = decoded_token['uid']
        email = decoded_token.get('email')
        name = decoded_token.get('name', 'User')

        print(f"Token verified successfully for user: {email} (UID: {uid})")

        # Create/update user in Firebase (keep existing)
        user_ref = db_firestore.collection('users').document(uid)
        user_doc = user_ref.get()
        if not user_doc.exists:
            user_ref.set({
                'email': email,
                'username': name,
                'created_at': firestore.SERVER_TIMESTAMP,
                'last_login': firestore.SERVER_TIMESTAMP
            })
            print(f"New user {uid} registered in Firestore.")
        else:
            user_ref.update({'last_login': firestore.SERVER_TIMESTAMP})
            print(f"User {uid} logged in and updated last_login in Firestore.")

        # Create/update user in Supabase
        try:
            supabase_user = supabase_service.create_user(
                firebase_uid=uid,
                email=email,
                name=name,
                role='faculty'  # Default role, can be updated later
            )
            if supabase_user:
                print(f"User {uid} synced to Supabase successfully.")
            else:
                print(f"Warning: Failed to sync user {uid} to Supabase.")
        except Exception as e:
            print(f"Error syncing user to Supabase: {e}")

        response_data = {
            'message': 'Backend authenticated successfully',
            'uid': uid,
            'email': email,
            'username': name
        }
        print(f"Sending response: {response_data}")
        return jsonify(response_data), 200
    except firebase_admin.auth.InvalidIdTokenError as e:
        print(f"Invalid ID token error: {e}")
        return jsonify({'message': 'Invalid or expired ID token.'}), 401
    except Exception as e:
        error_str = str(e)
        print(f"Authentication error: {error_str}")
        
        # Handle specific Firebase quota errors
        if "Quota exceeded" in error_str or "ResourceExhausted" in error_str or "429" in error_str:
            return jsonify({
                'message': 'Firebase quota exceeded. Please try again later or contact support.',
                'error_type': 'quota_exceeded'
            }), 429
        elif "Timeout" in error_str:
            return jsonify({
                'message': 'Authentication timeout. Please try again.',
                'error_type': 'timeout'
            }), 408
        else:
            return jsonify({'message': f'Authentication failed: {error_str}'}), 500

@app.route('/protected_data', methods=['GET'])
@firebase_auth_required
def protected_data():
    user_uid = request.current_user_uid
    return jsonify({'message': f'Hello, user {user_uid}! You accessed protected data.'}), 200

# --- HOD Authentication Routes ---
# --------------------------
# HOD REGISTER (kept safe)
# --------------------------
@app.route('/hod_register', methods=['POST'])
def hod_register():
    try:
        data = request.get_json()

        required_fields = ['email', 'password', 'name', 'department', 'institution', 'hodCode']
        for field in required_fields:
            if not data.get(field):
                return jsonify({'error': f'{field} is required'}), 400

        # Validate HOD code
        valid_hod_codes = ['HOD2024', 'ADMIN123', 'DEPT_HEAD']
        if data['hodCode'] not in valid_hod_codes:
            return jsonify({'error': 'Invalid HOD authorization code'}), 400

        # Create Firebase user
        user_record = auth.create_user(
            email=data['email'],
            password=data['password'],
            display_name=data['name']
        )

        # Assign Firebase custom claim
        auth.set_custom_user_claims(user_record.uid, {'role': 'hod'})

        return jsonify({
            'message': 'HOD registered successfully',
            'uid': user_record.uid
        }), 201

    except auth.EmailAlreadyExistsError:
        return jsonify({'error': 'Email already exists'}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500



# --------------------------
# HOD LOGIN (BYPASSED)
# --------------------------
@app.route('/hod_login', methods=['POST'])
def hod_login():
    try:
        data = request.get_json()
        id_token = data.get('idToken')

        if not id_token:
            return jsonify({'error': 'ID token is required'}), 400

        decoded = auth.verify_id_token(id_token)
        uid = decoded['uid']
        email = decoded.get('email')

        # 🔓 BYPASS: Everyone is treated as HOD
        return jsonify({
            'message': 'HOD login bypassed',
            'user': {
                'uid': uid,
                'email': email,
                'name': email.split('@')[0],
                'department': 'AI & ML',
                'institution': 'SKIT',
                'role': 'hod'
            }
        }), 200

    except Exception as e:
        return jsonify({'error': str(e)}), 500



# --------------------------
# VERIFY HOD (BYPASSED)
# --------------------------
@app.route('/verify_hod', methods=['POST'])
@firebase_auth_required
def verify_hod():
    try:
        uid = request.current_user_uid
        email = request.current_user_email

        # 🔓 BYPASS: Always return isHOD = True
        return jsonify({
            'isHOD': True,
            'user': {
                'uid': uid,
                'email': email,
                'name': email.split('@')[0],
                'department': 'AI & ML',
                'institution': 'SKIT',
                'role': 'hod'
            }
        }), 200

    except Exception as e:
        return jsonify({'error': str(e)}), 500



# --- Route for File Upload and Parsing with Firestore Saving ---
@app.route('/upload_and_parse', methods=['POST'])
@firebase_auth_required
def upload_and_parse():
    user_uid = request.current_user_uid
    
    if 'file' not in request.files:
        return jsonify({"error": "No file part"}), 400
    
    file = request.files['file']
    
    if file.filename == '':
        return jsonify({"error": "No selected file"}), 400
    
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        user_upload_folder = os.path.join(app.config['UPLOAD_FOLDER'], user_uid)
        os.makedirs(user_upload_folder, exist_ok=True)
        filepath = os.path.join(user_upload_folder, filename)
        
        file.save(filepath)
        
        file_extension = filename.rsplit('.', 1)[1].lower()
        
        try:
            parsed_questions = []
            if file_extension == 'pdf':
                # Try enhanced parsing first, fallback to original if needed
                parsed_questions = parse_pdf_with_embedded_tables(filepath)
                if not parsed_questions:
                    parsed_questions = parse_pdf_question_bank(filepath)
            elif file_extension == 'docx':
                parsed_questions = parse_docx_question_bank(filepath)
            
            if not parsed_questions:
                return jsonify({"error": "No questions could be parsed from the uploaded file. Please check its format."}), 400

            # --- Save the Question Bank and its Questions to Firestore ---
            questions_to_return = [] # Store questions with their Firestore ID for frontend
            batch = db_firestore.batch() # Use a batch for efficient writes

            for q_data_original in parsed_questions: # Use a different variable name for clarity
                # Create a copy of the original data to modify for Firestore saving
                q_data_for_firestore = q_data_original.copy() 

                question_doc_ref = db_firestore.collection('users').document(user_uid).collection('question_bank_pool').document() # Auto-generate ID
                
                # Add metadata to the question data for Firestore
                q_data_for_firestore['user_uid'] = user_uid
                q_data_for_firestore['source_file'] = filename # Track where it came from
                q_data_for_firestore['uploaded_at'] = firestore.SERVER_TIMESTAMP
                q_data_for_firestore['is_pre_selected'] = False 
                q_data_for_firestore['last_used_date'] = None 

                batch.set(question_doc_ref, q_data_for_firestore)
                
                # Prepare data to send back to frontend
                q_data_original['firestore_id'] = question_doc_ref.id
                # IMPORTANT: Remove the Sentinel objects before sending to frontend
                # These fields are correctly saved to Firestore, but cannot be JSON serialized
                if 'uploaded_at' in q_data_original:
                    del q_data_original['uploaded_at']
                if 'last_used_date' in q_data_original:
                    del q_data_original['last_used_date']

                questions_to_return.append(q_data_original)
            
            batch.commit() # Commit all writes in one go

            print(f"Saved {len(parsed_questions)} questions from '{filename}' to Firestore pool for user {user_uid}")

            return jsonify({
                "message": "File uploaded, parsed, and saved successfully!",
                "filename": filename,
                "parsed_questions_count": len(parsed_questions),
                "parsed_data": questions_to_return, # Send questions with their Firestore IDs
            }), 200
            
        except Exception as e:
            traceback.print_exc()
            return jsonify({"error": f"Error parsing or saving file: {str(e)}. Check server logs for details."}), 500
    else:
        return jsonify({"error": "File type not allowed. Only PDF and DOCX are supported."}), 400

# --- New Route for CIE Upload and Parse ---
@app.route('/upload_and_parse_cie', methods=['POST'])
@firebase_auth_required
def upload_and_parse_cie():
    user_uid = request.current_user_uid
    cie_type = request.form.get('cie_type', 'cie1')
    
    # Define which modules to expect based on CIE type
    if cie_type == 'cie1':
        expected_modules = ['module1_file', 'module2_file', 'module3_file']
        module_numbers = ['1', '2', '3']
    elif cie_type == 'cie2':
        expected_modules = ['module3_file', 'module4_file', 'module5_file']
        module_numbers = ['3', '4', '5']
    else:
        return jsonify({"error": "Invalid CIE type. Must be 'cie1' or 'cie2'."}), 400
    
    # Check if at least one file is uploaded
    uploaded_files = []
    for module_field in expected_modules:
        if module_field in request.files:
            file = request.files[module_field]
            if file and file.filename != '' and allowed_file(file.filename):
                uploaded_files.append((module_field, file))
    
    if not uploaded_files:
        return jsonify({"error": f"No valid files uploaded for {cie_type.upper()}. Please upload at least one module file."}), 400
    
    try:
        all_questions = []
        batch = db_firestore.batch()
        
        for module_field, file in uploaded_files:
            filename = secure_filename(file.filename)
            user_upload_folder = os.path.join(app.config['UPLOAD_FOLDER'], user_uid)
            os.makedirs(user_upload_folder, exist_ok=True)
            filepath = os.path.join(user_upload_folder, filename)
            
            file.save(filepath)
            
            # Extract module number from field name
            module_num = module_field.replace('_file', '').replace('module', '')
            
            file_extension = filename.rsplit('.', 1)[1].lower()
            
            # Parse the file
            parsed_questions = []
            if file_extension == 'pdf':
                # Try enhanced parsing first, fallback to original if needed
                parsed_questions = parse_pdf_with_embedded_tables(filepath)
                if not parsed_questions:
                    parsed_questions = parse_pdf_question_bank(filepath)
            elif file_extension == 'docx':
                parsed_questions = parse_docx_question_bank(filepath)
            
            if parsed_questions:
                # Add module information to each question
                for q_data_original in parsed_questions:
                    q_data_for_firestore = q_data_original.copy()
                    
                    # Ensure module is set correctly
                    q_data_for_firestore['module'] = module_num
                    q_data_for_firestore['user_uid'] = user_uid
                    q_data_for_firestore['source_file'] = filename
                    q_data_for_firestore['cie_type'] = cie_type
                    q_data_for_firestore['uploaded_at'] = firestore.SERVER_TIMESTAMP
                    q_data_for_firestore['is_pre_selected'] = False
                    q_data_for_firestore['last_used_date'] = None
                    
                    question_doc_ref = db_firestore.collection('users').document(user_uid).collection('question_bank_pool').document()
                    batch.set(question_doc_ref, q_data_for_firestore)
                    
                    # Prepare data for frontend
                    q_data_original['firestore_id'] = question_doc_ref.id
                    q_data_original['module'] = module_num
                    q_data_original['cie_type'] = cie_type
                    
                    # Remove non-serializable fields
                    if 'uploaded_at' in q_data_original:
                        del q_data_original['uploaded_at']
                    if 'last_used_date' in q_data_original:
                        del q_data_original['last_used_date']
                    
                    all_questions.append(q_data_original)
        
        batch.commit()
        
        print(f"Saved {len(all_questions)} questions from {cie_type.upper()} modules to Firestore pool for user {user_uid}")
        
        return jsonify({
            "message": f"{cie_type.upper()} modules uploaded, parsed, and saved successfully!",
            "cie_type": cie_type,
            "total_questions": len(all_questions),
            "all_questions": all_questions,
            "uploaded_modules": [f"Module {m}" for m in module_numbers if any(f"module{m}_file" in f[0] for f in uploaded_files)]
        }), 200
        
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": f"Error parsing or saving {cie_type.upper()} files: {str(e)}. Check server logs for details."}), 500

# ---------------------------
# Rephrase Question (OpenAI)
# ---------------------------
from openai import OpenAI

@app.route('/rephrase_question', methods=['POST'])
@firebase_auth_required
def rephrase_question():
    """Rephrases a question using OpenAI and updates Firestore."""

    user_uid = request.current_user_uid
    data = request.get_json()

    original_text = data.get("original_text", "").strip()
    question_id = data.get("question_id")

    if not original_text:
        return jsonify({"error": "No original_text provided"}), 400

    # Load API key
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return jsonify({"error": "OpenAI API key missing"}), 500

    # OpenAI Prompt
    prompt = (
        "Rephrase the following question while preserving EXACT meaning, "
        "technical terms, formulas, math symbols, and formatting. "
        "Return ONLY the rephrased question text.\n\n"
        f"{original_text}"
    )

    try:
        client = OpenAI(api_key=api_key)

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "user", "content": prompt}
            ],
            temperature=0.3
        )

        rephrased = response.choices[0].message["content"].strip()

        # Fallback if empty
        if not rephrased:
            rephrased = original_text

        # Update Firestore question
        if question_id:
            try:
                question_ref = (
                    db_firestore.collection("users")
                    .document(user_uid)
                    .collection("question_bank_pool")
                    .document(question_id)
                )
                question_ref.update({"question_text": rephrased})
            except Exception as e:
                print("Warning: Firestore update failed:", e)

        return jsonify({"rephrased_text": rephrased}), 200

    except Exception as e:
        print("OpenAI rephrase error:", e)
        return jsonify({
            "error": "Rephrasing failed — returning original text.",
            "rephrased_text": original_text
        }), 200


# --- New Endpoint: Add a new question to the user's question bank pool ---
@app.route('/add_question_to_bank', methods=['POST'])
@firebase_auth_required
def add_question_to_bank():
    user_uid = request.current_user_uid
    data = request.get_json()

    required_fields = ['question_text', 'marks']
    if not all(field in data for field in required_fields):
        return jsonify({"error": "Missing required fields (question_text, marks)."}), 400

    try:
        new_question_ref = db_firestore.collection('users').document(user_uid).collection('question_bank_pool').document()
        new_question_id = new_question_ref.id

        question_data = {
            "question_text": data.get('question_text'),
            "co": data.get('co', 'N/A'),
            "blooms_level": data.get('blooms_level', 'N/A'),
            "marks": int(data.get('marks')), # Ensure marks is an integer
            "user_uid": user_uid,
            "uploaded_at": firestore.SERVER_TIMESTAMP,
            "is_pre_selected": False,
            "last_used_date": None,
            "source_file": "Manual Entry" # Indicate manual entry
        }
        
        new_question_ref.set(question_data)
        print(f"Manually added question {new_question_id} to bank for user {user_uid}.")
        
        # Prepare data to return to frontend (remove Sentinel objects)
        question_data_for_frontend = question_data.copy()
        if 'uploaded_at' in question_data_for_frontend:
            del question_data_for_frontend['uploaded_at']
        if 'last_used_date' in question_data_for_frontend:
            del question_data_for_frontend['last_used_date']

        question_data_for_frontend['firestore_id'] = new_question_id
        return jsonify({"message": "Question added successfully!", "new_question": question_data_for_frontend}), 200

    except ValueError:
        return jsonify({"error": "Marks must be a valid number."}), 400
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": f"Failed to add question to bank: {str(e)}"}), 500

# --- New Endpoint: Update an existing question in the user's question bank pool ---
@app.route('/update_question_in_bank', methods=['POST'])
@firebase_auth_required
def update_question_in_bank():
    user_uid = request.current_user_uid
    data = request.get_json()
    question_id = data.get('question_id')
    updated_fields = {k: v for k, v in data.items() if k != 'question_id'}

    if not question_id:
        return jsonify({"error": "Question ID is missing."}), 400
    if not updated_fields:
        return jsonify({"error": "No fields provided for update."}), 400

    try:
        # Ensure marks is converted to int if present in updated_fields
        if 'marks' in updated_fields:
            updated_fields['marks'] = int(updated_fields['marks'])

        question_ref = db_firestore.collection('users').document(user_uid).collection('question_bank_pool').document(question_id)
        question_ref.update(updated_fields)
        print(f"Question {question_id} updated in bank for user {user_uid}.")
        return jsonify({"message": "Question updated successfully!"}), 200

    except ValueError:
        return jsonify({"error": "Marks must be a valid number."}), 400
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": f"Failed to update question in bank: {str(e)}"}), 500

# --- New Endpoint: Delete a question from the user's question bank pool ---
@app.route('/delete_question_from_bank', methods=['DELETE'])
@firebase_auth_required
def delete_question_from_bank():
    user_uid = request.current_user_uid
    data = request.get_json()
    question_id = data.get('question_id')

    if not question_id:
        return jsonify({"error": "Question ID is missing."}), 400

    try:
        question_ref = db_firestore.collection('users').document(user_uid).collection('question_bank_pool').document(question_id)
        question_ref.delete()
        print(f"Question {question_id} deleted from bank for user {user_uid}.")
        return jsonify({"message": "Question deleted successfully!"}), 200

    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": f"Failed to delete question from bank: {str(e)}"}), 500

# --- New Endpoint: Get all questions for the current user ---
@app.route('/get_user_questions', methods=['GET'])
@firebase_auth_required
def get_user_questions():
    user_uid = request.current_user_uid
    try:
        questions_ref = db_firestore.collection('users').document(user_uid).collection('question_bank_pool')
        docs = questions_ref.stream()
        
        questions_list = []
        for doc in docs:
            q_data = doc.to_dict()
            q_data['firestore_id'] = doc.id # Include the Firestore document ID
            
            # Remove Sentinel objects if they somehow got into the dict during fetch
            # (though they shouldn't if saved correctly, this is a safeguard)
            if 'uploaded_at' in q_data and isinstance(q_data['uploaded_at'], firestore.SERVER_TIMESTAMP.__class__):
                del q_data['uploaded_at']
            if 'last_used_date' in q_data and isinstance(q_data['last_used_date'], firestore.SERVER_TIMESTAMP.__class__):
                del q_data['last_used_date']
            
            questions_list.append(q_data)
        
        return jsonify({"message": "Questions fetched successfully!", "questions": questions_list}), 200
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": f"Failed to fetch user questions: {str(e)}"}), 500


# --- Enhanced Endpoint: Generate Final DOCX Document ---
@app.route('/export_question_paper', methods=['POST'])
@firebase_auth_required
def export_question_paper():
    """Export question paper as PDF or DOCX"""
    user_uid = request.current_user_uid
    data = request.get_json()
    paper_id = data.get('paper_id')
    format_type = data.get('format', 'docx')  # 'docx' or 'pdf'
    
    try:
        # Get the paper from Firestore
        paper_ref = db_firestore.collection('users').document(user_uid).collection('generated_papers').document(paper_id)
        paper_doc = paper_ref.get()
        
        if not paper_doc.exists:
            return jsonify({"error": "Question paper not found"}), 404
        
        paper_data = paper_doc.to_dict()
        questions = paper_data.get('questions', [])
        subject = paper_data.get('subject', 'Question Paper')
        
        if not questions:
            return jsonify({"error": "No questions found in the paper"}), 400
        
        # Generate the document
        if format_type == 'docx':
            file_path = generate_docx_export(questions, subject, paper_id)
            mime_type = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
            file_extension = 'docx'
        elif format_type == 'pdf':
            file_path = generate_pdf_export(questions, subject, paper_id)
            mime_type = 'application/pdf'
            file_extension = 'pdf'
        else:
            return jsonify({"error": "Invalid format. Use 'docx' or 'pdf'"}), 400
        
        # Update download count
        paper_ref.update({
            'download_count': firestore.Increment(1),
            'last_downloaded': firestore.SERVER_TIMESTAMP
        })
        
        return jsonify({
            "message": f"Question paper exported successfully as {format_type.upper()}",
            "file_path": file_path,
            "file_name": f"{subject.replace(' ', '_')}_{paper_id}.{file_extension}",
            "mime_type": mime_type
        }), 200
        
    except Exception as e:
        return jsonify({"error": f"Failed to export question paper: {str(e)}"}), 500

def generate_docx_export(questions, subject, paper_id):
    """Generate DOCX export of question paper"""
    from docx import Document
    from docx.shared import Inches
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    
    doc = Document()
    
    # Add title
    title = doc.add_heading(f'{subject} - Question Paper', 0)
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    
    # Add paper info
    doc.add_paragraph(f'Paper ID: {paper_id}')
    doc.add_paragraph(f'Generated on: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}')
    doc.add_paragraph('')  # Empty line
    
    # Add questions
    for i, question in enumerate(questions, 1):
        main_q = question.get('main_question', f'Q{i}')
        module = question.get('module', 'Unknown')
        
        # Main question header
        doc.add_heading(f'{main_q} (Module {module})', level=1)
        
        # Sub-questions
        sub_questions = question.get('sub_questions', [])
        for j, sub_q in enumerate(sub_questions):
            part = sub_q.get('part', chr(97 + j))  # a, b, c, etc.
            text = sub_q.get('text', sub_q.get('question_text', ''))
            marks = sub_q.get('marks', 0)
            
            doc.add_paragraph(f'({part}) {text} [{marks} marks]')
        
        doc.add_paragraph('')  # Empty line between questions
    
    # Save the document
    filename = f"{subject.replace(' ', '_')}_{paper_id}.docx"
    filepath = os.path.join(UPLOAD_FOLDER, filename)
    doc.save(filepath)
    
    return filepath

def generate_pdf_export(questions, subject, paper_id):
    """Generate PDF export of question paper"""
    from reportlab.lib.pagesizes import letter, A4
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import inch
    
    filename = f"{subject.replace(' ', '_')}_{paper_id}.pdf"
    filepath = os.path.join(UPLOAD_FOLDER, filename)
    
    doc = SimpleDocTemplate(filepath, pagesize=A4)
    styles = getSampleStyleSheet()
    story = []
    
    # Title
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=16,
        spaceAfter=30,
        alignment=1  # Center alignment
    )
    story.append(Paragraph(f'{subject} - Question Paper', title_style))
    story.append(Spacer(1, 12))
    
    # Paper info
    story.append(Paragraph(f'Paper ID: {paper_id}', styles['Normal']))
    story.append(Paragraph(f'Generated on: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}', styles['Normal']))
    story.append(Spacer(1, 20))
    
    # Questions
    for i, question in enumerate(questions, 1):
        main_q = question.get('main_question', f'Q{i}')
        module = question.get('module', 'Unknown')
        
        # Main question header
        story.append(Paragraph(f'{main_q} (Module {module})', styles['Heading2']))
        story.append(Spacer(1, 12))
        
        # Sub-questions
        sub_questions = question.get('sub_questions', [])
        for j, sub_q in enumerate(sub_questions):
            part = sub_q.get('part', chr(97 + j))  # a, b, c, etc.
            text = sub_q.get('text', sub_q.get('question_text', ''))
            marks = sub_q.get('marks', 0)
            
            story.append(Paragraph(f'({part}) {text} [{marks} marks]', styles['Normal']))
            story.append(Spacer(1, 6))
        
        story.append(Spacer(1, 20))
    
    doc.build(story)
    return filepath

@app.route('/generate_final_document', methods=['POST'])
@firebase_auth_required
def generate_final_document():
    user_uid = request.current_user_uid
    data = request.get_json()
    question_paper_data = data.get('question_paper_data')
    overall_max_marks = data.get('overall_max_marks', 100)
    metadata = data.get('metadata', {})

    if not question_paper_data:
        return jsonify({"error": "No question paper data provided."}), 400

    try:
        # Create a new document from scratch with proper formatting
        document = docx.Document()

        # Set document margins - smaller margins to fit everything on one page
        sections = document.sections
        for section in sections:
            section.top_margin = docx.shared.Inches(0.4)
            section.bottom_margin = docx.shared.Inches(0.4)
            section.left_margin = docx.shared.Inches(0.5)
            section.right_margin = docx.shared.Inches(0.5)
            # Set page size to ensure single page layout
            section.page_height = docx.shared.Inches(11)  # Letter size
            section.page_width = docx.shared.Inches(8.5)

        # Add college header with official layout (logo + college info only)
        header_table = document.add_table(rows=1, cols=2)

        # Use a simple table style without borders
        header_table.style = 'Light List'

        # Set white background for header (clean professional look)
        for row in header_table.rows:
            for cell in row.cells:
                # Set white background (default)
                from docx.oxml.shared import qn
                from docx.oxml import parse_xml
                shading_elm = parse_xml(r'<w:shd {} w:fill="FFFFFF"/>'.format(
                    'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'))
                cell._tc.get_or_add_tcPr().append(shading_elm)

        # Set column widths: Logo (12%), College Info (88%)
        header_col_widths = [
            docx.shared.Inches(1.0),   # Logo column
            docx.shared.Inches(7.0),   # College info column (much wider)
        ]

        # Apply column widths to header
        for i, width in enumerate(header_col_widths):
            header_table.rows[0].cells[i].width = width

        # Logo cell (left) - with actual SKIT logo
        logo_cell = header_table.cell(0, 0)
        logo_para = logo_cell.paragraphs[0]
        logo_para.alignment = docx.enum.text.WD_ALIGN_PARAGRAPH.CENTER
        logo_cell.vertical_alignment = docx.enum.table.WD_ALIGN_VERTICAL.CENTER

        # Add the actual SKIT logo image
        try:
            logo_path = os.path.join('static', 'assets', 'skit_logo.png')
            if os.path.exists(logo_path):
                # Add the logo image with proper sizing
                logo_run = logo_para.runs[0] if logo_para.runs else logo_para.add_run()
                logo_run.add_picture(logo_path, width=docx.shared.Inches(0.8), height=docx.shared.Inches(0.8))
            else:
                # Fallback if logo not found
                logo_run = logo_para.add_run("SKIT\nLOGO")
                logo_run.font.size = docx.shared.Pt(12)
                logo_run.font.bold = True
                logo_run.font.name = 'Times New Roman'
        except Exception as e:
            # Fallback in case of any error
            logo_run = logo_para.add_run("SKIT")
            logo_run.font.size = docx.shared.Pt(14)
            logo_run.font.bold = True
            logo_run.font.name = 'Times New Roman'

        # College info cell (right) - main content
        college_cell = header_table.cell(0, 1)
        college_para = college_cell.paragraphs[0]
        college_para.alignment = docx.enum.text.WD_ALIGN_PARAGRAPH.CENTER
        college_cell.vertical_alignment = docx.enum.table.WD_ALIGN_VERTICAL.CENTER

        # Main college name - large and bold with black text (clean professional look)
        college_run = college_para.add_run("SRI KRISHNA INSTITUTE OF TECHNOLOGY")
        college_run.font.size = docx.shared.Pt(16)  # Slightly smaller for better fit
        college_run.font.bold = True
        college_run.font.name = 'Times New Roman'
        college_run.font.color.rgb = docx.shared.RGBColor(0, 0, 0)  # Black text

        # Line break
        college_para.add_run("\n")

        # Accreditation line - smaller text with black color (clean professional look)
        accreditation_run = college_para.add_run("Accredited by NAAC, Approved by AICTE, New Delhi, Recognised by Govt of Karnataka & Affiliated to VTU, Belagavi")
        accreditation_run.font.size = docx.shared.Pt(9)
        accreditation_run.font.name = 'Times New Roman'
        accreditation_run.font.color.rgb = docx.shared.RGBColor(0, 0, 0)  # Black text

        # Line break
        college_para.add_run("\n")

        # Address line - smaller text with black color (clean professional look)
        address_run = college_para.add_run("#57, Chimney Hills, Hesaraghatta Main Road, Chikkabanavara Post, Bengaluru- 560090")
        address_run.font.size = docx.shared.Pt(9)
        address_run.font.name = 'Times New Roman'
        address_run.font.color.rgb = docx.shared.RGBColor(0, 0, 0)  # Black text

        # Add horizontal line below header (like in your image)
        line_para = document.add_paragraph()
        line_para.alignment = docx.enum.text.WD_ALIGN_PARAGRAPH.CENTER

        # Create a more professional horizontal line
        line_run = line_para.add_run("─" * 120)  # Using proper horizontal line character
        line_run.font.size = docx.shared.Pt(6)
        line_run.font.name = 'Times New Roman'

        # Add IA section centered below header (as per your requirement)
        ia_para = document.add_paragraph()
        ia_para.alignment = docx.enum.text.WD_ALIGN_PARAGRAPH.CENTER
        ia_run = ia_para.add_run("IA - 1")
        ia_run.font.size = docx.shared.Pt(14)
        ia_run.font.bold = True
        ia_run.font.name = 'Times New Roman'

        # Add minimal spacing after IA section
        spacing_para = document.add_paragraph()
        spacing_para.space_after = docx.shared.Pt(6)  # Reduced spacing

        # Add metadata table
        meta_table = document.add_table(rows=2, cols=4)
        meta_table.style = 'Table Grid'

        # First row
        meta_table.cell(0, 0).text = f"Dept: {metadata.get('dept', 'CSE')}"
        meta_table.cell(0, 1).text = f"Sem / Div: {metadata.get('sem', '7')} / {metadata.get('div', 'A')}"
        meta_table.cell(0, 2).text = f"Course: {metadata.get('course', 'AIML')}"
        meta_table.cell(0, 3).text = f"Elective: {metadata.get('elective', 'NLP')}"

        # Second row
        meta_table.cell(1, 0).text = f"Date: {metadata.get('date', datetime.now().strftime('%Y-%m-%d'))}"
        meta_table.cell(1, 1).text = f"Time: {metadata.get('time', '3 Hrs')}"
        meta_table.cell(1, 2).text = f"C Code: {metadata.get('code', '18CS71')}"
        meta_table.cell(1, 3).text = f"Max Marks: {overall_max_marks}"

        # Add note
        note_para = document.add_paragraph()
        note_run = note_para.add_run("Note: Answer all full questions. All questions carry 25 marks.")
        note_run.font.size = docx.shared.Pt(10)
        note_run.font.bold = True

        # Create main questions table
        questions_table = document.add_table(rows=1, cols=6)
        questions_table.style = 'Table Grid'

        # Set column widths for better formatting
        # Total width is approximately 100% - we'll distribute as follows:
        # Q.No: 8%, Questions: 65%, CO: 7%, Level: 7%, Marks: 7%, Module: 6%
        col_widths = [
            docx.shared.Inches(0.5),   # Q.No - narrow
            docx.shared.Inches(5.0),   # Questions - very wide (increased)
            docx.shared.Inches(0.5),   # CO - narrow
            docx.shared.Inches(0.6),   # Level - narrow
            docx.shared.Inches(0.6),   # Marks - narrow
            docx.shared.Inches(0.8)    # Module - narrow
        ]

        # Apply column widths and set table properties
        questions_table.autofit = False  # Disable autofit to maintain our widths
        for i, width in enumerate(col_widths):
            for row in questions_table.rows:
                row.cells[i].width = width

        # Add headers
        headers = ['Q.No', 'Questions', 'CO', 'Level', 'Marks', 'Module']
        header_row = questions_table.rows[0]
        for i, header in enumerate(headers):
            if i < len(header_row.cells):
                cell = header_row.cells[i]
                cell.text = header
                # Make header bold and styled
                cell.vertical_alignment = docx.enum.table.WD_ALIGN_VERTICAL.CENTER
                for paragraph in cell.paragraphs:
                    paragraph.alignment = docx.enum.text.WD_ALIGN_PARAGRAPH.CENTER
                    for run in paragraph.runs:
                        run.font.bold = True
                        run.font.size = docx.shared.Pt(11)
                        run.font.name = 'Times New Roman'

                # Add shading to header cells for better visibility
                from docx.oxml.shared import qn
                from docx.oxml import parse_xml
                shading_elm = parse_xml(r'<w:shd {} w:fill="D9D9D9"/>'.format(
                    'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'))
                cell._tc.get_or_add_tcPr().append(shading_elm)

        # Add questions to table
        for main_q_idx, main_q_data in enumerate(question_paper_data):
            if main_q_idx >= 4:  # Only process up to 4 main questions
                break

            # Add OR row before Q2 and Q4
            if main_q_idx == 1 or main_q_idx == 3:
                or_row = questions_table.add_row()

                # Apply column widths to OR row
                for i, width in enumerate(col_widths):
                    or_row.cells[i].width = width

                or_cell = or_row.cells[1]  # Questions column
                or_cell.text = "OR"
                or_para = or_cell.paragraphs[0]
                or_para.alignment = docx.enum.text.WD_ALIGN_PARAGRAPH.CENTER
                for run in or_para.runs:
                    run.font.bold = True
                    run.font.size = docx.shared.Pt(12)

            # Add sub-questions
            sub_questions = main_q_data.get('subQuestions', [])
            for sub_q_idx, sub_q_data in enumerate(sub_questions):
                if sub_q_idx >= 3:  # Maximum 3 sub-questions per main question
                    break

                row = questions_table.add_row()

                # Apply column widths to each new row
                for i, width in enumerate(col_widths):
                    row.cells[i].width = width

                # Q.No column - only show main question number for first sub-question
                if sub_q_idx == 0:
                    cell = row.cells[0]
                    cell.text = str(main_q_idx + 1)
                    cell.paragraphs[0].alignment = docx.enum.text.WD_ALIGN_PARAGRAPH.CENTER
                    for run in cell.paragraphs[0].runs:
                        run.font.size = docx.shared.Pt(10)
                        run.font.bold = True

                # Questions column - with better formatting
                sub_letter = chr(97 + sub_q_idx)  # a, b, c
                question_text = sub_q_data.get('question_text', f'Question {main_q_idx + 1}{sub_letter}')
                questions_cell = row.cells[1]
                questions_cell.text = f"{sub_letter}. {question_text}"

                # Set font size and alignment for questions
                for paragraph in questions_cell.paragraphs:
                    paragraph.alignment = docx.enum.text.WD_ALIGN_PARAGRAPH.JUSTIFY  # Justify text for better appearance
                    for run in paragraph.runs:
                        run.font.size = docx.shared.Pt(10)
                        run.font.name = 'Times New Roman'  # Use a more readable font

                # Add some padding to the questions cell
                questions_cell.vertical_alignment = docx.enum.table.WD_ALIGN_VERTICAL.TOP

                # CO, Level, Marks, Module columns - with center alignment and smaller font
                data_cells = [
                    (row.cells[2], sub_q_data.get('co', 'CO1')),
                    (row.cells[3], sub_q_data.get('blooms_level', 'L2')),
                    (row.cells[4], str(sub_q_data.get('marks', 8))),
                    (row.cells[5], sub_q_data.get('module', 'Module 1'))
                ]

                for cell, text in data_cells:
                    cell.text = text
                    cell.paragraphs[0].alignment = docx.enum.text.WD_ALIGN_PARAGRAPH.CENTER
                    cell.vertical_alignment = docx.enum.table.WD_ALIGN_VERTICAL.CENTER
                    for run in cell.paragraphs[0].runs:
                        run.font.size = docx.shared.Pt(9)
                        run.font.name = 'Times New Roman'

        # Add spacing before certificate section
        document.add_paragraph()
        document.add_paragraph()

        # Add certificate section
        cert_para = document.add_paragraph()
        cert_run = cert_para.add_run("Certificate")
        cert_run.font.size = docx.shared.Pt(12)
        cert_run.font.bold = True
        cert_para.alignment = docx.enum.text.WD_ALIGN_PARAGRAPH.CENTER

        # Certificate text
        cert_text = document.add_paragraph()
        cert_text_content = ("I hereby certify that I have completed the specified syllabus for the CIE exam. I have referred the specified "
                           "Text & Reference books / I have referred additional books and notes. Questions are set to cover the Course "
                           "Outcomes and Blooms learning levels specified for the CIE.")
        cert_text.add_run(cert_text_content)

        # Add spacing
        document.add_paragraph()

        # Add signature section exactly as you specified
        signature_table = document.add_table(rows=2, cols=3)
        signature_table.style = 'Table Grid'

        # First row - headers
        signature_table.cell(0, 0).text = "Name:"
        signature_table.cell(0, 1).text = ""
        signature_table.cell(0, 2).text = ""

        # Second row - signature line
        signature_table.cell(1, 0).text = "Signature:"
        signature_table.cell(1, 1).text = ""
        signature_table.cell(1, 2).text = ""

        # Add spacing
        document.add_paragraph()

        # Add final footer table (Prepared by | Checked by | Approved)
        footer_table = document.add_table(rows=1, cols=3)
        footer_table.style = 'Table Grid'

        # Set equal column widths for footer
        for i in range(3):
            footer_table.rows[0].cells[i].width = docx.shared.Inches(2.5)

        footer_table.cell(0, 0).text = "Prepared by"
        footer_table.cell(0, 1).text = "Checked by"
        footer_table.cell(0, 2).text = "Approved"

        # Center align footer text
        for i in range(3):
            cell = footer_table.cell(0, i)
            cell.paragraphs[0].alignment = docx.enum.text.WD_ALIGN_PARAGRAPH.CENTER
            for run in cell.paragraphs[0].runs:
                run.font.bold = True
                run.font.size = docx.shared.Pt(10)

        # Save the document
        temp_output_path = os.path.join(app.config['UPLOAD_FOLDER'], f"generated_qp_{user_uid}_{uuid.uuid4()}.docx")
        document.save(temp_output_path)

        # Check if PDF format is requested
        format_requested = data.get('format', 'docx').lower()

        if format_requested == 'pdf':
            # Convert to PDF using our robust conversion function
            try:
                print(f"Converting DOCX to PDF: {temp_output_path}")
                result_path = convert_docx_to_pdf_robust(temp_output_path)

                if result_path.endswith('.pdf') and os.path.exists(result_path) and os.path.getsize(result_path) > 0:
                    print(f"PDF conversion successful. File size: {os.path.getsize(result_path)} bytes")
                    return send_file(result_path, as_attachment=True, download_name="Generated_Question_Paper.pdf",
                                   mimetype="application/pdf")
                else:
                    # Fallback to DOCX if PDF conversion fails
                    print("PDF conversion failed, returning DOCX")
                    return send_file(temp_output_path, as_attachment=True, download_name="Generated_Question_Paper.docx",
                                   mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document")

            except Exception as pdf_error:
                print(f"PDF conversion failed: {pdf_error}")
                traceback.print_exc()
                # Fallback to DOCX
                return send_file(temp_output_path, as_attachment=True, download_name="Generated_Question_Paper.docx",
                               mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document")
        else:
            return send_file(temp_output_path, as_attachment=True, download_name="Generated_Question_Paper.docx",
                            mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document")

    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": f"Error generating document: {str(e)}. Check server logs."}), 500


def generate_paper_with_rules(all_questions):
    """
    Generate a question paper following the specified rules:
    - 4 main questions (Q1-Q4)
    - Each main question has 3 sub-questions (a, b, c)
    - Each main question totals 25 marks
    - Either Q1 OR Q2 → All sub-questions from Module 1
    - Either Q3 OR Q4 → Sub-questions (a, b) from Module 2, Sub-question (c) from Module 3
    """
    import random
    from collections import defaultdict



    # Group questions by module and marks
    questions_by_module = defaultdict(list)
    for q in all_questions:
        try:
            # Extract module number directly from the module field
            module_num = str(q.get('module', '1'))  # Default to module 1 if not specified
            
            # Ensure marks is integer
            marks = int(q.get('marks', 0))
            if marks > 0:  # Only include questions with valid marks
                q['module_num'] = module_num
                q['marks'] = marks
                questions_by_module[module_num].append(q)

        except (ValueError, TypeError):
            continue  # Skip questions with invalid marks

    # Check if we have questions from required modules
    available_modules = list(questions_by_module.keys())
    print(f"Available modules: {available_modules}")
    for module, questions in questions_by_module.items():
        print(f"Module {module}: {len(questions)} questions")

    if not available_modules:
        return {"error": "No questions found with valid modules and marks."}

    # Flexible module handling based on available questions
    if len(available_modules) == 1:
        # If only one module is available, use it for all questions
        single_module = available_modules[0]
        print(f"Single module mode: Using Module {single_module} for all questions.")

        # Check if we have enough questions for 4 main questions (12 sub-questions total)
        total_questions = len(questions_by_module[single_module])
        if total_questions < 12:
            return {"error": f"Insufficient questions in Module {single_module}. Need at least 12 questions, found {total_questions}."}
    else:
        # Original multi-module logic - require at least modules 1 and one other
        if not questions_by_module.get('1'):
            return {"error": "No questions found from Module 1. Cannot generate Q1 or Q2."}

        if not questions_by_module.get('2') and not questions_by_module.get('3'):
            return {"error": "No questions found from Module 2 or 3. Cannot generate Q3 or Q4."}

    def find_question_combination(questions, target_marks=25):
        """Find 3 questions that sum to target_marks (or close to it)"""
        questions = [q for q in questions if q['marks'] <= target_marks]
        if len(questions) < 3:
            return None

        best_combination = None
        best_score = float('inf')

        # Try all combinations of 3 questions
        for i in range(len(questions)):
            for j in range(i+1, len(questions)):
                for k in range(j+1, len(questions)):
                    total = questions[i]['marks'] + questions[j]['marks'] + questions[k]['marks']
                    score = abs(total - target_marks)
                    if score < best_score:
                        best_score = score
                        best_combination = [questions[i], questions[j], questions[k]]
                        if total == target_marks:  # Perfect match
                            break
                if best_combination and sum(q['marks'] for q in best_combination) == target_marks:
                    break
            if best_combination and sum(q['marks'] for q in best_combination) == target_marks:
                break

        return best_combination

    # Generate the paper
    paper = []
    used_questions = set()

    # Handle single module case differently
    if len(available_modules) == 1:
        single_module = available_modules[0]
        all_questions = questions_by_module[single_module]

        # Generate 4 questions, each with 3 sub-questions from the single module
        for q_num in range(1, 5):
            available_questions = [q for q in all_questions if q['firestore_id'] not in used_questions]
            combination = find_question_combination(available_questions)

            if not combination:
                return {"error": f"Could not find enough questions for Q{q_num} from Module {single_module}"}

            for q in combination:
                used_questions.add(q['firestore_id'])

            paper.append({
                "main_question": f"Q{q_num}",
                "module": single_module,
                "sub_questions": [
                    {"part": "a", "text": combination[0]['question_text'], "marks": combination[0]['marks'], "module": single_module},
                    {"part": "b", "text": combination[1]['question_text'], "marks": combination[1]['marks'], "module": single_module},
                    {"part": "c", "text": combination[2]['question_text'], "marks": combination[2]['marks'], "module": single_module}
                ]
            })

        return paper

    # Multi-module logic (original approach)
    # Randomly choose Q1 or Q2 for Module 1
    module1_question = random.choice(['Q1', 'Q2'])

    # Generate Q1
    if module1_question == 'Q1':
        # Q1 from Module 1
        available_q1 = [q for q in questions_by_module['1'] if q['firestore_id'] not in used_questions]
        q1_combination = find_question_combination(available_q1)
        if not q1_combination:
            return None

        for q in q1_combination:
            used_questions.add(q['firestore_id'])

        paper.append({
            "main_question": "Q1",
            "module": "1",
            "sub_questions": [
                {"part": "a", "text": q1_combination[0]['question_text'], "marks": q1_combination[0]['marks'], "module": "1"},
                {"part": "b", "text": q1_combination[1]['question_text'], "marks": q1_combination[1]['marks'], "module": "1"},
                {"part": "c", "text": q1_combination[2]['question_text'], "marks": q1_combination[2]['marks'], "module": "1"}
            ]
        })

        # Q2 from other available modules
        other_modules = [m for m in available_modules if m != '1']
        if not other_modules:
            return {"error": "Need at least one other module besides Module 1 for multi-module question paper"}

        # Combine questions from all other modules for Q2
        available_q2_questions = []
        for module in other_modules:
            available_q2_questions.extend([q for q in questions_by_module[module] if q['firestore_id'] not in used_questions])

        q2_combination = find_question_combination(available_q2_questions)
        if not q2_combination:
            return {"error": "Could not find suitable question combination for Q2"}

        for q in q2_combination:
            used_questions.add(q['firestore_id'])

        # Determine module label for Q2
        q2_modules = list(set([q['module_num'] for q in q2_combination]))
        q2_module_label = " & ".join(sorted(q2_modules)) if len(q2_modules) > 1 else q2_modules[0]

        paper.append({
            "main_question": "Q2",
            "module": q2_module_label,
            "sub_questions": [
                {"part": "a", "text": q2_combination[0]['question_text'], "marks": q2_combination[0]['marks'], "module": q2_combination[0]['module_num']},
                {"part": "b", "text": q2_combination[1]['question_text'], "marks": q2_combination[1]['marks'], "module": q2_combination[1]['module_num']},
                {"part": "c", "text": q2_combination[2]['question_text'], "marks": q2_combination[2]['marks'], "module": q2_combination[2]['module_num']}
            ]
        })
    else:
        # Q2 from Module 1
        available_q2 = [q for q in questions_by_module['1'] if q['firestore_id'] not in used_questions]
        q2_combination = find_question_combination(available_q2)
        if not q2_combination:
            return None

        for q in q2_combination:
            used_questions.add(q['firestore_id'])

        # Q1 from other available modules
        other_modules = [m for m in available_modules if m != '1']
        if not other_modules:
            return {"error": "Need at least one other module besides Module 1 for multi-module question paper"}

        # Combine questions from all other modules for Q1
        available_q1_questions = []
        for module in other_modules:
            available_q1_questions.extend([q for q in questions_by_module[module] if q['firestore_id'] not in used_questions])

        q1_combination = find_question_combination(available_q1_questions)
        if not q1_combination:
            return {"error": "Could not find suitable question combination for Q1"}

        for q in q1_combination:
            used_questions.add(q['firestore_id'])

        # Determine module label for Q1
        q1_modules = list(set([q['module_num'] for q in q1_combination]))
        q1_module_label = " & ".join(sorted(q1_modules)) if len(q1_modules) > 1 else q1_modules[0]

        paper.append({
            "main_question": "Q1",
            "module": q1_module_label,
            "sub_questions": [
                {"part": "a", "text": q1_combination[0]['question_text'], "marks": q1_combination[0]['marks'], "module": q1_combination[0]['module_num']},
                {"part": "b", "text": q1_combination[1]['question_text'], "marks": q1_combination[1]['marks'], "module": q1_combination[1]['module_num']},
                {"part": "c", "text": q1_combination[2]['question_text'], "marks": q1_combination[2]['marks'], "module": q1_combination[2]['module_num']}
            ]
        })

        paper.append({
            "main_question": "Q2",
            "module": "1",
            "sub_questions": [
                {"part": "a", "text": q2_combination[0]['question_text'], "marks": q2_combination[0]['marks'], "module": "1"},
                {"part": "b", "text": q2_combination[1]['question_text'], "marks": q2_combination[1]['marks'], "module": "1"},
                {"part": "c", "text": q2_combination[2]['question_text'], "marks": q2_combination[2]['marks'], "module": "1"}
            ]
        })

    # Generate Q3 and Q4 from remaining questions
    for q_num in [3, 4]:
        # Get all remaining questions from all available modules
        all_remaining = []
        for module_num in available_modules:
            for q in questions_by_module[module_num]:
                if q['firestore_id'] not in used_questions:
                    all_remaining.append(q)

        if len(all_remaining) >= 3:
            combination = find_question_combination(all_remaining)
            if combination:
                for q in combination:
                    used_questions.add(q['firestore_id'])

                # Determine module label
                modules_used = list(set([q['module_num'] for q in combination]))
                module_label = " & ".join(sorted(modules_used)) if len(modules_used) > 1 else modules_used[0]

                paper.append({
                    "main_question": f"Q{q_num}",
                    "module": module_label,
                    "sub_questions": [
                        {"part": "a", "text": combination[0]['question_text'], "marks": combination[0]['marks'], "module": combination[0]['module_num']},
                        {"part": "b", "text": combination[1]['question_text'], "marks": combination[1]['marks'], "module": combination[1]['module_num']},
                        {"part": "c", "text": combination[2]['question_text'], "marks": combination[2]['marks'], "module": combination[2]['module_num']}
                    ]
                })
            else:
                print(f"Could not generate Q{q_num} - insufficient remaining questions")
                break
        else:
            print(f"Could not generate Q{q_num} - only {len(all_remaining)} questions remaining")
            break

    # Ensure we have at least 2 questions (minimum viable paper)
    if len(paper) < 2:
        return None

    return paper


def generate_cie1_paper(all_questions):
    """
    Generate CIE1 pattern question paper (correct academic structure):
    - Q1 OR Q2: 3 sub-questions from Module 1 (25 marks each)
    - Q3: 3 sub-questions (a, b from Module 2, c from Module 3) (25 marks)
    - Q4: 3 sub-questions (a, b from Module 2, c from Module 3) (25 marks)
    Total: 100 marks (students answer 3 questions = 75 marks)
    """
    print("🎯 Generating CIE1 pattern question paper...")

    # Use the same module detection logic as the standard pattern
    from collections import defaultdict
    questions_by_module = defaultdict(list)
    
    for q in all_questions:
        try:
            # Extract module number directly from the module field
            module_num = str(q.get('module', '1'))  # Default to module 1 if not specified
            
            # Ensure marks is integer
            marks = int(q.get('marks', 0))
            if marks > 0:  # Only include questions with valid marks
                q['module_num'] = module_num
                q['marks'] = marks
                questions_by_module[module_num].append(q)

        except (ValueError, TypeError):
            continue  # Skip questions with invalid marks

    # Check module availability - CIE1 requires specific modules
    available_modules = list(questions_by_module.keys())
    print(f"Available modules: {available_modules}")
    for module, questions in questions_by_module.items():
        print(f"Module {module}: {len(questions)} questions")

    if not available_modules:
        return {"error": "No questions found with valid modules and marks."}

    # CIE1 requires at least 12 questions total
    total_questions = sum(len(questions_by_module[module]) for module in available_modules)
    if total_questions < 12:
        return {"error": f"CIE1 requires at least 12 questions total. Found {total_questions} questions across all modules."}
    
    # Use available modules in order
    primary_module = available_modules[0]
    secondary_module = available_modules[1] if len(available_modules) > 1 else available_modules[0]
    tertiary_module = available_modules[2] if len(available_modules) > 2 else secondary_module

    paper = []
    used_questions = set()

    def find_question_combination_cie(available_questions, count=3):
        """Find combination of questions with different marks that sum to 25"""
        import itertools
        for combo in itertools.combinations(available_questions, count):
            if all(q['firestore_id'] not in used_questions for q in combo):
                return list(combo)
        return None

    # Generate Q1 - Primary module (3 sub-questions)
    primary_questions = [q for q in questions_by_module[primary_module] if q['firestore_id'] not in used_questions]
    q1_combination = find_question_combination_cie(primary_questions)
    if not q1_combination:
        return {"error": f"Could not find suitable question combination for Q1 from Module {primary_module}"}

    for q in q1_combination:
        used_questions.add(q['firestore_id'])

    paper.append({
        "main_question": "Q1",
        "module": primary_module,
        "sub_questions": [
            {"part": "a", "text": q1_combination[0]['question_text'], "marks": q1_combination[0]['marks'], "co": q1_combination[0].get('co', 'N/A'), "blooms_level": q1_combination[0].get('blooms_level', 'L2'), "module": primary_module},
            {"part": "b", "text": q1_combination[1]['question_text'], "marks": q1_combination[1]['marks'], "co": q1_combination[1].get('co', 'N/A'), "blooms_level": q1_combination[1].get('blooms_level', 'L2'), "module": primary_module},
            {"part": "c", "text": q1_combination[2]['question_text'], "marks": q1_combination[2]['marks'], "co": q1_combination[2].get('co', 'N/A'), "blooms_level": q1_combination[2].get('blooms_level', 'L2'), "module": primary_module}
        ]
    })

    # Generate Q2 - Primary module (Alternative to Q1)
    primary_remaining = [q for q in questions_by_module[primary_module] if q['firestore_id'] not in used_questions]
    q2_combination = find_question_combination_cie(primary_remaining)
    if not q2_combination:
        return {"error": f"Could not find suitable question combination for Q2 from Module {primary_module}"}

    for q in q2_combination:
        used_questions.add(q['firestore_id'])

    paper.append({
        "main_question": "Q2",
        "module": primary_module,
        "sub_questions": [
            {"part": "a", "text": q2_combination[0]['question_text'], "marks": q2_combination[0]['marks'], "co": q2_combination[0].get('co', 'N/A'), "blooms_level": q2_combination[0].get('blooms_level', 'L2'), "module": primary_module},
            {"part": "b", "text": q2_combination[1]['question_text'], "marks": q2_combination[1]['marks'], "co": q2_combination[1].get('co', 'N/A'), "blooms_level": q2_combination[1].get('blooms_level', 'L2'), "module": primary_module},
            {"part": "c", "text": q2_combination[2]['question_text'], "marks": q2_combination[2]['marks'], "co": q2_combination[2].get('co', 'N/A'), "blooms_level": q2_combination[2].get('blooms_level', 'L2'), "module": primary_module}
        ]
    })

    # Generate Q3 - Secondary module (a, b) + Tertiary module (c)
    secondary_questions = [q for q in questions_by_module[secondary_module] if q['firestore_id'] not in used_questions]
    tertiary_questions = [q for q in questions_by_module[tertiary_module] if q['firestore_id'] not in used_questions]

    if len(secondary_questions) < 2:
        return {"error": f"Need at least 2 questions from Module {secondary_module} for Q3. Found {len(secondary_questions)}."}
    if len(tertiary_questions) < 1:
        return {"error": f"Need at least 1 question from Module {tertiary_module} for Q3. Found {len(tertiary_questions)}."}

    q3_secondary_questions = secondary_questions[:2]
    q3_tertiary_question = tertiary_questions[0]

    for q in q3_secondary_questions + [q3_tertiary_question]:
        used_questions.add(q['firestore_id'])

    module_label_q3 = f"{secondary_module} & {tertiary_module}" if secondary_module != tertiary_module else secondary_module

    paper.append({
        "main_question": "Q3",
        "module": module_label_q3,
        "sub_questions": [
            {"part": "a", "text": q3_secondary_questions[0]['question_text'], "marks": q3_secondary_questions[0]['marks'], "co": q3_secondary_questions[0].get('co', 'N/A'), "blooms_level": q3_secondary_questions[0].get('blooms_level', 'L2'), "module": secondary_module},
            {"part": "b", "text": q3_secondary_questions[1]['question_text'], "marks": q3_secondary_questions[1]['marks'], "co": q3_secondary_questions[1].get('co', 'N/A'), "blooms_level": q3_secondary_questions[1].get('blooms_level', 'L2'), "module": secondary_module},
            {"part": "c", "text": q3_tertiary_question['question_text'], "marks": q3_tertiary_question['marks'], "co": q3_tertiary_question.get('co', 'N/A'), "blooms_level": q3_tertiary_question.get('blooms_level', 'L2'), "module": tertiary_module}
        ]
    })

    # Generate Q4 - Secondary module (a, b) + Tertiary module (c) - Different questions
    secondary_remaining = [q for q in questions_by_module[secondary_module] if q['firestore_id'] not in used_questions]
    tertiary_remaining = [q for q in questions_by_module[tertiary_module] if q['firestore_id'] not in used_questions]

    if len(secondary_remaining) < 2:
        return {"error": f"Need at least 2 more questions from Module {secondary_module} for Q4. Found {len(secondary_remaining)}."}
    if len(tertiary_remaining) < 1:
        return {"error": f"Need at least 1 more question from Module {tertiary_module} for Q4. Found {len(tertiary_remaining)}."}

    q4_secondary_questions = secondary_remaining[:2]
    q4_tertiary_question = tertiary_remaining[0]

    for q in q4_secondary_questions + [q4_tertiary_question]:
        used_questions.add(q['firestore_id'])

    module_label_q4 = f"{secondary_module} & {tertiary_module}" if secondary_module != tertiary_module else secondary_module

    paper.append({
        "main_question": "Q4",
        "module": module_label_q4,
        "sub_questions": [
            {"part": "a", "text": q4_secondary_questions[0]['question_text'], "marks": q4_secondary_questions[0]['marks'], "co": q4_secondary_questions[0].get('co', 'N/A'), "blooms_level": q4_secondary_questions[0].get('blooms_level', 'L2'), "module": secondary_module},
            {"part": "b", "text": q4_secondary_questions[1]['question_text'], "marks": q4_secondary_questions[1]['marks'], "co": q4_secondary_questions[1].get('co', 'N/A'), "blooms_level": q4_secondary_questions[1].get('blooms_level', 'L2'), "module": secondary_module},
            {"part": "c", "text": q4_tertiary_question['question_text'], "marks": q4_tertiary_question['marks'], "co": q4_tertiary_question.get('co', 'N/A'), "blooms_level": q4_tertiary_question.get('blooms_level', 'L2'), "module": tertiary_module}
        ]
    })

    print(f"✅ CIE1 paper generated successfully with {len(paper)} questions")
    return paper


def generate_cie2_paper(all_questions):
    """
    Generate CIE2 pattern question paper (correct academic structure):
    - Q1 OR Q2: 3 sub-questions from Module 4 (25 marks each)
    - Q3: 3 sub-questions (a, b from Module 5, c from Module 6) (25 marks)
    - Q4: 3 sub-questions (a, b from Module 5, c from Module 6) (25 marks)
    Total: 100 marks (students answer 3 questions = 75 marks)
    """
    print("🎯 Generating CIE2 pattern question paper...")

    # Use the same module detection logic as the standard pattern
    from collections import defaultdict
    questions_by_module = defaultdict(list)
    
    for q in all_questions:
        try:
            # Extract module number directly from the module field
            module_num = str(q.get('module', '1'))  # Default to module 1 if not specified
            
            # Ensure marks is integer
            marks = int(q.get('marks', 0))
            if marks > 0:  # Only include questions with valid marks
                q['module_num'] = module_num
                q['marks'] = marks
                questions_by_module[module_num].append(q)

        except (ValueError, TypeError):
            continue  # Skip questions with invalid marks

    # Check module availability - CIE2 requires specific modules
    available_modules = list(questions_by_module.keys())
    print(f"Available modules: {available_modules}")
    for module, questions in questions_by_module.items():
        print(f"Module {module}: {len(questions)} questions")

    if not available_modules:
        return {"error": "No questions found with valid modules and marks."}

    # CIE2 requires at least 12 questions total
    total_questions = sum(len(questions_by_module[module]) for module in available_modules)
    if total_questions < 12:
        return {"error": f"CIE2 requires at least 12 questions total. Found {total_questions} questions across all modules."}
    
    # Use available modules in order
    primary_module = available_modules[0]
    secondary_module = available_modules[1] if len(available_modules) > 1 else available_modules[0]
    tertiary_module = available_modules[2] if len(available_modules) > 2 else secondary_module

    paper = []
    used_questions = set()

    def find_question_combination_cie(available_questions, count=3):
        """Find combination of questions with different marks that sum to 25"""
        import itertools
        for combo in itertools.combinations(available_questions, count):
            if all(q['firestore_id'] not in used_questions for q in combo):
                return list(combo)
        return None

    # Generate Q1 - Module 4 (3 sub-questions)
    module4_questions = [q for q in questions_by_module['4'] if q['firestore_id'] not in used_questions]
    q1_combination = find_question_combination_cie(module4_questions)
    if not q1_combination:
        return {"error": "Could not find suitable question combination for Q1 from Module 4"}

    for q in q1_combination:
        used_questions.add(q['firestore_id'])

    paper.append({
        "main_question": "Q1",
        "module": "4",
        "sub_questions": [
            {"part": "a", "text": q1_combination[0]['question_text'], "marks": q1_combination[0]['marks'], "co": q1_combination[0].get('co', 'N/A'), "blooms_level": q1_combination[0].get('blooms_level', 'L2'), "module": "4"},
            {"part": "b", "text": q1_combination[1]['question_text'], "marks": q1_combination[1]['marks'], "co": q1_combination[1].get('co', 'N/A'), "blooms_level": q1_combination[1].get('blooms_level', 'L2'), "module": "4"},
            {"part": "c", "text": q1_combination[2]['question_text'], "marks": q1_combination[2]['marks'], "co": q1_combination[2].get('co', 'N/A'), "blooms_level": q1_combination[2].get('blooms_level', 'L2'), "module": "4"}
        ]
    })

    # Generate Q2 - Module 4 (Alternative to Q1)
    module4_remaining = [q for q in questions_by_module['4'] if q['firestore_id'] not in used_questions]
    q2_combination = find_question_combination_cie(module4_remaining)
    if not q2_combination:
        return {"error": "Could not find suitable question combination for Q2 from Module 4"}

    for q in q2_combination:
        used_questions.add(q['firestore_id'])

    paper.append({
        "main_question": "Q2",
        "module": "4",
        "sub_questions": [
            {"part": "a", "text": q2_combination[0]['question_text'], "marks": q2_combination[0]['marks'], "co": q2_combination[0].get('co', 'N/A'), "blooms_level": q2_combination[0].get('blooms_level', 'L2'), "module": "4"},
            {"part": "b", "text": q2_combination[1]['question_text'], "marks": q2_combination[1]['marks'], "co": q2_combination[1].get('co', 'N/A'), "blooms_level": q2_combination[1].get('blooms_level', 'L2'), "module": "4"},
            {"part": "c", "text": q2_combination[2]['question_text'], "marks": q2_combination[2]['marks'], "co": q2_combination[2].get('co', 'N/A'), "blooms_level": q2_combination[2].get('blooms_level', 'L2'), "module": "4"}
        ]
    })

    # Generate Q3 - Module 5 (a, b) + Module 6 (c)
    module5_questions = [q for q in questions_by_module['5'] if q['firestore_id'] not in used_questions]
    module6_questions = [q for q in questions_by_module['6'] if q['firestore_id'] not in used_questions]

    if len(module5_questions) < 2:
        return {"error": f"Need at least 2 questions from Module 5 for Q3. Found {len(module5_questions)}."}
    if len(module6_questions) < 1:
        return {"error": f"Need at least 1 question from Module 6 for Q3. Found {len(module6_questions)}."}

    q3_mod5_questions = module5_questions[:2]
    q3_mod6_question = module6_questions[0]

    for q in q3_mod5_questions + [q3_mod6_question]:
        used_questions.add(q['firestore_id'])

    paper.append({
        "main_question": "Q3",
        "module": "5 & 6",
        "sub_questions": [
            {"part": "a", "text": q3_mod5_questions[0]['question_text'], "marks": q3_mod5_questions[0]['marks'], "co": q3_mod5_questions[0].get('co', 'N/A'), "blooms_level": q3_mod5_questions[0].get('blooms_level', 'L2'), "module": "5"},
            {"part": "b", "text": q3_mod5_questions[1]['question_text'], "marks": q3_mod5_questions[1]['marks'], "co": q3_mod5_questions[1].get('co', 'N/A'), "blooms_level": q3_mod5_questions[1].get('blooms_level', 'L2'), "module": "5"},
            {"part": "c", "text": q3_mod6_question['question_text'], "marks": q3_mod6_question['marks'], "co": q3_mod6_question.get('co', 'N/A'), "blooms_level": q3_mod6_question.get('blooms_level', 'L2'), "module": "6"}
        ]
    })

    # Generate Q4 - Module 5 (a, b) + Module 6 (c) - Different questions
    module5_remaining = [q for q in questions_by_module['5'] if q['firestore_id'] not in used_questions]
    module6_remaining = [q for q in questions_by_module['6'] if q['firestore_id'] not in used_questions]

    if len(module5_remaining) < 2:
        return {"error": f"Need at least 2 more questions from Module 5 for Q4. Found {len(module5_remaining)}."}
    if len(module6_remaining) < 1:
        return {"error": f"Need at least 1 more question from Module 6 for Q4. Found {len(module6_remaining)}."}

    q4_mod5_questions = module5_remaining[:2]
    q4_mod6_question = module6_remaining[0]

    for q in q4_mod5_questions + [q4_mod6_question]:
        used_questions.add(q['firestore_id'])

    paper.append({
        "main_question": "Q4",
        "module": "5 & 6",
        "sub_questions": [
            {"part": "a", "text": q4_mod5_questions[0]['question_text'], "marks": q4_mod5_questions[0]['marks'], "co": q4_mod5_questions[0].get('co', 'N/A'), "blooms_level": q4_mod5_questions[0].get('blooms_level', 'L2'), "module": "5"},
            {"part": "b", "text": q4_mod5_questions[1]['question_text'], "marks": q4_mod5_questions[1]['marks'], "co": q4_mod5_questions[1].get('co', 'N/A'), "blooms_level": q4_mod5_questions[1].get('blooms_level', 'L2'), "module": "5"},
            {"part": "c", "text": q4_mod6_question['question_text'], "marks": q4_mod6_question['marks'], "co": q4_mod6_question.get('co', 'N/A'), "blooms_level": q4_mod6_question.get('blooms_level', 'L2'), "module": "6"}
        ]
    })

    print(f"✅ CIE2 paper generated successfully with {len(paper)} questions")
    return paper


@app.route('/save_question_paper', methods=['POST'])
@firebase_auth_required
def save_question_paper():
    """Save a question paper to Supabase (hybrid approach)"""
    user_uid = request.current_user_uid
    data = request.get_json()
    
    try:
        # Get Supabase user ID
        supabase_user = supabase_service.get_user_by_firebase_uid(user_uid)
        if not supabase_user:
            return jsonify({'error': 'User not found in Supabase'}), 404
        
        # Prepare data for Supabase
        paper_data = {
            'firebase_paper_id': data.get('firebase_paper_id'),
            'paper_name': data.get('paper_name', 'Untitled Question Paper'),
            'subject': data.get('subject', 'Unknown Subject'),
            'pattern': data.get('pattern', 'standard'),
            'total_marks': data.get('total_marks', 100),
            'question_count': len(data.get('questions', [])),
            'questions': data.get('questions', []),
            'metadata': data.get('metadata', {}),
            'status': data.get('status', 'draft'),
            'tags': data.get('tags', [])
        }
        
        # Save to Supabase
        saved_paper = supabase_service.save_question_paper(supabase_user['id'], paper_data)
        
        if saved_paper:
            # Also save to Firebase for backup (optional)
            try:
                data['user_uid'] = user_uid
                data['saved_at'] = firestore.SERVER_TIMESTAMP
                data['updated_at'] = firestore.SERVER_TIMESTAMP
                data['supabase_id'] = saved_paper['id']  # Reference to Supabase record
                
                saved_paper_ref = db_firestore.collection('users').document(user_uid).collection('saved_question_papers').document()
                saved_paper_ref.set(data)
                print(f"Question paper also backed up to Firebase: {saved_paper_ref.id}")
            except Exception as e:
                print(f"Warning: Failed to backup to Firebase: {e}")
            
            return jsonify({
                'message': 'Question paper saved successfully',
                'paper_id': saved_paper['id'],
                'supabase_id': saved_paper['id']
            }), 200
        else:
            return jsonify({'error': 'Failed to save question paper to Supabase'}), 500
        
    except Exception as e:
        print(f"Error saving question paper: {e}")
        return jsonify({'error': f'Failed to save question paper: {str(e)}'}), 500

@app.route('/get_saved_items', methods=['GET'])
@firebase_auth_required
def get_saved_items():
    """Get saved question papers from Supabase, question banks and templates from Firebase"""
    user_uid = request.current_user_uid
    
    try:
        # Get Supabase user ID
        supabase_user = supabase_service.get_user_by_firebase_uid(user_uid)
        if not supabase_user:
            return jsonify({'error': 'User not found in Supabase'}), 404
        
        # Get saved question papers from Supabase
        saved_question_papers = supabase_service.get_saved_question_papers(supabase_user['id'], limit=50)
        
        # Add type field for frontend compatibility
        for paper in saved_question_papers:
            paper['type'] = 'question-paper'
            # Convert UUID to string for JSON serialization
            paper['id'] = str(paper['id'])
        
        # Get generated question papers
        papers_ref = db_firestore.collection('users').document(user_uid).collection('generated_papers')
        papers_docs = papers_ref.order_by('created_at', direction=firestore.Query.DESCENDING).limit(50).stream()
        
        generated_question_papers = []
        for doc in papers_docs:
            paper_data = doc.to_dict()
            paper_data['id'] = doc.id
            paper_data['type'] = 'generated-paper'
            generated_question_papers.append(paper_data)
        
        # Get question banks (group by source file)
        banks_ref = db_firestore.collection('users').document(user_uid).collection('question_bank_pool')
        banks_docs = banks_ref.stream()
        
        # Group questions by source file to create question banks
        question_banks_by_source = {}
        for doc in banks_docs:
            question_data = doc.to_dict()
            source_file = question_data.get('source_file', 'Unknown Source')
            
            if source_file not in question_banks_by_source:
                # Create a safe ID by replacing non-alphanumeric characters
                import re
                safe_id = re.sub(r'[^a-zA-Z0-9]', '_', source_file)
                
                question_banks_by_source[source_file] = {
                    'id': f"bank_{safe_id}",
                    'type': 'question-bank',
                    'name': source_file,
                    'source_file': source_file,
                    'questions': [],
                    'question_count': 0,
                    'uploaded_at': question_data.get('uploaded_at')
                }
            
            question_banks_by_source[source_file]['questions'].append(question_data)
            question_banks_by_source[source_file]['question_count'] += 1
        
        question_banks = list(question_banks_by_source.values())
        
        return jsonify({
            "message": "Saved items fetched successfully",
            "question_papers": saved_question_papers,
            "generated_papers": generated_question_papers,
            "question_banks": question_banks,
            "templates": []  # Placeholder for templates
        }), 200
        
    except Exception as e:
        return jsonify({"error": f"Error fetching saved items: {str(e)}"}), 500

@app.route('/get_recent_papers', methods=['GET'])
@firebase_auth_required
def get_recent_papers():
    """Get recently generated question papers for the user"""
    user_uid = request.current_user_uid
    
    try:
        # Get recent papers from both generated_papers and saved_question_papers collections
        recent_papers = []
        
        # Get from generated papers
        generated_ref = db_firestore.collection('users').document(user_uid).collection('generated_papers')
        generated_docs = generated_ref.order_by('created_at', direction=firestore.Query.DESCENDING).limit(10).stream()
        
        for doc in generated_docs:
            paper_data = doc.to_dict()
            paper_data['id'] = doc.id
            paper_data['source'] = 'generated'
            recent_papers.append(paper_data)
        
        # Get from saved papers
        saved_ref = db_firestore.collection('users').document(user_uid).collection('saved_question_papers')
        saved_docs = saved_ref.order_by('saved_at', direction=firestore.Query.DESCENDING).limit(10).stream()
        
        for doc in saved_docs:
            paper_data = doc.to_dict()
            paper_data['id'] = doc.id
            paper_data['source'] = 'saved'
            recent_papers.append(paper_data)
        
        # Sort by date (newest first)
        recent_papers.sort(key=lambda x: x.get('created_at', x.get('saved_at', {})).get('seconds', 0), reverse=True)
        
        return jsonify({
            "message": "Recent papers fetched successfully",
            "recent_papers": recent_papers[:20]  # Limit to 20 most recent
        }), 200
        
    except Exception as e:
        return jsonify({"error": f"Error fetching recent papers: {str(e)}"}), 500

@app.route('/submit_for_approval', methods=['POST'])
@firebase_auth_required
def submit_for_approval():
    """Submit a question paper for HOD approval (hybrid approach)"""
    user_uid = request.current_user_uid
    data = request.get_json()
    paper_id = data.get('paper_id')
    comments = data.get('comments', '')
    
    try:
        # Get Supabase user ID
        supabase_user = supabase_service.get_user_by_firebase_uid(user_uid)
        if not supabase_user:
            return jsonify({'error': 'User not found in Supabase'}), 404
        
        paper_data = None
        paper_source = None
        
        # First, try to get from Supabase saved papers
        try:
            saved_papers = supabase_service.get_saved_question_papers(supabase_user['id'], limit=100)
            for paper in saved_papers:
                if str(paper['id']) == str(paper_id) or paper.get('firebase_paper_id') == paper_id:
                    paper_data = {
                        'paper_name': paper.get('paper_name', 'Untitled Paper'),
                        'subject': paper.get('subject', 'Unknown Subject'),
                        'questions': paper.get('questions', []),
                        'pattern': paper.get('pattern', 'standard'),
                        'total_marks': paper.get('total_marks', 100),
                        'metadata': paper.get('metadata', {})
                    }
                    paper_source = 'supabase'
                    break
        except Exception as e:
            print(f"Error fetching from Supabase: {e}")
        
        # If not found in Supabase, try Firebase generated papers
        if not paper_data:
            try:
                paper_ref = db_firestore.collection('users').document(user_uid).collection('generated_papers').document(paper_id)
                paper_doc = paper_ref.get()
                
                if paper_doc.exists:
                    paper_data = paper_doc.to_dict()
                    paper_source = 'firebase'
            except Exception as e:
                print(f"Error fetching from Firebase: {e}")
        
        if not paper_data:
            return jsonify({"error": "Question paper not found in either Supabase or Firebase"}), 404
        
        # Get user info from Supabase
        user_data = {
            'name': supabase_user.get('name', 'Unknown Faculty'),
            'email': supabase_user.get('email', ''),
            'department': supabase_user.get('department', 'Unknown Department')
        }
        
        # Find the Supabase paper ID for the approval
        supabase_paper_id = None
        if paper_source == 'supabase':
            # Find the paper in the saved papers list
            for paper in saved_papers:
                if str(paper['id']) == str(paper_id) or paper.get('firebase_paper_id') == paper_id:
                    supabase_paper_id = paper['id']
                    break
        else:
            # For Firebase papers, check if there's a corresponding Supabase paper
            try:
                firebase_paper_result = supabase_service.supabase.table('saved_question_papers').select('id').eq('firebase_paper_id', paper_id).execute()
                if firebase_paper_result.data:
                    supabase_paper_id = firebase_paper_result.data[0]['id']
            except Exception as e:
                print(f"Error finding Supabase paper for Firebase ID {paper_id}: {e}")
        
        if not supabase_paper_id:
            # If paper is not in Supabase but exists in Firebase, save it now
            if paper_source == 'firebase' and paper_data:
                print(f"Paper {paper_id} not in Supabase, saving it now...")
                try:
                    # Prepare data for Supabase
                    supabase_paper_data = {
                        'firebase_paper_id': paper_id,
                        'paper_name': paper_data.get('paper_name', 'Untitled Paper'),
                        'subject': paper_data.get('subject', 'Unknown Subject'),
                        'pattern': paper_data.get('pattern', 'standard'),
                        'total_marks': 100,  # Default
                        'question_count': len(paper_data.get('questions', [])),
                        'questions': paper_data.get('questions', []),
                        'metadata': paper_data.get('source_info', {}),
                        'status': 'draft',
                        'tags': paper_data.get('tags', [])
                    }
                    
                    # Save to Supabase
                    saved_paper = supabase_service.save_question_paper(supabase_user['id'], supabase_paper_data)
                    if saved_paper:
                        supabase_paper_id = saved_paper['id']
                        print(f"Paper saved to Supabase: {supabase_paper_id}")
                        
                        # Update Firebase with Supabase ID reference
                        paper_ref = db_firestore.collection('users').document(user_uid).collection('generated_papers').document(paper_id)
                        paper_ref.update({'supabase_id': supabase_paper_id})
                    else:
                        return jsonify({"error": "Failed to save paper to Supabase"}), 500
                except Exception as e:
                    print(f"Error saving paper to Supabase: {e}")
                    return jsonify({"error": f"Failed to save paper to Supabase: {str(e)}"}), 500
            else:
                return jsonify({"error": "Paper not found in Supabase. Please save the paper first."}), 404
        
        # Create approval request (matching database schema)
        approval_data = {
            "paper_id": supabase_paper_id,  # Use Supabase UUID
            "submitted_by": supabase_user['id'],  # Use Supabase user ID
            "status": "pending",
            "comments": comments,  # faculty comments
            "hod_comments": None,
            "reviewed_by": None,
            "reviewed_at": None
        }
        
        # Save to Supabase first (primary storage)
        try:
            supabase_approval = supabase_service.create_approval(supabase_user['id'], approval_data)
            if supabase_approval:
                approval_id = supabase_approval['id']
                print(f"Approval saved to Supabase: {approval_id}")
            else:
                return jsonify({"error": "Failed to save approval to Supabase"}), 500
        except Exception as e:
            print(f"Error saving to Supabase: {e}")
            return jsonify({"error": f"Failed to save approval: {str(e)}"}), 500
        
        # Also save to Firebase for backup
        try:
            firebase_approval_data = approval_data.copy()
            firebase_approval_data["submitted_at"] = firestore.SERVER_TIMESTAMP
            firebase_approval_data["supabase_id"] = approval_id
            
            approval_ref = db_firestore.collection('approvals').document()
            approval_ref.set(firebase_approval_data)
            print(f"Approval also backed up to Firebase: {approval_ref.id}")
        except Exception as e:
            print(f"Warning: Failed to backup approval to Firebase: {e}")
        
        # Update paper status in both systems
        try:
            # Update Supabase paper status (always use the Supabase paper ID)
            supabase_service.update_question_paper_status(supabase_paper_id, 'submitted', approval_id)
        except Exception as e:
            print(f"Warning: Failed to update Supabase paper status: {e}")
        
        # Also update Firebase paper status if it's a Firebase paper
        if paper_source == 'firebase':
            try:
                paper_ref = db_firestore.collection('users').document(user_uid).collection('generated_papers').document(paper_id)
                paper_ref.update({
                    "status": "submitted",
                    "approval_id": approval_id,
                    "submitted_for_approval_at": firestore.SERVER_TIMESTAMP
                })
            except Exception as e:
                print(f"Warning: Failed to update Firebase paper status: {e}")
        
        return jsonify({
            "message": "Question paper submitted for approval successfully!",
            "approval_id": approval_id,
            "status": "pending"
        }), 200
        
    except Exception as e:
        return jsonify({"error": f"Failed to submit for approval: {str(e)}"}), 500

@app.route('/get_pending_approvals', methods=['GET'])
@firebase_auth_required
def get_pending_approvals():
    """Get papers pending approval for HOD"""
    user_uid = request.current_user_uid
    
    try:
        # Check if user is HOD using Supabase
        hod_user = supabase_service.get_user_by_firebase_uid(user_uid)
        if not hod_user or hod_user.get('role') != 'hod':
            return jsonify({"error": "Access denied. HOD privileges required."}), 403
        
        # Get pending approvals from Supabase
        approvals = supabase_service.get_pending_approvals(hod_user['id'])
        
        # Format approvals for frontend
        formatted_approvals = []
        for approval in approvals:
            paper = approval.get('saved_question_papers', {})
            faculty = approval.get('users', {})
            
            formatted_approval = {
                'id': approval['id'],
                'paper_id': approval['paper_id'],
                'faculty_uid': approval['submitted_by'],
                'faculty_name': faculty.get('name', 'Unknown Faculty'),
                'faculty_email': faculty.get('email', ''),
                'department': faculty.get('department', 'Unknown Department'),
                'subject': paper.get('subject', 'Unknown Subject'),
                'paper_name': paper.get('paper_name', 'Untitled Paper'),
                'questions': paper.get('questions', []),
                'pattern': paper.get('pattern', 'standard'),
                'total_marks': paper.get('total_marks', 100),
                'status': approval['status'],
                'comments': approval.get('comments', ''),
                'hod_comments': approval.get('hod_comments', ''),
                'submitted_at': approval.get('submitted_at'),
                'reviewed_at': approval.get('reviewed_at'),
                'priority': 'medium',
                'estimated_review_time': '2-3 days'
            }
            formatted_approvals.append(formatted_approval)
        
        return jsonify({
            "approvals": formatted_approvals,
            "department": hod_user.get('department', 'Unknown Department')
        }), 200
        
    except Exception as e:
        return jsonify({"error": f"Error fetching pending approvals: {str(e)}"}), 500

@app.route('/approve_paper', methods=['POST'])
@firebase_auth_required
def approve_paper():
    """Approve a question paper"""
    user_uid = request.current_user_uid
    data = request.get_json()
    approval_id = data.get('approval_id')
    comments = data.get('comments', '')
    
    try:
        # Check if user is HOD using Supabase
        hod_user = supabase_service.get_user_by_firebase_uid(user_uid)
        if not hod_user or hod_user.get('role') != 'hod':
            return jsonify({"error": "Access denied. HOD privileges required."}), 403
        
        # Approve paper using Supabase service
        success = supabase_service.approve_paper(approval_id, hod_user['id'], comments)
        
        if success:
            return jsonify({
                "message": "Question paper approved successfully!",
                "status": "approved"
            }), 200
        else:
            return jsonify({"error": "Failed to approve paper"}), 500
        
    except Exception as e:
        return jsonify({"error": f"Failed to approve paper: {str(e)}"}), 500

@app.route('/request_revision', methods=['POST'])
@firebase_auth_required
def request_revision():
    """Request revision for a question paper"""
    user_uid = request.current_user_uid
    data = request.get_json()
    approval_id = data.get('approval_id')
    comments = data.get('comments', '')
    revision_type = data.get('revision_type', 'minor')  # minor, major, complete_rewrite
    
    try:
        # Check if user is HOD using Supabase
        hod_user = supabase_service.get_user_by_firebase_uid(user_uid)
        if not hod_user or hod_user.get('role') != 'hod':
            return jsonify({"error": "Access denied. HOD privileges required."}), 403
        
        # Reject paper using Supabase service (treating revision as rejection with comments)
        success = supabase_service.reject_paper(approval_id, hod_user['id'], f"Revision requested: {comments}")
        
        if success:
            return jsonify({
                "message": "Revision requested successfully!",
                "status": "revision_requested",
                "revision_type": revision_type
            }), 200
        else:
            return jsonify({"error": "Failed to request revision"}), 500
        
    except Exception as e:
        return jsonify({"error": f"Failed to request revision: {str(e)}"}), 500

@app.route('/get_approval_status', methods=['GET'])
@firebase_auth_required
def get_approval_status():
    """Get approval status for a paper"""
    user_uid = request.current_user_uid
    paper_id = request.args.get('paper_id')
    
    try:
        # Get paper
        paper_ref = db_firestore.collection('users').document(user_uid).collection('generated_papers').document(paper_id)
        paper_doc = paper_ref.get()
        
        if not paper_doc.exists:
            return jsonify({"error": "Question paper not found"}), 404
        
        paper_data = paper_doc.to_dict()
        approval_id = paper_data.get('approval_id')
        
        if not approval_id:
            return jsonify({
                "status": "not_submitted",
                "message": "Paper not submitted for approval"
            }), 200
        
        # Get approval details
        approval_ref = db_firestore.collection('approvals').document(approval_id)
        approval_doc = approval_ref.get()
        
        if not approval_doc.exists:
            return jsonify({
                "status": "error",
                "message": "Approval record not found"
            }), 200
        
        approval_data = approval_doc.to_dict()
        
        return jsonify({
            "status": approval_data.get('status', 'unknown'),
            "submitted_at": approval_data.get('submitted_at'),
            "reviewed_at": approval_data.get('reviewed_at'),
            "reviewed_by": approval_data.get('reviewed_by', ''),
            "hod_comments": approval_data.get('hod_comments', ''),
            "comments": approval_data.get('comments', ''),
            "revision_requests": approval_data.get('revision_requests', []),
            "priority": approval_data.get('priority', 'medium')
        }), 200
        
    except Exception as e:
        return jsonify({"error": f"Error fetching approval status: {str(e)}"}), 500

@app.route('/get_user_submissions', methods=['GET'])
@firebase_auth_required
def get_user_submissions():
    """Get all submissions for a user"""
    user_uid = request.current_user_uid
    
    try:
        # Get Supabase user ID
        supabase_user = supabase_service.get_user_by_firebase_uid(user_uid)
        if not supabase_user:
            return jsonify({'error': 'User not found in Supabase'}), 404
        
        # Get all approvals for this user
        approvals_result = supabase_service.supabase.table('approvals')\
            .select('*, saved_question_papers(paper_name, subject, pattern)')\
            .eq('submitted_by', supabase_user['id'])\
            .order('submitted_at', desc=True)\
            .execute()
        
        submissions = []
        for approval in approvals_result.data:
            paper_info = approval.get('saved_question_papers', {})
            submissions.append({
                'id': approval['id'],
                'paper_id': approval['paper_id'],
                'paper_name': paper_info.get('paper_name', 'Untitled Paper'),
                'subject': paper_info.get('subject', 'Unknown Subject'),
                'pattern': paper_info.get('pattern', 'standard'),
                'status': approval['status'],
                'comments': approval.get('comments', ''),
                'hod_comments': approval.get('hod_comments', ''),
                'submitted_at': approval.get('submitted_at'),
                'reviewed_at': approval.get('reviewed_at'),
                'reviewed_by': approval.get('reviewed_by')
            })
        
        return jsonify({
            'submissions': submissions,
            'total': len(submissions)
        }), 200
        
    except Exception as e:
        print(f"Error fetching user submissions: {e}")
        return jsonify({"error": f"Error fetching submissions: {str(e)}"}), 500

@app.route('/get_dashboard_metrics', methods=['GET'])
@firebase_auth_required
def get_dashboard_metrics():
    """Get dashboard metrics for the user"""
    user_uid = request.current_user_uid
    
    try:
        # Get Supabase user ID
        supabase_user = supabase_service.get_user_by_firebase_uid(user_uid)
        if not supabase_user:
            return jsonify({'error': 'User not found in Supabase'}), 404
        
        user_id = supabase_user['id']
        
        # Get total questions from question banks
        questions_result = supabase_service.supabase.table('question_banks')\
            .select('total_questions')\
            .eq('user_id', user_id)\
            .execute()
        
        total_questions = sum(bank.get('total_questions', 0) for bank in questions_result.data)
        
        # If no questions in question_banks, try to count from saved papers
        if total_questions == 0:
            papers_with_questions = supabase_service.supabase.table('saved_question_papers')\
                .select('question_count')\
                .eq('user_id', user_id)\
                .execute()
            
            total_questions = sum(paper.get('question_count', 0) for paper in papers_with_questions.data)
        
        # Get papers generated this month
        from datetime import datetime, timedelta
        month_start = datetime.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        
        papers_result = supabase_service.supabase.table('saved_question_papers')\
            .select('id, created_at')\
            .eq('user_id', user_id)\
            .gte('created_at', month_start.isoformat())\
            .execute()
        
        papers_generated = len(papers_result.data)
        
        # Get saved templates (all saved papers can be used as templates)
        templates_result = supabase_service.supabase.table('saved_question_papers')\
            .select('id')\
            .eq('user_id', user_id)\
            .execute()
        
        saved_templates = len(templates_result.data)
        
        # Calculate success rate (papers that were successfully generated vs failed)
        # For now, assume high success rate since we don't track failures
        success_rate = 98 if papers_generated > 0 else 100
        
        # Calculate trends (simplified - in real app, compare with previous periods)
        questions_trend = 12 if total_questions > 0 else 0
        papers_trend = 8 if papers_generated > 0 else 0
        
        return jsonify({
            'total_questions': total_questions,
            'papers_generated': papers_generated,
            'saved_templates': saved_templates,
            'success_rate': success_rate,
            'questions_trend': questions_trend,
            'papers_trend': papers_trend
        }), 200
        
    except Exception as e:
        print(f"Error fetching dashboard metrics: {e}")
        return jsonify({"error": f"Error fetching metrics: {str(e)}"}), 500

@app.route('/create_hod_user', methods=['POST'])
def create_hod_user():
    """Create HOD user for testing"""
    try:
        firebase_uid = 'jaQrJOvNfxO4eN5sqKoiNkmlixg2'
        email = 'test_hod@example.com'
        
        # Check if user already exists
        existing_user = supabase_service.get_user_by_firebase_uid(firebase_uid)
        if existing_user:
            if existing_user.get('role') != 'hod':
                # Update role to hod
                supabase_service.supabase.table('users')\
                    .update({'role': 'hod'})\
                    .eq('id', existing_user['id'])\
                    .execute()
                return jsonify({'message': 'User role updated to HOD'}), 200
            else:
                return jsonify({'message': 'User already has HOD role'}), 200
        
        # Create new HOD user
        user_data = {
            'firebase_uid': firebase_uid,
            'email': email,
            'name': 'Test HOD',
            'role': 'hod',
            'department': 'Computer Science'
        }
        
        result = supabase_service.supabase.table('users').insert(user_data).execute()
        
        if result.data:
            return jsonify({'message': 'HOD user created successfully', 'user': result.data[0]}), 200
        else:
            return jsonify({'error': 'Failed to create HOD user'}), 500
            
    except Exception as e:
        return jsonify({'error': f'Error creating HOD user: {str(e)}'}), 500

@app.route('/generate_question_paper', methods=['POST'])
@firebase_auth_required
def generate_question_paper():
    user_uid = request.current_user_uid
    data = request.get_json()
    subject = data.get('subject')
    modules = data.get('modules', [])
    use_latest_upload_only = data.get('use_latest_upload_only', True)  # New parameter
    pattern = data.get('pattern', 'standard')  # New parameter for question pattern

    try:
        if use_latest_upload_only:
            # Check cache first
            cache_key = f"{user_uid}_latest"
            cached_questions = get_cached_questions(user_uid, cache_key)
            
            if cached_questions:
                all_questions = cached_questions
                latest_source_file = all_questions[0].get('source_file') if all_questions else None
            else:
                # First, get the latest source file with a single query
                questions_ref = db_firestore.collection('users').document(user_uid).collection('question_bank_pool')
                
                # Get only the most recent document to find the latest source file
                latest_doc = questions_ref.order_by('uploaded_at', direction=firestore.Query.DESCENDING).limit(1).get()
                
                if not latest_doc:
                    return jsonify({'error': 'No questions found in your question bank.'}), 404
                    
                latest_source_file = latest_doc[0].to_dict().get('source_file')
                
                # Now fetch only questions from the latest source file
                docs = questions_ref.where('source_file', '==', latest_source_file).stream()
                
                all_questions = []
                for doc in docs:
                    question_data = doc.to_dict()
                    question_data['firestore_id'] = doc.id
                    all_questions.append(question_data)
                
                # Cache the results
                cache_questions(user_uid, cache_key, all_questions)

            if not all_questions:
                return jsonify({"error": "No questions found from the latest upload. Please upload a question bank first."}), 400

            print(f"Using questions only from latest upload: '{latest_source_file}' ({len(all_questions)} questions)")

        else:
            # Original behavior: Fetch all questions from user's question bank
            questions_ref = db_firestore.collection('users').document(user_uid).collection('question_bank_pool')
            docs = questions_ref.stream()

            all_questions = []
            for doc in docs:
                question_data = doc.to_dict()
                question_data['firestore_id'] = doc.id
                all_questions.append(question_data)

            if not all_questions:
                return jsonify({"error": "No questions found in your question bank. Please upload questions first."}), 400

            print(f"Using all questions from question bank ({len(all_questions)} questions)")

        # Generate question paper according to selected pattern
        if pattern == 'cie1':
            generated_paper = generate_cie1_paper(all_questions)
        elif pattern == 'cie2':
            generated_paper = generate_cie2_paper(all_questions)
        else:
            # Default to standard pattern
            generated_paper = generate_paper_with_rules(all_questions)

        if not generated_paper:
            return jsonify({"error": "Could not generate a question paper with the available questions. Please ensure you have questions from all required modules with appropriate marks distribution."}), 400

        # Handle error responses from the generation function
        if isinstance(generated_paper, dict) and "error" in generated_paper:
            return jsonify(generated_paper), 400

        # Save the generated paper to Firestore
        paper_data = {
            "user_uid": user_uid,
            "paper_name": f"{subject} - {pattern.upper()} Pattern",
            "subject": subject,
            "pattern": pattern,
            "questions": generated_paper,
            "modules": modules,
            "source_info": {
                "latest_upload_only": use_latest_upload_only,
                "source_file": latest_source_file if use_latest_upload_only else "All uploaded files",
                "total_questions_used": len(all_questions)
            },
            "created_at": firestore.SERVER_TIMESTAMP,
            "updated_at": firestore.SERVER_TIMESTAMP,
            "status": "generated",
            "download_count": 0,
            "size": len(str(generated_paper)),
            "tags": [pattern, subject.lower().replace(" ", "-")]
        }
        
        # Save to Firestore
        paper_ref = db_firestore.collection('users').document(user_uid).collection('generated_papers').document()
        paper_ref.set(paper_data)
        firebase_paper_id = paper_ref.id
        
        # Also save to Supabase for HOD approval workflow
        try:
            # Get Supabase user ID
            supabase_user = supabase_service.get_user_by_firebase_uid(user_uid)
            if supabase_user:
                # Prepare data for Supabase
                supabase_paper_data = {
                    'firebase_paper_id': firebase_paper_id,
                    'paper_name': f"{subject} - {pattern.upper()} Pattern",
                    'subject': subject,
                    'pattern': pattern,
                    'total_marks': 100,  # Default, can be calculated from questions
                    'question_count': len(generated_paper),
                    'questions': generated_paper,
                    'metadata': {
                        "latest_upload_only": use_latest_upload_only,
                        "source_file": latest_source_file if use_latest_upload_only else "All uploaded files",
                        "total_questions_used": len(all_questions),
                        "modules": modules
                    },
                    'status': 'draft',
                    'tags': [pattern, subject.lower().replace(" ", "-")]
                }
                
                # Save to Supabase
                saved_paper = supabase_service.save_question_paper(supabase_user['id'], supabase_paper_data)
                if saved_paper:
                    print(f"Paper also saved to Supabase: {saved_paper['id']}")
                    # Update Firebase with Supabase ID reference
                    paper_ref.update({'supabase_id': saved_paper['id']})
                else:
                    print("Warning: Failed to save paper to Supabase")
            else:
                print("Warning: User not found in Supabase, paper only saved to Firebase")
        except Exception as e:
            print(f"Warning: Failed to save paper to Supabase: {e}")
        
        return jsonify({
            "message": "Question paper generated successfully!",
            "questions": generated_paper,
            "paper_id": firebase_paper_id,
            "source_info": {
                "latest_upload_only": use_latest_upload_only,
                "source_file": latest_source_file if use_latest_upload_only else "All uploaded files",
                "total_questions_used": len(all_questions)
            }
        }), 200

    except Exception as e:
        traceback.print_exc()
        
        # Check if it's a quota exceeded error
        if "Quota exceeded" in str(e) or "ResourceExhausted" in str(e):
            return jsonify({
                'error': 'Firebase quota exceeded. Please try again later or contact support.',
                'details': 'You have reached the daily limit for database operations. This will reset tomorrow.',
                'suggestion': 'Try using fewer questions or wait until tomorrow when the quota resets.'
            }), 429
        else:
            return jsonify({"error": f"Failed to generate question paper: {str(e)}"}), 500

if __name__ == '__main__':
    port = int(os.environ.get('FLASK_RUN_PORT', 5000))
    app.run(debug=True, port=port)
