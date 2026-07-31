#!/usr/bin/env python3
"""
SmartQPGen Setup Script
Automated setup for the SmartQPGen application
"""

import os
import sys
import subprocess
import shutil
from pathlib import Path

def print_banner():
    """Print the setup banner"""
    print("=" * 60)
    print("🎓 SmartQPGen - Setup Script")
    print("Intelligent Question Paper Generation System")
    print("=" * 60)
    print()

def check_python_version():
    """Check if Python version is compatible"""
    if sys.version_info < (3, 8):
        print("❌ Error: Python 3.8 or higher is required")
        print(f"Current version: {sys.version}")
        sys.exit(1)
    print(f"✅ Python version: {sys.version.split()[0]}")

def check_pip():
    """Check if pip is available"""
    try:
        subprocess.run([sys.executable, "-m", "pip", "--version"], 
                      check=True, capture_output=True)
        print("✅ pip is available")
    except subprocess.CalledProcessError:
        print("❌ Error: pip is not available")
        sys.exit(1)

def create_virtual_environment():
    """Create a virtual environment"""
    venv_path = Path("venv")
    if venv_path.exists():
        print("📁 Virtual environment already exists")
        return
    
    print("🔧 Creating virtual environment...")
    try:
        subprocess.run([sys.executable, "-m", "venv", "venv"], check=True)
        print("✅ Virtual environment created")
    except subprocess.CalledProcessError:
        print("❌ Error: Failed to create virtual environment")
        sys.exit(1)

def get_pip_command():
    """Get the appropriate pip command for the platform"""
    if os.name == 'nt':  # Windows
        return os.path.join("venv", "Scripts", "pip")
    else:  # Unix/Linux/Mac
        return os.path.join("venv", "bin", "pip")

def install_dependencies():
    """Install Python dependencies"""
    print("📦 Installing dependencies...")
    pip_cmd = get_pip_command()
    
    try:
        # Upgrade pip first
        subprocess.run([pip_cmd, "install", "--upgrade", "pip"], check=True)
        
        # Install requirements
        subprocess.run([pip_cmd, "install", "-r", "requirements.txt"], check=True)
        print("✅ Dependencies installed successfully")
    except subprocess.CalledProcessError:
        print("❌ Error: Failed to install dependencies")
        sys.exit(1)

def create_directories():
    """Create necessary directories"""
    directories = [
        "backend/uploads",
        "backend/static/assets",
        "logs",
        "tests"
    ]
    
    for directory in directories:
        Path(directory).mkdir(parents=True, exist_ok=True)
    
    print("✅ Directories created")

def setup_environment_file():
    """Setup environment configuration"""
    env_file = Path(".env")
    env_example = Path(".env.example")
    
    if env_file.exists():
        print("📄 .env file already exists")
        return
    
    if env_example.exists():
        shutil.copy(env_example, env_file)
        print("✅ .env file created from template")
        print("⚠️  Please edit .env file with your Firebase configuration")
    else:
        print("⚠️  .env.example not found, please create .env manually")

def check_firebase_setup():
    """Check if Firebase is properly configured"""
    print("\n🔥 Firebase Setup Checklist:")
    print("1. Create a Firebase project at https://console.firebase.google.com/")
    print("2. Enable Authentication (Email/Password)")
    print("3. Create Firestore database")
    print("4. Download service account key JSON file")
    print("5. Update .env file with your Firebase configuration")
    print("6. Set GOOGLE_APPLICATION_CREDENTIALS environment variable")

def print_next_steps():
    """Print next steps for the user"""
    print("\n" + "=" * 60)
    print("🎉 Setup Complete!")
    print("=" * 60)
    print("\nNext Steps:")
    print("1. Configure Firebase:")
    print("   - Edit .env file with your Firebase settings")
    print("   - Place your Firebase service account key in the project")
    print()
    print("2. Start the application:")
    if os.name == 'nt':  # Windows
        print("   venv\\Scripts\\activate")
    else:  # Unix/Linux/Mac
        print("   source venv/bin/activate")
    print("   cd backend")
    print("   python app.py")
    print()
    print("3. Access the application:")
    print("   http://127.0.0.1:5000")
    print()
    print("4. For production deployment, see README.md")
    print("\n📚 Documentation: README.md")
    print("🐛 Issues: https://github.com/your-username/SmartQPGen/issues")

def main():
    """Main setup function"""
    print_banner()
    
    # Check system requirements
    check_python_version()
    check_pip()
    
    # Setup project
    create_virtual_environment()
    install_dependencies()
    create_directories()
    setup_environment_file()
    
    # Information
    check_firebase_setup()
    print_next_steps()

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n❌ Setup interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Setup failed: {str(e)}")
        sys.exit(1)
