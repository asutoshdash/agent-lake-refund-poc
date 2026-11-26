"""Serve the React refund console on loopback using the existing agent."""
import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path

from dotenv import load_dotenv
from agent import conversation, open_client, scenario_turns

ROOT = Path(__file__).resolve().parent
ASSETS = {"/": ("ui/index.html", "text/html; charset=utf-8"),
          "/app.js": ("ui/dist/app.js", "text/javascript"),
          "/style.css": ("ui/style.css", "text/css")}


class Handler(BaseHTTPRequestHandler):
    def send(self, status, content_type, body):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def json(self, status, value):
        self.send(status, "application/json", json.dumps(value).encode())

    def do_GET(self):
        asset = ASSETS.get(self.path)
        if not asset:
            return self.send_error(404)
        path, mime = asset
        self.send(200, mime, (ROOT / path).read_bytes())

    def do_POST(self):
        if self.path != "/api/query":
            return self.send_error(404)
        address = f"127.0.0.1:{self.server.server_port}"
        if self.headers.get("Host") != address or self.headers.get("Origin") != f"http://{address}":
            return self.json(403, {"error": "Open the console at its printed local address."})
        try:
            length = int(self.headers.get("Content-Length", 0))
            if self.headers.get_content_type() != "application/json" or not 0 < length <= 16384:
                raise ValueError()
            body = json.loads(self.rfile.read(length))
            if not isinstance(body, dict) or not isinstance(body.get("question"), str):
                raise ValueError()
            question = body["question"].strip()
            if not 0 < len(question) <= 1200:
                raise ValueError()
            turns = scenario_turns(body["case"], question)
        except (ValueError, KeyError, TypeError):
            return self.json(400, {"error": "Choose a scenario and enter a question up to 1,200 characters."})
        try:
            outputs = conversation(turns, complete=self.server.client.chat.completions.create,
                                   model=os.getenv("OPENAI_MODEL", "gpt-4.1-mini"))
            rows = [dict(question=t["question"], refund_id=t["refund_id"], **result)
                    for t, result in zip(turns, outputs, strict=True)]
        except Exception:
            return self.json(502, {"error": "The agent could not complete the lookup. Check your API configuration and retry."})
        self.json(200, {"turns": rows})


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8077)
    args = parser.parse_args()
    load_dotenv(ROOT / ".env")
    if not (ROOT / "ui/dist/app.js").is_file():
        parser.exit(1, "Build the UI first with npm ci --prefix ui && npm run build --prefix ui\n")
    if not os.getenv("OPENAI_API_KEY"):
        parser.exit(1, "Set OPENAI_API_KEY in .env before starting the server.\n")
    with ThreadingHTTPServer(("127.0.0.1", args.port), Handler) as server:
        server.client = open_client()
        print(f"http://127.0.0.1:{server.server_port}", flush=True)
        server.serve_forever()
