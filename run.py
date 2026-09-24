"""Launcher script for DATA SENSEI."""
import sys
import os
import uvicorn

# Add root directory to python search path
ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT_DIR)

from main import app

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    print("=" * 60)
    print("🥋  DATA SENSEI // YOUR AI DATA ANALYSIS MASTER")
    print(f"👉  Server running at: http://127.0.0.1:{port}")
    print("=" * 60)
    uvicorn.run(app, host="0.0.0.0", port=port)
