# 🎓 SmartQPGen - Intelligent Question Paper Generation System

[![Python](https://img.shields.io/badge/Python-3.8+-blue.svg)](https://python.org)
[![Flask](https://img.shields.io/badge/Flask-2.0+-green.svg)](https://flask.palletsprojects.com/)
[![Firebase](https://img.shields.io/badge/Firebase-Admin-orange.svg)](https://firebase.google.com/)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

**SmartQPGen** is an intelligent question paper generation system designed for educational institutions. It automates the creation of question papers from uploaded question banks, with role-based access control for Faculty and Head of Department (HOD) users.

## 🌟 Features

### 📚 **Core Functionality**
- **Intelligent Question Paper Generation**: Automatically generates balanced question papers from uploaded question banks
- **Multi-format Support**: Upload question banks in DOCX or PDF format
- **Flexible Output**: Download generated papers in DOCX or PDF format
- **Module-based Organization**: Supports multi-module question distribution
- **Bloom's Taxonomy Integration**: Questions categorized by cognitive levels
- **Course Outcome Mapping**: Maps questions to specific course outcomes

### 👥 **Role-Based Access Control**

#### 🧑‍🏫 **Faculty Features**
- Upload and manage question banks
- Generate question papers with customizable parameters
- View and edit personal question collections
- Download generated papers in multiple formats
- Track paper generation history

#### 👑 **HOD (Head of Department) Features**
- **Review & Approval System**: Review and approve faculty-generated papers
- **Faculty Management**: Oversee department faculty and their submissions
- **Analytics Dashboard**: View department-wide statistics and performance metrics
- **Quality Control**: Ensure question paper standards and consistency
- **Bulk Operations**: Manage multiple papers and faculty members efficiently

### 🎨 **Professional Interface**
- **Modern UI/UX**: Clean, responsive design with institutional branding
- **College Branding**: Customizable with college logo and background
- **Mobile Responsive**: Works seamlessly on all devices
- **Dark/Light Themes**: Professional color schemes
- **Intuitive Navigation**: Easy-to-use interface for all user types

## 🏗️ System Architecture

```
SmartQPGen/
├── backend/
│   ├── app.py                 # Main Flask application
│   ├── generator.py           # Question paper generation logic
│   ├── templates/             # HTML templates
│   │   ├── index.html         # Landing page
│   │   ├── login.html         # Faculty login
│   │   ├── register.html      # Faculty registration
│   │   ├── dashboard.html     # Faculty dashboard
│   │   ├── hod_login.html     # HOD login
│   │   ├── hod_register.html  # HOD registration
│   │   └── hod_dashboard.html # HOD dashboard
│   ├── static/                # Static assets
│   │   └── assets/            # Images, CSS, JS
│   └── uploads/               # Temporary file storage
├── requirements.txt           # Python dependencies
├── .env                      # Environment variables
└── README.md                 # This file
```

## 🚀 Quick Start

### Prerequisites
- Python 3.8 or higher
- Microsoft Word (for PDF conversion on Windows)
- Firebase project with Authentication and Firestore enabled
- Google Cloud credentials (for Firebase Admin SDK)

### 1. Clone the Repository
```bash
git clone https://github.com/your-username/SmartQPGen.git
cd SmartQPGen
```

### 2. Install Dependencies
```bash
pip install -r requirements.txt
```

### 3. Firebase Setup

#### Create Firebase Project
1. Go to [Firebase Console](https://console.firebase.google.com/)
2. Create a new project
3. Enable **Authentication** and **Firestore Database**

#### Configure Authentication
1. In Firebase Console → Authentication → Sign-in method
2. Enable **Email/Password** authentication
3. Add authorized domains if deploying

#### Setup Firestore Database
1. Create Firestore database in production mode
2. Set up the following collections:
   - `users` - Faculty user profiles
   - `hod_users` - HOD user profiles  
   - `question_banks` - Uploaded question banks
   - `generated_papers` - Generated question papers

#### Get Firebase Credentials
1. Go to Project Settings → Service Accounts
2. Generate new private key
3. Download the JSON file
4. Set up Google Application Default Credentials:
   ```bash
   # Windows
   set GOOGLE_APPLICATION_CREDENTIALS=path\to\your\firebase-key.json
   
   # Linux/Mac
   export GOOGLE_APPLICATION_CREDENTIALS=path/to/your/firebase-key.json
   ```

### 4. Environment Configuration
Create a `.env` file in the root directory:
```env
# Firebase Configuration
FIREBASE_API_KEY=your_api_key_here
FIREBASE_AUTH_DOMAIN=your_project.firebaseapp.com
FIREBASE_PROJECT_ID=your_project_id
FIREBASE_STORAGE_BUCKET=your_project.appspot.com
FIREBASE_MESSAGING_SENDER_ID=your_sender_id
FIREBASE_APP_ID=your_app_id

# Flask Configuration
FLASK_ENV=development
SECRET_KEY=your_secret_key_here
```

### 5. Run the Application
```bash
cd backend
python app.py
```

The application will be available at `http://127.0.0.1:5000`

## 🔐 Authentication System

### Faculty Authentication

#### Registration Process
```python
# Frontend JavaScript
const registerFaculty = async (userData) => {
    // Create Firebase Auth user
    const userCredential = await auth.createUserWithEmailAndPassword(
        userData.email,
        userData.password
    );

    // Get ID token
    const idToken = await userCredential.user.getIdToken();

    // Register with backend
    const response = await fetch('/register', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({
            idToken: idToken,
            name: userData.name,
            department: userData.department
        })
    });
};
```

#### Backend Registration Handler
```python
@app.route('/register', methods=['POST'])
def register():
    data = request.get_json()
    id_token = data.get('idToken')

    try:
        # Verify Firebase ID token
        decoded_token = auth.verify_id_token(id_token)
        uid = decoded_token['uid']
        email = decoded_token['email']

        # Create user profile in Firestore
        user_data = {
            'uid': uid,
            'email': email,
            'name': data.get('name'),
            'department': data.get('department'),
            'role': 'faculty',
            'created_at': datetime.now(),
            'approved': True  # Faculty auto-approved
        }

        db.collection('users').document(uid).set(user_data)
        return jsonify({"message": "Registration successful!"}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 400
```

### HOD Authentication System

#### HOD Registration Process
```python
# Frontend JavaScript
const registerHOD = async (userData) => {
    // Create Firebase Auth user
    const userCredential = await auth.createUserWithEmailAndPassword(
        userData.email,
        userData.password
    );

    // Get ID token
    const idToken = await userCredential.user.getIdToken();

    // Register as HOD with backend
    const response = await fetch('/hod_register', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({
            idToken: idToken,
            name: userData.name,
            department: userData.department,
            hodCode: userData.hodCode  // Special verification code
        })
    });
};
```

#### Backend HOD Registration Handler
```python
@app.route('/hod_register', methods=['POST'])
def hod_register():
    data = request.get_json()
    id_token = data.get('idToken')
    hod_code = data.get('hodCode')

    # Verify HOD code (implement your verification logic)
    valid_hod_codes = {
        'HOD_CS_2024': 'Computer Science',
        'HOD_ECE_2024': 'Electronics & Communication',
        'HOD_ME_2024': 'Mechanical Engineering'
    }

    if hod_code not in valid_hod_codes:
        return jsonify({"error": "Invalid HOD verification code"}), 400

    try:
        # Verify Firebase ID token
        decoded_token = auth.verify_id_token(id_token)
        uid = decoded_token['uid']
        email = decoded_token['email']

        # Create HOD profile in Firestore
        hod_data = {
            'uid': uid,
            'email': email,
            'name': data.get('name'),
            'department': data.get('department'),
            'role': 'hod',
            'hod_code': hod_code,
            'created_at': datetime.now(),
            'approved': True,  # HOD auto-approved with valid code
            'permissions': {
                'review_papers': True,
                'manage_faculty': True,
                'view_analytics': True,
                'approve_papers': True
            }
        }

        db.collection('hod_users').document(uid).set(hod_data)
        return jsonify({"message": "HOD registration successful!"}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 400
```

#### HOD Login Process
```python
# Frontend JavaScript
const loginHOD = async (credentials) => {
    // Sign in with Firebase
    const userCredential = await auth.signInWithEmailAndPassword(
        credentials.email,
        credentials.password
    );

    // Get ID token
    const idToken = await userCredential.user.getIdToken();

    // Verify HOD status with backend
    const response = await fetch('/hod_login', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({ idToken })
    });

    if (response.ok) {
        const data = await response.json();
        localStorage.setItem('hodUser', JSON.stringify(data.user));
        window.location.href = '/hod-dashboard';
    }
};
```

#### Backend HOD Login Handler
```python
@app.route('/hod_login', methods=['POST'])
def hod_login():
    data = request.get_json()
    id_token = data.get('idToken')

    try:
        # Verify Firebase ID token
        decoded_token = auth.verify_id_token(id_token)
        uid = decoded_token['uid']

        # Check if user is HOD
        hod_doc = db.collection('hod_users').document(uid).get()

        if not hod_doc.exists:
            return jsonify({"error": "Not authorized as HOD"}), 403

        hod_data = hod_doc.to_dict()

        if not hod_data.get('approved', False):
            return jsonify({"error": "HOD account not approved"}), 403

        return jsonify({
            "message": "HOD login successful",
            "user": {
                "uid": uid,
                "name": hod_data.get('name'),
                "department": hod_data.get('department'),
                "role": "hod",
                "permissions": hod_data.get('permissions', {})
            }
        }), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 400
```

### Authentication Middleware

#### Firebase Auth Decorator
```python
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
            request.current_user_uid = decoded_token['uid']
            return f(*args, **kwargs)
        except firebase_admin.auth.InvalidIdTokenError:
            return jsonify({'message': 'Invalid or expired authentication token.'}), 401
        except Exception as e:
            return jsonify({'message': f'Authentication error: {str(e)}'}), 500
    return decorated_function
```

#### HOD Role Verification
```python
def hod_required(f):
    """Decorator to ensure user has HOD privileges."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        user_uid = request.current_user_uid

        try:
            # Check if user is HOD
            hod_doc = db.collection('hod_users').document(user_uid).get()

            if not hod_doc.exists:
                return jsonify({'message': 'HOD access required'}), 403

            hod_data = hod_doc.to_dict()
            if not hod_data.get('approved', False):
                return jsonify({'message': 'HOD account not approved'}), 403

            request.current_hod_data = hod_data
            return f(*args, **kwargs)

        except Exception as e:
            return jsonify({'message': f'Authorization error: {str(e)}'}), 500
    return decorated_function

# Usage example
@app.route('/hod-dashboard')
@firebase_auth_required
@hod_required
def hod_dashboard():
    hod_data = request.current_hod_data
    return render_template('hod_dashboard.html', hod=hod_data)
```

### Session Management

#### Client-Side Token Management
```javascript
// Store authentication state
const authState = {
    user: null,
    idToken: null,
    role: null
};

// Listen for auth state changes
auth.onAuthStateChanged(async (user) => {
    if (user) {
        authState.user = user;
        authState.idToken = await user.getIdToken();

        // Determine user role
        const hodUser = localStorage.getItem('hodUser');
        const facultyUser = localStorage.getItem('facultyUser');

        if (hodUser) {
            authState.role = 'hod';
        } else if (facultyUser) {
            authState.role = 'faculty';
        }
    } else {
        authState.user = null;
        authState.idToken = null;
        authState.role = null;
        localStorage.removeItem('hodUser');
        localStorage.removeItem('facultyUser');
    }
});

// Make authenticated requests
const makeAuthenticatedRequest = async (url, options = {}) => {
    if (!authState.idToken) {
        throw new Error('Not authenticated');
    }

    const headers = {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${authState.idToken}`,
        ...options.headers
    };

    return fetch(url, { ...options, headers });
};
```

### Authentication Flow Summary
1. **Registration**: User creates account → Firebase Auth → Backend verification → Firestore profile
2. **Login**: Credentials verification → Firebase ID token → Role verification → Dashboard redirect
3. **Protected Routes**: ID token validation → Role checking → Access granted/denied
4. **Session Management**: Token refresh → State persistence → Automatic logout on expiry
5. **Logout**: Firebase signOut → Clear local storage → Redirect to login

## 📊 API Endpoints

### Public Endpoints
- `GET /` - Landing page
- `GET /login` - Faculty login page
- `GET /register` - Faculty registration page
- `GET /hod-login` - HOD login page
- `GET /hod-register` - HOD registration page

### Faculty Endpoints (Protected)
- `GET /dashboard` - Faculty dashboard
- `POST /upload_questions` - Upload question bank
- `GET /get_user_questions` - Fetch user's questions
- `POST /generate_question_paper` - Generate question paper
- `POST /generate_final_document` - Generate final document

### HOD Endpoints (Protected + Role-based)
- `GET /hod-dashboard` - HOD dashboard
- `POST /verify_hod` - Verify HOD status
- `GET /get_pending_papers` - Get papers pending review
- `POST /approve_paper` - Approve question paper
- `POST /request_revision` - Request paper revision
- `GET /get_faculty_list` - Get department faculty
- `GET /get_department_analytics` - Get analytics data

## 👑 HOD Workflow & Features

### Paper Review Process

#### 1. Pending Papers Review
```python
@app.route('/get_pending_papers', methods=['GET'])
@firebase_auth_required
@hod_required
def get_pending_papers():
    hod_data = request.current_hod_data
    department = hod_data.get('department')

    # Get papers pending review from same department
    papers_ref = db.collection('generated_papers')
    query = papers_ref.where('department', '==', department)\
                     .where('status', '==', 'pending_review')\
                     .order_by('created_at', direction=firestore.Query.DESCENDING)

    papers = []
    for doc in query.stream():
        paper_data = doc.to_dict()
        paper_data['id'] = doc.id
        papers.append(paper_data)

    return jsonify({"papers": papers}), 200
```

#### 2. Paper Approval
```python
@app.route('/approve_paper', methods=['POST'])
@firebase_auth_required
@hod_required
def approve_paper():
    data = request.get_json()
    paper_id = data.get('paper_id')
    comments = data.get('comments', '')

    hod_data = request.current_hod_data

    try:
        # Update paper status
        paper_ref = db.collection('generated_papers').document(paper_id)
        paper_ref.update({
            'status': 'approved',
            'approved_by': hod_data.get('name'),
            'approved_at': datetime.now(),
            'hod_comments': comments,
            'approval_history': firestore.ArrayUnion([{
                'action': 'approved',
                'by': hod_data.get('name'),
                'at': datetime.now(),
                'comments': comments
            }])
        })

        return jsonify({"message": "Paper approved successfully"}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500
```

#### 3. Request Revision
```python
@app.route('/request_revision', methods=['POST'])
@firebase_auth_required
@hod_required
def request_revision():
    data = request.get_json()
    paper_id = data.get('paper_id')
    revision_comments = data.get('comments', '')

    hod_data = request.current_hod_data

    try:
        # Update paper status
        paper_ref = db.collection('generated_papers').document(paper_id)
        paper_ref.update({
            'status': 'needs_revision',
            'revision_requested_by': hod_data.get('name'),
            'revision_requested_at': datetime.now(),
            'revision_comments': revision_comments,
            'approval_history': firestore.ArrayUnion([{
                'action': 'revision_requested',
                'by': hod_data.get('name'),
                'at': datetime.now(),
                'comments': revision_comments
            }])
        })

        return jsonify({"message": "Revision requested successfully"}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500
```

### Faculty Management

#### Get Department Faculty
```python
@app.route('/get_faculty_list', methods=['GET'])
@firebase_auth_required
@hod_required
def get_faculty_list():
    hod_data = request.current_hod_data
    department = hod_data.get('department')

    # Get faculty from same department
    faculty_ref = db.collection('users')
    query = faculty_ref.where('department', '==', department)\
                      .where('role', '==', 'faculty')

    faculty_list = []
    for doc in query.stream():
        faculty_data = doc.to_dict()

        # Get faculty statistics
        papers_count = db.collection('generated_papers')\
                        .where('faculty_uid', '==', faculty_data['uid'])\
                        .get()

        faculty_data['papers_submitted'] = len(papers_count)
        faculty_data['id'] = doc.id
        faculty_list.append(faculty_data)

    return jsonify({"faculty": faculty_list}), 200
```

### Analytics Dashboard

#### Department Analytics
```python
@app.route('/get_department_analytics', methods=['GET'])
@firebase_auth_required
@hod_required
def get_department_analytics():
    hod_data = request.current_hod_data
    department = hod_data.get('department')

    # Get department statistics
    papers_ref = db.collection('generated_papers')
    dept_papers = papers_ref.where('department', '==', department).get()

    analytics = {
        'total_papers': len(dept_papers),
        'pending_review': 0,
        'approved': 0,
        'needs_revision': 0,
        'faculty_count': 0,
        'monthly_stats': {},
        'subject_distribution': {},
        'quality_metrics': {
            'avg_review_time': 0,
            'approval_rate': 0,
            'revision_rate': 0
        }
    }

    # Calculate statistics
    for paper in dept_papers:
        paper_data = paper.to_dict()
        status = paper_data.get('status', 'pending')

        if status == 'pending_review':
            analytics['pending_review'] += 1
        elif status == 'approved':
            analytics['approved'] += 1
        elif status == 'needs_revision':
            analytics['needs_revision'] += 1

    # Calculate rates
    if analytics['total_papers'] > 0:
        analytics['quality_metrics']['approval_rate'] = \
            (analytics['approved'] / analytics['total_papers']) * 100
        analytics['quality_metrics']['revision_rate'] = \
            (analytics['needs_revision'] / analytics['total_papers']) * 100

    return jsonify({"analytics": analytics}), 200
```

### HOD Dashboard Features

#### Real-time Notifications
```javascript
// HOD Dashboard - Real-time updates
const setupHODNotifications = () => {
    const hodData = JSON.parse(localStorage.getItem('hodUser'));

    // Listen for new papers requiring review
    db.collection('generated_papers')
      .where('department', '==', hodData.department)
      .where('status', '==', 'pending_review')
      .onSnapshot((snapshot) => {
          const pendingCount = snapshot.size;
          document.getElementById('pending-count').textContent = pendingCount;

          // Show notification for new papers
          snapshot.docChanges().forEach((change) => {
              if (change.type === 'added') {
                  showNotification('New paper submitted for review');
              }
          });
      });
};
```

#### Bulk Operations
```javascript
// Bulk approve/reject papers
const bulkApprovePapers = async (paperIds, comments) => {
    const promises = paperIds.map(paperId =>
        makeAuthenticatedRequest('/approve_paper', {
            method: 'POST',
            body: JSON.stringify({
                paper_id: paperId,
                comments: comments
            })
        })
    );

    try {
        await Promise.all(promises);
        showMessage('Papers approved successfully', 'success');
        refreshPendingPapers();
    } catch (error) {
        showMessage('Error approving papers', 'error');
    }
};
```

## 🔧 Advanced Configuration

### HOD Verification Codes
Create a secure system for HOD verification codes:

```python
# config.py
HOD_VERIFICATION_CODES = {
    'departments': {
        'Computer Science': {
            'code': 'HOD_CS_2024_SECURE',
            'expires': '2024-12-31',
            'permissions': ['review_papers', 'manage_faculty', 'view_analytics']
        },
        'Electronics & Communication': {
            'code': 'HOD_ECE_2024_SECURE',
            'expires': '2024-12-31',
            'permissions': ['review_papers', 'manage_faculty', 'view_analytics']
        }
    }
}

def verify_hod_code(code, department):
    dept_config = HOD_VERIFICATION_CODES['departments'].get(department)
    if not dept_config:
        return False

    # Check code match
    if dept_config['code'] != code:
        return False

    # Check expiration
    from datetime import datetime
    expires = datetime.strptime(dept_config['expires'], '%Y-%m-%d')
    if datetime.now() > expires:
        return False

    return True
```

### Email Notifications
```python
# Email notifications for HOD actions
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

def send_approval_notification(faculty_email, paper_title, status, comments):
    msg = MIMEMultipart()
    msg['From'] = 'noreply@smartqpgen.com'
    msg['To'] = faculty_email
    msg['Subject'] = f'Question Paper {status.title()}: {paper_title}'

    body = f"""
    Dear Faculty,

    Your question paper "{paper_title}" has been {status}.

    HOD Comments: {comments}

    Please log in to your dashboard for more details.

    Best regards,
    SmartQPGen System
    """

    msg.attach(MIMEText(body, 'plain'))

    # Send email (configure SMTP settings)
    server = smtplib.SMTP('smtp.gmail.com', 587)
    server.starttls()
    server.login('your-email@gmail.com', 'your-password')
    server.send_message(msg)
    server.quit()
```

### Audit Logging
```python
# Audit trail for HOD actions
def log_hod_action(hod_uid, action, target_id, details):
    audit_log = {
        'hod_uid': hod_uid,
        'action': action,  # 'approve', 'reject', 'request_revision'
        'target_id': target_id,  # paper_id or faculty_id
        'details': details,
        'timestamp': datetime.now(),
        'ip_address': request.remote_addr,
        'user_agent': request.headers.get('User-Agent')
    }

    db.collection('audit_logs').add(audit_log)
```

## 🎯 Question Paper Generation

### Upload Format
Question banks should be uploaded in the following format:

#### DOCX Format
| Sl. No | Question | CO | Bloom's Level | Marks |
|--------|----------|----|--------------| ------|
| 1 | What is machine learning? | CO1 | Remember | 5 |
| 2 | Explain neural networks | CO2 | Understand | 10 |

#### PDF Format
Same table structure as DOCX, properly formatted with clear column separation.

### Generation Rules
- **4 Main Questions** (Q1-Q4), each worth 25 marks
- **3 Sub-questions** per main question (a, b, c)
- **Module Distribution**:
  - Q1 OR Q2: All from Module 1
  - Q3 OR Q4: Parts (a,b) from Module 2, Part (c) from Module 3
- **Balanced Difficulty**: Mix of Bloom's taxonomy levels
- **CO Coverage**: Ensures course outcome distribution

### Sample Generated Paper Structure
```
Q1. a) [5 marks] - Module 1, CO1, Remember
    b) [10 marks] - Module 1, CO2, Understand  
    c) [10 marks] - Module 1, CO3, Apply

OR

Q2. a) [5 marks] - Module 1, CO1, Remember
    b) [10 marks] - Module 1, CO2, Analyze
    c) [10 marks] - Module 1, CO3, Evaluate
```

## 🔧 Configuration

### College Branding
Replace the following files in `backend/static/assets/`:
- `skit_logo.png` - College logo
- `college_bg.png` - Background image

### Customization
Update the following in templates:
- College name and details
- Department information  
- Course codes and names
- Examination patterns

## �️ Database Schema

### Firestore Collections

#### users (Faculty)
```json
{
  "uid": "firebase_user_id",
  "email": "faculty@college.edu",
  "name": "Dr. John Doe",
  "department": "Computer Science",
  "role": "faculty",
  "created_at": "2024-01-15T10:30:00Z",
  "approved": true,
  "profile": {
    "phone": "+91-9876543210",
    "designation": "Assistant Professor",
    "experience": "5 years"
  }
}
```

#### hod_users (HOD)
```json
{
  "uid": "firebase_user_id",
  "email": "hod@college.edu",
  "name": "Dr. Jane Smith",
  "department": "Computer Science",
  "role": "hod",
  "hod_code": "HOD_CS_2024_SECURE",
  "created_at": "2024-01-15T10:30:00Z",
  "approved": true,
  "permissions": {
    "review_papers": true,
    "manage_faculty": true,
    "view_analytics": true,
    "approve_papers": true
  }
}
```

#### question_banks
```json
{
  "id": "unique_question_bank_id",
  "faculty_uid": "firebase_user_id",
  "faculty_name": "Dr. John Doe",
  "department": "Computer Science",
  "subject": "Machine Learning",
  "course_code": "CS701",
  "filename": "ml_questions.docx",
  "upload_date": "2024-01-15T10:30:00Z",
  "questions": [
    {
      "sl_no": "1",
      "question_text": "What is machine learning?",
      "co": "CO1",
      "blooms_level": "Remember",
      "marks": "5",
      "module": "1"
    }
  ],
  "total_questions": 50,
  "status": "active"
}
```

#### generated_papers
```json
{
  "id": "unique_paper_id",
  "faculty_uid": "firebase_user_id",
  "faculty_name": "Dr. John Doe",
  "department": "Computer Science",
  "subject": "Machine Learning",
  "course_code": "CS701",
  "paper_title": "Machine Learning - IA1",
  "created_at": "2024-01-15T10:30:00Z",
  "status": "pending_review", // pending_review, approved, needs_revision
  "questions": [
    {
      "main_question": 1,
      "sub_questions": [
        {
          "letter": "a",
          "question_text": "Define machine learning",
          "marks": 5,
          "co": "CO1",
          "blooms_level": "Remember",
          "module": "1"
        }
      ],
      "total_marks": 25
    }
  ],
  "metadata": {
    "total_marks": 100,
    "duration": "3 hours",
    "exam_type": "IA1"
  },
  "approval_history": [
    {
      "action": "submitted",
      "by": "Dr. John Doe",
      "at": "2024-01-15T10:30:00Z",
      "comments": "Initial submission"
    }
  ],
  "hod_comments": "",
  "approved_by": "",
  "approved_at": null
}
```

#### audit_logs
```json
{
  "id": "unique_log_id",
  "hod_uid": "firebase_user_id",
  "action": "approve_paper",
  "target_id": "paper_id",
  "details": {
    "paper_title": "Machine Learning - IA1",
    "faculty_name": "Dr. John Doe",
    "comments": "Good quality questions"
  },
  "timestamp": "2024-01-15T10:30:00Z",
  "ip_address": "192.168.1.100",
  "user_agent": "Mozilla/5.0..."
}
```

## 🔒 Security Considerations

### Authentication Security
```python
# Token validation with expiration check
def validate_token_with_expiry(id_token):
    try:
        decoded_token = auth.verify_id_token(id_token, check_revoked=True)

        # Check token expiration
        exp = decoded_token.get('exp', 0)
        if time.time() > exp:
            raise ValueError("Token expired")

        return decoded_token
    except Exception as e:
        raise ValueError(f"Invalid token: {str(e)}")
```

### Input Validation
```python
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

# Rate limiting
limiter = Limiter(
    app,
    key_func=get_remote_address,
    default_limits=["200 per day", "50 per hour"]
)

# File upload validation
def validate_uploaded_file(file):
    # Check file size (max 16MB)
    if len(file.read()) > 16 * 1024 * 1024:
        raise ValueError("File too large")

    file.seek(0)  # Reset file pointer

    # Check file type
    allowed_extensions = {'docx', 'pdf'}
    if not file.filename.lower().endswith(tuple(allowed_extensions)):
        raise ValueError("Invalid file type")

    # Scan for malicious content (implement virus scanning)
    # scan_file_for_malware(file)

    return True
```

### Data Sanitization
```python
import bleach
import re

def sanitize_input(text):
    # Remove HTML tags
    clean_text = bleach.clean(text, strip=True)

    # Remove potentially dangerous characters
    clean_text = re.sub(r'[<>"\']', '', clean_text)

    # Limit length
    return clean_text[:1000]

def sanitize_question_data(question):
    return {
        'sl_no': sanitize_input(question.get('sl_no', '')),
        'question_text': sanitize_input(question.get('question_text', '')),
        'co': sanitize_input(question.get('co', '')),
        'blooms_level': sanitize_input(question.get('blooms_level', '')),
        'marks': sanitize_input(question.get('marks', ''))
    }
```

### CORS Configuration
```python
from flask_cors import CORS

# Production CORS configuration
CORS(app,
     origins=['https://yourdomain.com'],
     methods=['GET', 'POST', 'PUT', 'DELETE'],
     allow_headers=['Content-Type', 'Authorization'])
```

## �🛠️ Development

### Project Structure
```
SmartQPGen/
├── backend/
│   ├── app.py                    # Main Flask application
│   ├── generator.py              # Legacy generator (optional)
│   ├── config.py                 # Configuration settings
│   ├── utils/
│   │   ├── auth.py              # Authentication utilities
│   │   ├── validators.py        # Input validation
│   │   └── email.py             # Email notifications
│   ├── templates/               # Jinja2 templates
│   │   ├── base.html           # Base template
│   │   ├── index.html          # Landing page
│   │   ├── login.html          # Faculty login
│   │   ├── register.html       # Faculty registration
│   │   ├── dashboard.html      # Faculty dashboard
│   │   ├── hod_login.html      # HOD login
│   │   ├── hod_register.html   # HOD registration
│   │   └── hod_dashboard.html  # HOD dashboard
│   ├── static/                 # Static files
│   │   ├── css/               # Stylesheets
│   │   ├── js/                # JavaScript files
│   │   └── assets/            # Images, fonts
│   └── uploads/               # Temporary file storage
├── tests/                     # Unit tests
├── docs/                      # Documentation
├── requirements.txt           # Python dependencies
├── .env.example              # Environment variables template
├── .gitignore               # Git ignore rules
└── README.md                # This file
```

### Key Functions

#### Authentication Decorator
```python
@firebase_auth_required
def protected_route():
    user_uid = request.current_user_uid
    # Route logic here
```

#### HOD Role Verification
```python
async def verify_hod_status(user_uid):
    hod_doc = db.collection('hod_users').document(user_uid).get()
    return hod_doc.exists and hod_doc.to_dict().get('approved', False)
```

#### Question Paper Generation
```python
def generate_paper_with_rules(all_questions):
    # Implements the 4-question, 25-marks-each structure
    # Handles module distribution and difficulty balancing
    return generated_paper
```

### Development Workflow
1. **Setup Environment**: Install dependencies and configure Firebase
2. **Database Setup**: Initialize Firestore collections
3. **Authentication**: Configure Firebase Auth and test login flows
4. **Feature Development**: Add new features with proper testing
5. **Testing**: Run unit tests and integration tests
6. **Deployment**: Deploy to staging/production environment

### Adding New Features
1. **New Routes**: Add to `app.py` with appropriate decorators
2. **Templates**: Create HTML templates in `templates/`
3. **Static Assets**: Add CSS/JS to `static/`
4. **Database**: Update Firestore collections as needed
5. **Tests**: Write unit tests for new functionality

## 🧪 Testing

### Unit Tests
```python
# tests/test_auth.py
import unittest
from unittest.mock import patch, MagicMock
from backend.app import app, firebase_auth_required

class TestAuthentication(unittest.TestCase):
    def setUp(self):
        self.app = app.test_client()
        self.app.testing = True

    @patch('backend.app.auth.verify_id_token')
    def test_valid_token(self, mock_verify):
        mock_verify.return_value = {'uid': 'test_uid'}

        response = self.app.get('/dashboard',
                               headers={'Authorization': 'Bearer valid_token'})
        self.assertEqual(response.status_code, 200)

    def test_missing_token(self):
        response = self.app.get('/dashboard')
        self.assertEqual(response.status_code, 401)

# tests/test_question_generation.py
class TestQuestionGeneration(unittest.TestCase):
    def test_paper_generation_rules(self):
        from backend.app import generate_paper_with_rules

        sample_questions = [
            {'question_text': 'Q1', 'marks': '5', 'module': '1'},
            {'question_text': 'Q2', 'marks': '10', 'module': '1'},
            # ... more questions
        ]

        result = generate_paper_with_rules(sample_questions)
        self.assertEqual(len(result), 4)  # 4 main questions
        self.assertEqual(sum(q['maxMarks'] for q in result), 100)  # Total 100 marks

if __name__ == '__main__':
    unittest.main()
```

### Integration Tests
```python
# tests/test_integration.py
import pytest
from backend.app import app, db

@pytest.fixture
def client():
    app.config['TESTING'] = True
    with app.test_client() as client:
        yield client

def test_full_workflow(client):
    # Test registration
    response = client.post('/register', json={
        'idToken': 'mock_token',
        'name': 'Test User',
        'department': 'Computer Science'
    })
    assert response.status_code == 200

    # Test login
    response = client.post('/login', json={
        'email': 'test@example.com',
        'password': 'password'
    })
    assert response.status_code == 200

    # Test question upload
    # Test paper generation
    # Test HOD approval workflow
```

### Running Tests
```bash
# Install test dependencies
pip install pytest pytest-cov

# Run all tests
python -m pytest tests/

# Run with coverage
python -m pytest --cov=backend tests/

# Run specific test file
python -m pytest tests/test_auth.py -v
```

## 🚀 Deployment

### Local Development
```bash
cd backend
python app.py
```

### Production Deployment

#### Using Gunicorn (Linux/Mac)
```bash
pip install gunicorn
gunicorn -w 4 -b 0.0.0.0:8000 app:app
```

#### Using Waitress (Windows)
```bash
pip install waitress
waitress-serve --host=0.0.0.0 --port=8000 app:app
```

#### Docker Deployment
```dockerfile
FROM python:3.9-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY backend/ ./backend/
COPY static/ ./static/

# Set environment variables
ENV FLASK_ENV=production
ENV PYTHONPATH=/app

# Expose port
EXPOSE 5000

# Health check
HEALTHCHECK --interval=30s --timeout=30s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:5000/ || exit 1

# Run application
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "4", "backend.app:app"]
```

#### Docker Compose
```yaml
# docker-compose.yml
version: '3.8'

