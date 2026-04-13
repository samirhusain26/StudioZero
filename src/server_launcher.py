#!/usr/bin/env python3
"""Direct launcher for the StudioZero web dashboard (skips CLI menu)."""

import threading
import webbrowser
import time
import uvicorn

PORT = 8910


def _open_browser():
    time.sleep(1.5)
    webbrowser.open(f"http://localhost:{PORT}")


if __name__ == "__main__":
    threading.Thread(target=_open_browser, daemon=True).start()
    uvicorn.run(
        "src.server:app",
        host="127.0.0.1",
        port=PORT,
        log_level="info",
    )
