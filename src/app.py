#!/usr/bin/env python3
"""
StudioZero entry point — choose between CLI Wizard and Web Server.

Usage: python -m src.app
"""

import sys
import logging
import threading
import webbrowser
import uvicorn
from src.cli import main as cli_main

PORT = 8910

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)


def _open_browser():
    """Open browser after a short delay to let uvicorn bind."""
    import time
    time.sleep(1.2)
    webbrowser.open(f"http://localhost:{PORT}")


def run_server():
    threading.Thread(target=_open_browser, daemon=True).start()
    uvicorn.run(
        "src.server:app",
        host="127.0.0.1",
        port=PORT,
        log_level="info",
    )


def main():
    print("\n" + "=" * 60)
    print("  StudioZero - AI Video Generation Studio")
    print("=" * 60 + "\n")
    print("Choose your interface:")
    print("1. Interactive CLI Wizard (Recommended for quick runs)")
    print("2. Web Dashboard (Recommended for project management)")
    
    choice = input("\nEnter choice (1 or 2): ").strip()
    
    if choice == "1":
        sys.exit(cli_main())
    elif choice == "2":
        run_server()
    else:
        print("Invalid choice. Defaulting to CLI Wizard...")
        sys.exit(cli_main())


if __name__ == "__main__":
    main()