services:
  smartqpgen:
    build: .
    ports:
      - "5000:5000"
    environment:
      - FLASK_ENV=production
      - GOOGLE_APPLICATION_CREDENTIALS=/app/firebase-key.json
    volumes:
      - ./firebase-key.json:/app/firebase-key.json:ro
      - ./uploads:/app/uploads
    restart: unless-stopped

  nginx:
    image: nginx:alpine
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx.conf:/etc/nginx/nginx.conf:ro
      - ./ssl:/etc/nginx/ssl:ro
    depends_on:
      - smartqpgen
    restart: unless-stopped
```

### Cloud Deployment

#### Google Cloud Platform
```bash
# Install Google Cloud SDK
curl https://sdk.cloud.google.com | bash

# Initialize and authenticate
gcloud init
gcloud auth login

# Deploy to App Engine
echo "runtime: python39" > app.yaml
echo "env_variables:" >> app.yaml
echo "  GOOGLE_APPLICATION_CREDENTIALS: firebase-key.json" >> app.yaml

gcloud app deploy
```

#### AWS Elastic Beanstalk
```bash
# Install EB CLI
pip install awsebcli

# Initialize EB application
eb init smartqpgen

# Create environment and deploy
eb create production
eb deploy
```

#### Heroku
```bash
# Install Heroku CLI
# Create Procfile
echo "web: gunicorn backend.app:app" > Procfile

