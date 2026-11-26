"""Serve the React refund console on loopback using the existing agent."""
import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path

from uuid import uuid4
from langsmith import Client, traceable, tracing_context
from langsmith.utils import LangSmithNotFoundError

from dotenv import load_dotenv
from experiments import classify, score
from agent import conversation, open_client, scenario_turns

ROOT = Path(__file__).resolve().parent
ASSETS = {"/": ("ui/index.html", "text/html; charset=utf-8"),
          "/app.js": ("ui/dist/app.js", "text/javascript"),
          "/style.css": ("ui/style.css", "text/css")}


@traceable(name="prepare_refund_scenario")
def prepare(case, question):
    return scenario_turns(case, question)


@traceable(name="refund_console_query", process_inputs=lambda inputs: {
    key: inputs[key] for key in ("case", "question", "evaluate", "model")})
def run_query(case, question, evaluate, complete, model):
    turns = prepare(case, question)
    outputs = conversation(turns, complete=complete, model=model)
    rows = [dict(question=t["question"], refund_id=t["refund_id"], **result)
                    for t, result in zip(turns, outputs, strict=True)]
    if evaluate:
        for turn, row in zip(turns, rows, strict=True):
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
        if self.path == "/api/runs":
            if self.headers.get("Host") != f"127.0.0.1:{self.server.server_port}":
                return self.send_error(403)
            store = self.server.store
            if store is None:
                return self.json(200, {"enabled": False, "runs": []})
            try:
                runs = store.list_runs(project_name=self.server.project, is_root=True,
                                       filter='eq(name, "refund_console_query")', limit=20)
                items = [{"id": str(r.id), "question": r.inputs.get("question", "Refund query"),
                          "at": r.start_time.isoformat(), "url": store.get_run_url(run=r),
                          "status": "Failed" if r.error else "Complete" if r.end_time else "Running"}
                         for r in runs]
            except LangSmithNotFoundError:
                items = []
            except Exception:
                return self.json(502, {"error": "Cannot read LangSmith history. Check the endpoint, key and project."})
            return self.json(200, {"enabled": True, "runs": items})
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
        run_id = uuid4()
        with tracing_context(enabled=store is not None, client=store, project_name=self.server.project):
            try:
                rows = run_query(body["case"], question, evaluate, self.server.client.chat.completions.create,
                                 os.getenv("OPENAI_MODEL", "gpt-4.1-mini"),
                                 langsmith_extra={"run_id": run_id})
            except Exception:
                return self.json(502, {"error": "The agent could not complete the lookup.",
                                       "run_id": str(run_id) if store else None})
        payload = {"turns": rows}
        if store:
            payload["run_id"] = str(run_id)
            try:
                saved = store.read_run(run_id)
                if saved.end_time is None:
                    raise ValueError("Run completion not yet visible")
                payload["url"] = store.get_run_url(run=saved)
            except Exception:
                payload["storage_warning"] = "LangSmith persistence is unconfirmed. Refresh saved runs to check."
        self.json(200, payload)



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
        server.project = os.getenv("LANGSMITH_PROJECT") or "refund-agent-lake"
        key = os.getenv("LANGSMITH_API_KEY") or os.getenv("LANGCHAIN_API_KEY")
        enabled = os.getenv("LANGSMITH_TRACING", "true" if key else "false").lower() == "true"
        if enabled and not key:
            parser.exit(1, "Add LANGSMITH_API_KEY to .env to enable persistent tracing.\n")
        server.store = Client(api_key=key, auto_batch_tracing=False) if enabled else None
        print(f"http://127.0.0.1:{server.server_port}", flush=True)
        server.serve_forever()
