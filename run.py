"""
Run script for Gen AI Academy APAC Edition
Run this from the project root directory
"""
import sys
import os

# Add the project root to Python path
project_root = os.path.dirname(os.path.abspath(__file__))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from server.app import create_app

if __name__ == '__main__':
    app = create_app()
    app.run(host='0.0.0.0', port=3002, debug=True)
