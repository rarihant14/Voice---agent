#!/usr/bin/env python3
"""
VOXA — Voice AI Agent
Startup script: installs deps, opens browser, runs server.
"""

import subprocess
import sys
import os
import time
import webbrowser
import threading
from pathlib import Path

ROOT = Path(__file__).parent
ENV_FILE = ROOT / ".env"
ENV_EXAMPLE = ROOT / ".env.example"
HOST = os.getenv("HOST", "127.0.0.1")
PORT = int(os.getenv("PORT", "8000"))


def check_env():
    if not ENV_FILE.exists():
        print("⚠  .env file not found. Creating from template...")
        import shutil
        shutil.copy(ENV_EXAMPLE, ENV_FILE)
        print("✏  Please edit .env and add your GROQ_API_KEY, then re-run.")
        sys.exit(1)


def install_deps():
    print("📦 Installing dependencies...")
    subprocess.check_call([
        sys.executable, "-m", "pip", "install", "-r",
        str(ROOT / "requirements.txt"), "-q"
    ])
    print("✅ Dependencies installed.")


def open_browser():
    time.sleep(2.5)
    webbrowser.open(f"http://{HOST}:{PORT}")


def run_server():
    os.chdir(ROOT)
    subprocess.run([
        sys.executable, "-m", "uvicorn",
        "app:app",
        "--host", HOST,
        "--port", str(PORT),
        "--reload",
    ])


if __name__ == "__main__":
    print("=" * 50)
    print("  VOXA — Voice-Controlled Local AI Agent")
    print("=" * 50)
    check_env()
    install_deps()
    print("\n🚀 Starting server at http://localhost:8000\n")
    threading.Thread(target=open_browser, daemon=True).start()
    run_server()
