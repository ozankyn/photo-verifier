"""
Photo Verifier - Production Server
===================================
Waitress WSGI server ile production çalıştırma.
"""

from waitress import serve
from app import app

if __name__ == '__main__':
    print("=" * 50)
    print("📸 Photo Verifier - Production Server")
    print("=" * 50)
    print("http://0.0.0.0:5555")
    print("=" * 50)
    
    serve(app, host='0.0.0.0', port=5555, threads=4)
