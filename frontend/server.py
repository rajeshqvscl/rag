"""
Simple HTTP server to serve the FinRAG frontend on port 9001.
The backend API remains on port 9000.
"""
import http.server
import socketserver
import os

PORT = 9001
DIRECTORY = os.path.dirname(os.path.abspath(__file__))

class MyHTTPRequestHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=DIRECTORY, **kwargs)

    def log_message(self, format, *args):
        # Add timestamp to logs
        from datetime import datetime
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"[{timestamp}] {self.address_string()} - {format % args}")

if __name__ == "__main__":
    with socketserver.TCPServer(("", PORT), MyHTTPRequestHandler) as httpd:
        print(f"=" * 50)
        print(f"FinRAG Frontend Server")
        print(f"=" * 50)
        print(f"Serving at: http://localhost:{PORT}")
        print(f"Frontend directory: {DIRECTORY}")
        print(f"Backend API: http://localhost:9000")
        print(f"=" * 50)
        print(f"Press Ctrl+C to stop the server")
        print(f"=" * 50)
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\n\nServer stopped.")
