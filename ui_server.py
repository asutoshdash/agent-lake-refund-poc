"""Serve the React refund console on loopback using the existing agent."""
import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path

from langsmith import tracing_context
from run_store import RunStore

from dotenv import load_dotenv
from experiments import classify, score
from agent import conversation, open_client, scenario_turns

ROOT = Path(__file__).resolve().parent
ASSETS = {"/": ("ui/index.html", "text/html; charset=utf-8"),
          "/app.js": ("ui/dist/app.js", "text/javascript"),
          "/style.css": ("ui/style.css", "text/css")}


def run_query(case, question, evaluate, complete, model, record):
    turns = scenario_turns(case, question)
    for number, turn in enumerate(turns, start=1):
        record(number, {"stage": "Prepared fixture", "data": {
            "refund_id": turn["refund_id"], "as_of": turn["at"], "snapshot": turn["snapshot"]}})
    outputs = conversation(turns, complete=complete, model=model, record=record)
    rows = [dict(question=t["question"], refund_id=t["refund_id"], **result)
                    for t, result in zip(turns, outputs, strict=True)]
    if evaluate:
        for number, (turn, row) in enumerate(zip(turns, rows, strict=True), start=1):
            try:
                def judge(reply):
                    return classify(reply, complete, os.getenv("JUDGE_MODEL", model))
                metrics = score([turn], [row], judge)
                verdict = "Passed" if metrics[-1]["score"] else "Failed"
                row["trace"].append({"stage": "Reply evaluation", "data": {
                    "verdict": verdict, "supporting_quote": metrics[0]["comment"],
                    "scores": {m["key"].removeprefix("turn_1_"): m["score"] for m in metrics[:-1]}}})
            except Exception:
                row["trace"].append({"stage": "Evaluation unavailable",
                                     "data": "The judge could not score this reply."})
            record(number, row["trace"][-1])
    return rows


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
        if self.path == "/api/runs" or self.path.startswith("/api/runs/"):
            if self.headers.get("Host") != f"127.0.0.1:{self.server.server_port}":
                return self.send_error(403)
            if self.path == "/api/runs":
                return self.json(200, {"runs": self.server.store.recent()})
            run = self.server.store.read(self.path.removeprefix("/api/runs/"))
            return self.json(200, run) if run else self.json(404, {"error": "Run not found."})
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
            evaluate = body.get("evaluate", False)
            if not isinstance(evaluate, bool):
                raise ValueError()
            question = body["question"].strip()
            if not 0 < len(question) <= 1200:
                raise ValueError()
            if body.get("case") not in ("pending", "settled", "failed", "timeout", "missing", "followup"):
                raise ValueError()
        except (ValueError, KeyError, TypeError):
            return self.json(400, {"error": "Choose a scenario and enter a question up to 1,200 characters."})
        store = self.server.store
        run_id = store.start(question, body["case"])
        try:
            with tracing_context(enabled=False):
                rows = run_query(body["case"], question, evaluate, self.server.client.chat.completions.create,
                                 os.getenv("OPENAI_MODEL", "gpt-4.1-mini"),
                                 lambda turn, event: store.append(run_id, turn, event))
        except Exception:
            store.finish(run_id, "Failed")
            return self.json(502, {"error": "The agent could not finish. Open the partial trace in Saved runs.",
                                   "run_id": run_id})
        store.finish(run_id, "Complete")
        self.json(200, {"turns": rows, "run_id": run_id})


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
        server.store = RunStore(ROOT / "refund-runs.sqlite3")
        print(f"http://127.0.0.1:{server.server_port}", flush=True)
        server.serve_forever()
