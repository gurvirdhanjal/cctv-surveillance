#!/usr/bin/env python3
"""
Run this script to open the VMS architecture presentation in your browser.

From project root:
    python docs/presentation/serve.py

From this directory:
    python serve.py

If 'python' is not on your PATH, use the full path:
    "C:\Users\APL TECHNO\AppData\Local\Programs\Python\Python310\python.exe" serve.py
"""

import http.server
import os
import socket
import threading
import webbrowser

PORT = 7420
HERE = os.path.dirname(os.path.abspath(__file__))


def find_free_port(start: int) -> int:
    for p in range(start, start + 20):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(("localhost", p)) != 0:
                return p
    return start


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=HERE, **kwargs)

    def log_message(self, fmt, *args):
        pass  # suppress per-request noise


if __name__ == "__main__":
    port = find_free_port(PORT)
    url = f"http://localhost:{port}"

    server = http.server.HTTPServer(("", port), Handler)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()

    print(f"\n  VMS Architecture Presentation")
    print(f"  -----------------------------")
    print(f"  URL   : {url}")
    print(f"  Slides: 12   (arrow keys or Space to navigate)")
    print(f"\n  Opening browser... Press Ctrl+C to stop.\n")

    webbrowser.open(url)

    try:
        t.join()
    except KeyboardInterrupt:
        print("\n  Server stopped.")
        server.shutdown()