# Deploy
heroku create smartqpgen-app
heroku config:set FLASK_ENV=production
heroku config:set GOOGLE_APPLICATION_CREDENTIALS=firebase-key.json
git push heroku main
```

### Environment Variables for Production
```env
# .env.production
FLASK_ENV=production
SECRET_KEY=your_super_secure_production_secret_key_here
GOOGLE_APPLICATION_CREDENTIALS=/path/to/firebase-key.json

# Database
FIREBASE_PROJECT_ID=your-project-id

# Email Configuration (optional)
SMTP_SERVER=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=your-email@gmail.com
SMTP_PASSWORD=your-app-password

# Security
ALLOWED_ORIGINS=https://yourdomain.com,https://www.yourdomain.com
RATE_LIMIT_ENABLED=true

# Monitoring
SENTRY_DSN=your-sentry-dsn-here
LOG_LEVEL=INFO
```

### SSL/HTTPS Configuration
```nginx
# nginx.conf
server {
    listen 80;
    server_name yourdomain.com www.yourdomain.com;
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name yourdomain.com www.yourdomain.com;

    ssl_certificate /etc/nginx/ssl/cert.pem;
    ssl_certificate_key /etc/nginx/ssl/key.pem;

    location / {
        proxy_pass http://smartqpgen:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

### Monitoring and Logging
```python
# backend/utils/monitoring.py
import logging
import sentry_sdk
from sentry_sdk.integrations.flask import FlaskIntegration

# Initialize Sentry for error tracking
sentry_sdk.init(
    dsn="your-sentry-dsn",
    integrations=[FlaskIntegration()],
    traces_sample_rate=1.0
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(name)s %(message)s',
    handlers=[
        logging.FileHandler('app.log'),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)

# Usage in routes
@app.route('/some-route')
def some_route():
    try:
        # Route logic
        logger.info("Route accessed successfully")
        return jsonify({"status": "success"})
    except Exception as e:
        logger.error(f"Error in route: {str(e)}")
        sentry_sdk.capture_exception(e)
        return jsonify({"error": "Internal server error"}), 500
```

## 🔍 Troubleshooting

### Common Issues

#### PDF Conversion Errors
```
Error: CoInitialize has not been called
```
**Solution**: The app includes robust PDF conversion with COM initialization. Ensure Microsoft Word is installed on Windows.

#### Firebase Authentication Errors
```
Error: Invalid or expired authentication token
```
**Solution**: Check Firebase configuration and ensure ID tokens are properly passed in Authorization headers.

#### File Upload Issues
```
Error: File type not supported
```
**Solution**: Ensure uploaded files are in DOCX or PDF format with proper question bank structure.

### Debug Mode
Enable debug logging:
```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

## 📝 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit your changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

## 📞 Support

For support and questions:
- 📧 Email: amruthamhalgeri@gmail.com
- 📱 Phone: +91-8970014248

## 🙏 Acknowledgments

- Firebase for authentication and database services
- Flask framework for web application development
- Python-docx for document processing
- All contributors and testers

---

**Made with ❤️ for Educational Institutions by amruthamhalgeri**
