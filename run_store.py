"""SQLite history for a local refund console."""
from contextlib import closing
import json
import sqlite3
from uuid import uuid4


class RunStore:
    def __init__(self, path):
        self.path = path
        with closing(self.connect()) as db, db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS runs (
                    id TEXT PRIMARY KEY, question TEXT NOT NULL, scenario TEXT NOT NULL,
                    at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
                    status TEXT NOT NULL DEFAULT 'Running'
                );
                CREATE TABLE IF NOT EXISTS events (
                    seq INTEGER PRIMARY KEY, run_id TEXT NOT NULL REFERENCES runs(id),
                    turn INTEGER NOT NULL, stage TEXT NOT NULL, data TEXT NOT NULL,
                    at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
                );
                CREATE INDEX IF NOT EXISTS events_by_run ON events(run_id, seq);
            """)
            # The loopback console owns this database for the lifetime of its server.
            db.execute("UPDATE runs SET status='Interrupted' WHERE status='Running'")

    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        return db

    def start(self, question, scenario):
        run_id = str(uuid4())
        with closing(self.connect()) as db, db:
            db.execute("INSERT INTO runs(id,question,scenario) VALUES (?,?,?)", (run_id, question, scenario))
        return run_id

    def append(self, run_id, turn, event):
        with closing(self.connect()) as db, db:
            db.execute("INSERT INTO events(run_id,turn,stage,data) VALUES (?,?,?,?)",
                       (run_id, turn, event["stage"], json.dumps(event["data"])))

    def finish(self, run_id, status):
        with closing(self.connect()) as db, db:
            db.execute("UPDATE runs SET status=? WHERE id=?", (status, run_id))

    def recent(self):
        with closing(self.connect()) as db:
            return [dict(row) for row in db.execute("SELECT * FROM runs ORDER BY rowid DESC LIMIT 20")]

    def read(self, run_id):
        with closing(self.connect()) as db, db:
            db.execute("BEGIN")
            run = db.execute("SELECT * FROM runs WHERE id=?", (run_id,)).fetchone()
            if run is None:
                return None
            events = db.execute("SELECT turn,stage,data,at FROM events WHERE run_id=? ORDER BY seq", (run_id,))
            return {**dict(run), "events": [{**dict(e), "data": json.loads(e["data"])} for e in events]}
