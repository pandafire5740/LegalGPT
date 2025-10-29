#!/usr/bin/env python3
"""
Startup script for Legal Knowledge Platform
"""
import os
import sys
import subprocess
import time
from pathlib import Path

# Load environment variables from .env file if it exists
from dotenv import load_dotenv
load_dotenv()

def check_requirements():
    """Check if all requirements are met."""
    print("🔍 Checking requirements...")
    
    # Check if .env file exists
    if not os.path.exists('.env'):
        print("❌ .env file not found. Please copy config.env.example to .env and configure it.")
        return False
    
    # Check if Redis is running
    try:
        import redis
        r = redis.Redis(host='localhost', port=6379, db=0)
        r.ping()
        print("✅ Redis connection successful")
    except Exception as e:
        print(f"❌ Redis connection failed: {e}")
        print("   Please make sure Redis is installed and running on localhost:6379")
        return False
    
    return True

def start_application():
    """Start the application components."""
    print("🚀 Starting Legal Knowledge Platform...")
    
    if not check_requirements():
        print("❌ Requirements check failed. Please fix the issues above.")
        return False
    
    # Read configuration from environment variables with defaults
    debug_mode = os.getenv("DEBUG", "True").lower() in ("true", "1", "yes")
    host = os.getenv("HOST", "localhost")
    port = int(os.getenv("PORT", "8000"))
    
    print("\n📚 Starting the main application...")
    print(f"   Access the web interface at: http://{host}:{port}")
    print(f"   API documentation at: http://{host}:{port}/docs")
    
    # Enable hot reloading in development mode
    if debug_mode:
        print("   🔥 Hot reloading enabled (development mode)")
    else:
        print("   ⚙️  Hot reloading disabled (production mode)")
    
    print("\n💡 To also run background tasks, open additional terminals and run:")
    print("   celery -A app.services.file_monitor.celery_app worker --loglevel=info")
    print("   celery -A app.services.file_monitor.celery_app beat --loglevel=info")
    print("\n🛑 Press Ctrl+C to stop the application\n")
    
    try:
        # Start the FastAPI application
        uvicorn_args = [
            sys.executable, "-m", "uvicorn",
            "app.main:app",
            "--host", host,
            "--port", str(port)
        ]
        
        # Add --reload flag in development mode
        if debug_mode:
            uvicorn_args.append("--reload")
        
        subprocess.run(uvicorn_args)
    except KeyboardInterrupt:
        print("\n👋 Application stopped.")
        return True

if __name__ == "__main__":
    start_application()
