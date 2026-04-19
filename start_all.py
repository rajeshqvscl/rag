"""
Master startup script for FinRAG - Starts both Backend (9000) and Frontend (9001)
"""
import subprocess
import sys
import os
import time
import signal

# Colors for Windows
GREEN = '\033[92m'
YELLOW = '\033[93m'
RED = '\033[91m'
RESET = '\033[0m'

def print_header(title):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}\n")

def check_port(port):
    """Check if a port is already in use"""
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(('localhost', port)) == 0

def start_backend():
    """Start the backend server on port 9000"""
    backend_dir = r"c:\Users\Admin\OneDrive\Documents\fin_rag\backend"
    
    print(f"{YELLOW}Starting Backend Server...{RESET}")
    print(f"Directory: {backend_dir}")
    print(f"Port: 9000")
    print(f"URL: http://localhost:9000\n")
    
    # Change to backend directory
    os.chdir(backend_dir)
    
    # Check if venv exists, create if not
    if not os.path.exists("venv"):
        print("Creating virtual environment...")
        subprocess.run([sys.executable, "-m", "venv", "venv"], check=True)
    
    # Activate and install dependencies
    activate_script = os.path.join("venv", "Scripts", "activate.bat")
    
    # Start uvicorn
    cmd = f'cmd /k "{activate_script} && python -m uvicorn app.main:app --host 0.0.0.0 --port 9000 --reload"'
    
    return subprocess.Popen(cmd, shell=True)

def start_frontend():
    """Start the frontend server on port 9001"""
    frontend_dir = r"c:\Users\Admin\OneDrive\Documents\fin_rag\frontend"
    
    print(f"{YELLOW}Starting Frontend Server...{RESET}")
    print(f"Directory: {frontend_dir}")
    print(f"Port: 9001")
    print(f"URL: http://localhost:9001\n")
    
    os.chdir(frontend_dir)
    
    # Start the frontend server
    cmd = f'cmd /k "python server.py"'
    
    return subprocess.Popen(cmd, shell=True)

def main():
    print_header("FinRAG System Startup")
    
    # Check Python
    print(f"Python: {sys.executable}")
    print(f"Platform: {sys.platform}\n")
    
    # Check if ports are already in use
    if check_port(9000):
        print(f"{YELLOW}WARNING: Port 9000 is already in use. Backend may already be running.{RESET}")
    if check_port(9001):
        print(f"{YELLOW}WARNING: Port 9001 is already in use. Frontend may already be running.{RESET}")
    
    print("\nStarting both servers in separate windows...")
    print("Press Ctrl+C in those windows to stop each server.\n")
    
    try:
        # Start backend first
        backend_proc = start_backend()
        time.sleep(2)  # Give backend time to start
        
        # Start frontend
        frontend_proc = start_frontend()
        
        print(f"\n{GREEN}✓ Both servers started successfully!{RESET}")
        print(f"\n{GREEN}Backend API:{RESET} http://localhost:9000")
        print(f"{GREEN}Frontend UI:{RESET} http://localhost:9001")
        print(f"\n{YELLOW}Press Enter to exit this launcher (servers will keep running)...{RESET}")
        input()
        
    except KeyboardInterrupt:
        print(f"\n{RED}Shutting down...{RESET}")
    except Exception as e:
        print(f"\n{RED}Error: {e}{RESET}")
        return 1
    
    return 0

if __name__ == "__main__":
    sys.exit(main())
