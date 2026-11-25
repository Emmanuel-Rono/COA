"""Local RAG: page chunks + real embeddings, stored in SQLite for a small corpus."""
import hashlib
import json
import math
from pathlib import Path
from .documents import read_document
from .errors import AppError


def cosine(a, b):
    if len(a) != len(b):
        raise AppError("index_model_changed", "Embedding dimensions changed. Re-index the policies.")
    denominator = math.sqrt(sum(x*x for x in a) * sum(x*x for x in b))
    return sum(x*y for x, y in zip(a, b)) / denominator if denominator else 0


class Knowledge:
    def __init__(self, storage, model, settings):
        self.storage, self.model, self.settings = storage, model, settings
        with storage.connect() as db:
            db.execute("CREATE TABLE IF NOT EXISTS policies (id TEXT PRIMARY KEY, store_id TEXT, title TEXT, hash TEXT, version INTEGER, active INTEGER, model TEXT, pages TEXT)")
            db.execute("CREATE TABLE IF NOT EXISTS chunks (id TEXT PRIMARY KEY, policy_id TEXT, page INTEGER, text TEXT, vector TEXT)")

    def ingest(self, title, content, filename):
        parsed = read_document(filename, content)
        policy_id = hashlib.sha256((self.settings.store_id + ':' + title).encode()).hexdigest()[:24]
        with self.storage.connect() as db:
            old = db.execute("SELECT * FROM policies WHERE id=?", (policy_id,)).fetchone()
        if old and old['hash'] == parsed['hash'] and old['active'] and old['model'] == self.settings.embedding_model:
            return {"id": policy_id, "version": old['version'], "duplicate": True}
        version = old['version'] + 1 if old else 1
        chunks = []
        for page in parsed['pages']:
            words = page['text'].split()
            for start in range(0, len(words), 240):
                chunks.append({"page": page['page'], "text": ' '.join(words[start:start+300])})
        vectors = self.model.embed([chunk['text'] for chunk in chunks])
        with self.storage.connect() as db:
            db.execute("DELETE FROM chunks WHERE policy_id=?", (policy_id,))
            db.execute("INSERT OR REPLACE INTO policies VALUES (?,?,?,?,?,?,?,?)",
                       (policy_id, self.settings.store_id, title, parsed['hash'], version, 1,
                        self.settings.embedding_model, json.dumps(parsed['pages'])))
            for i, (chunk, vector) in enumerate(zip(chunks, vectors)):
                db.execute("INSERT INTO chunks VALUES (?,?,?,?,?)", (f'{policy_id}:v{version}:c{i}', policy_id,
                           chunk['page'], chunk['text'], json.dumps(vector)))
        return {"id": policy_id, "version": version, "duplicate": False}

    def list(self):
        with self.storage.connect() as db:
            rows = db.execute("SELECT id,title,version,model FROM policies WHERE store_id=? AND active=1",
                              (self.settings.store_id,)).fetchall()
        return [dict(row) for row in rows]

    def delete(self, policy_id):
        with self.storage.connect() as db:
            row = db.execute("SELECT id FROM policies WHERE id=? AND store_id=?", (policy_id, self.settings.store_id)).fetchone()
            if not row:
                raise AppError("policy_not_found", "No policy found for this store.", 404)
            db.execute("UPDATE policies SET active=0 WHERE id=?", (policy_id,))
            db.execute("DELETE FROM chunks WHERE policy_id=?", (policy_id,))

    def search(self, query):
        with self.storage.connect() as db:
            rows = db.execute("SELECT c.*,p.title,p.version,p.model FROM chunks c JOIN policies p ON c.policy_id=p.id WHERE p.active=1 AND p.store_id=?",
                              (self.settings.store_id,)).fetchall()
        if not rows:
            return []
        if any(row['model'] != self.settings.embedding_model for row in rows):
            raise AppError("index_model_changed", "Configured embedding model differs from the index. Re-upload policies.")
        vector = self.model.embed([query], query=True)[0]
        results = [{"id": row['id'], "document_id": row['policy_id'], "title": row['title'],
                    "version": row['version'], "page": row['page'], "text": row['text'],
                    "score": round(cosine(vector, json.loads(row['vector'])), 4), "source_type": "policy"}
                   for row in rows]
        return sorted((item for item in results if item['score'] >= 0.35), key=lambda item: item['score'], reverse=True)[:5]
