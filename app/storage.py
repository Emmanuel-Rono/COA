"""SQLite stores runs and internal review decisions across restarts."""
import json
import sqlite3
from contextlib import contextmanager
from uuid import uuid4
from .errors import AppError
from .spree import utc_now


class Storage:
    def __init__(self, path):
        self.path = path
        with self.connect() as db:
            db.execute("CREATE TABLE IF NOT EXISTS records (id TEXT PRIMARY KEY, store_id TEXT, body TEXT)")
            db.execute("CREATE TABLE IF NOT EXISTS audit (id INTEGER PRIMARY KEY, record_id TEXT, event TEXT, actor TEXT, at TEXT)")
            for row in db.execute("SELECT id, body FROM records").fetchall():
                body = json.loads(row[1])
                if body["status"] == "running":
                    body.update(status="failed", error={"code": "interrupted", "message": "Server restarted during processing; submit a new run."})
                    db.execute("UPDATE records SET body=? WHERE id=?", (json.dumps(body), row[0]))

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=15)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def create(self, store_id, mode, kind):
        body = {"id": uuid4().hex, "store_id": store_id, "source_mode": mode, "kind": kind,
                "status": "running", "version": 1, "created_at": utc_now(), "result": None, "error": None, "review": None}
        with self.connect() as db:
            db.execute("INSERT INTO records VALUES (?, ?, ?)", (body["id"], store_id, json.dumps(body)))
            db.execute("INSERT INTO audit(record_id,event,actor,at) VALUES (?,?,?,?)", (body["id"], "created", "demo-staff", utc_now()))
        return body

    def save(self, body):
        with self.connect() as db:
            db.execute("UPDATE records SET body=? WHERE id=? AND store_id=?", (json.dumps(body), body["id"], body["store_id"]))
        return body

    def get(self, record_id, store_id):
        with self.connect() as db:
            row = db.execute("SELECT body FROM records WHERE id=? AND store_id=?", (record_id, store_id)).fetchone()
        if not row:
            raise AppError("record_not_found", "No report found for this store.", 404)
        return json.loads(row[0])

    def recent(self, store_id):
        with self.connect() as db:
            rows = db.execute("SELECT body FROM records WHERE store_id=? ORDER BY rowid DESC LIMIT 20", (store_id,)).fetchall()
        return [json.loads(row[0]) for row in rows]

    def review(self, record_id, store_id, decision, note, version):
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT body FROM records WHERE id=? AND store_id=?", (record_id, store_id)).fetchone()
            if not row:
                raise AppError("record_not_found", "Report not found.", 404)
            body = json.loads(row[0])
            if body["review"]:
                if body["review"]["decision"] == decision and body["review"]["note"] == note and version == body["review"]["report_version"]:
                    return body
                raise AppError("review_conflict", "This report has already been reviewed.", 409)
            if body["version"] != version or body["status"] != "needs_review":
                raise AppError("review_conflict", "Only the current finished report can be reviewed.", 409)
            body["review"] = {"decision": decision, "note": note, "reviewer": "demo-staff", "at": utc_now(), "report_version": version}
            body["status"] = "approved" if decision == "approve" else "rejected"
            body["version"] += 1
            db.execute("UPDATE records SET body=? WHERE id=?", (json.dumps(body), record_id))
            db.execute("INSERT INTO audit(record_id,event,actor,at) VALUES (?,?,?,?)", (record_id, decision, "demo-staff", utc_now()))
        return body
