#!/usr/bin/env python3
"""Serve index.html and proxy /api/generate to a local Ollama instance.

Usage:
    python3 server.py [--port 8000]
Then open http://localhost:8000
"""

import argparse
import http.server
import os
import urllib.error
import urllib.request

OLLAMA_URL = "http://localhost:11434/api/generate"
HERE = os.path.dirname(os.path.abspath(__file__))
STATIC_FILES = {
    "index.html": "text/html; charset=utf-8",
    "regions.js": "text/javascript; charset=utf-8",
    "wheel.png": "image/png",
}


class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        name = "index.html" if self.path == "/" else self.path.lstrip("/")
        if name not in STATIC_FILES:
            self.send_error(404)
            return
        with open(os.path.join(HERE, name), "rb") as f:
            body = f.read()
        self.send_response(200)
        self.send_header("Content-Type", STATIC_FILES[name])
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        if self.path != "/api/generate":
            self.send_error(404)
            return
        payload = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        request = urllib.request.Request(
            OLLAMA_URL, data=payload, headers={"Content-Type": "application/json"}
        )
        try:
            upstream = urllib.request.urlopen(request)
        except urllib.error.HTTPError as e:
            self.send_error(e.code, e.reason)
            return
        except urllib.error.URLError:
            self.send_error(502, "Could not reach Ollama. Run: ollama serve")
            return
        with upstream:
            self.send_response(200)
            self.send_header("Content-Type", "application/x-ndjson")
            self.end_headers()
            for line in upstream:
                self.wfile.write(line)
                self.wfile.flush()


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    server = http.server.ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print(f"Open http://localhost:{args.port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
