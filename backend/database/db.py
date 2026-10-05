"""SQLite persistence for DIGITAL CRIME SCENE AI.

Every table is declared in TABLES. Columns typed JSON are stored as TEXT and
transparently encoded/decoded, so the rest of the code works with plain
Python dicts and lists.
"""
import json
import os
import sqlite3
from contextlib import contextmanager

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
DATA_DIR = os.path.join(ROOT, "data")
DB_PATH = os.environ.get("DCS_DB", os.path.join(DATA_DIR, "digital_crime_scene.db"))

# name -> list of (column, type). "JSON" columns hold encoded Python objects.
TABLES = {
    "cases": [("id", "TEXT PRIMARY KEY"), ("seed", "TEXT"), ("difficulty", "TEXT"),
              ("incident_type", "TEXT"), ("title", "TEXT"), ("case_number", "INTEGER"),
              ("company", "TEXT"), ("summary", "TEXT"), ("severity", "TEXT"),
              ("incident_time", "TEXT"), ("alert_minute", "INTEGER"), ("location_ref", "TEXT"),
              ("status", "TEXT"), ("created_at", "TEXT"), ("data", "JSON")],
    "suspects": [("case_id", "TEXT"), ("ref", "TEXT"), ("name", "TEXT"), ("role", "TEXT"),
                 ("age", "INTEGER"), ("access_level", "TEXT"), ("email", "TEXT"), ("bio", "TEXT"),
                 ("alibi", "TEXT"), ("extra", "JSON")],
    "victims": [("case_id", "TEXT"), ("ref", "TEXT"), ("name", "TEXT"), ("role", "TEXT"),
                ("age", "INTEGER"), ("access_level", "TEXT"), ("email", "TEXT"), ("bio", "TEXT"),
                ("alibi", "TEXT"), ("extra", "JSON")],
    "witnesses": [("case_id", "TEXT"), ("ref", "TEXT"), ("name", "TEXT"), ("role", "TEXT"),
                  ("age", "INTEGER"), ("access_level", "TEXT"), ("email", "TEXT"), ("bio", "TEXT"),
                  ("alibi", "TEXT"), ("extra", "JSON")],
    "devices": [("case_id", "TEXT"), ("ref", "TEXT"), ("name", "TEXT"), ("kind", "TEXT"),
                ("owner_ref", "TEXT"), ("location_ref", "TEXT"), ("extra", "JSON")],
    "locations": [("case_id", "TEXT"), ("ref", "TEXT"), ("name", "TEXT"), ("building", "TEXT"),
                  ("extra", "JSON")],
    "emails": [("case_id", "TEXT"), ("ref", "TEXT"), ("evidence_id", "TEXT"), ("sender", "TEXT"),
               ("recipients", "JSON"), ("cc", "JSON"), ("subject", "TEXT"), ("ts", "TEXT"),
               ("minute", "INTEGER"), ("body", "TEXT"), ("attachments", "JSON"), ("extra", "JSON")],
    "messages": [("case_id", "TEXT"), ("ref", "TEXT"), ("evidence_id", "TEXT"), ("a", "TEXT"),
                 ("b", "TEXT"), ("ts", "TEXT"), ("minute", "INTEGER"), ("lines", "JSON"),
                 ("extra", "JSON")],
    "files": [("case_id", "TEXT"), ("ref", "TEXT"), ("evidence_id", "TEXT"), ("filename", "TEXT"),
              ("created", "INTEGER"), ("modified", "INTEGER"), ("owner_ref", "TEXT"),
              ("size", "TEXT"), ("location_ref", "TEXT"), ("device_ref", "TEXT"), ("hash", "TEXT"),
              ("access_history", "JSON"), ("extra", "JSON")],
    "images": [("case_id", "TEXT"), ("ref", "TEXT"), ("evidence_id", "TEXT"), ("ts", "TEXT"),
               ("minute", "INTEGER"), ("location_ref", "TEXT"), ("device_ref", "TEXT"),
               ("caption", "TEXT"), ("metadata", "JSON"), ("extra", "JSON")],
    "events": [("case_id", "TEXT"), ("ref", "TEXT"), ("evidence_id", "TEXT"), ("minute", "INTEGER"),
               ("ts", "TEXT"), ("type", "TEXT"), ("actor_ref", "TEXT"), ("device_ref", "TEXT"),
               ("location_ref", "TEXT"), ("description", "TEXT"), ("data", "JSON")],
    "relationships": [("case_id", "TEXT"), ("ref", "TEXT"), ("src", "TEXT"), ("dst", "TEXT"),
                      ("type", "TEXT"), ("minute", "INTEGER"), ("evidence_id", "TEXT"),
                      ("label", "TEXT")],
    "evidence": [("case_id", "TEXT"), ("id", "TEXT"), ("type", "TEXT"), ("title", "TEXT"),
                 ("minute", "INTEGER"), ("ts", "TEXT"), ("reliability", "TEXT"),
                 ("discovered", "INTEGER"), ("source_ref", "TEXT"), ("entities", "JSON"),
                 ("summary", "TEXT"), ("depth", "INTEGER"), ("data", "JSON")],
    "hypotheses": [("case_id", "TEXT"), ("id", "INTEGER"), ("title", "TEXT"),
                   ("suspect_ref", "TEXT"), ("kind", "TEXT"), ("notes", "TEXT"),
                   ("support", "JSON"), ("against", "JSON"), ("created_at", "TEXT")],
    "investigations": [("case_id", "TEXT PRIMARY KEY"), ("started_at", "TEXT"), ("elapsed", "INTEGER"),
                       ("state", "JSON"), ("accusation", "JSON"), ("result", "JSON"),
                       ("status", "TEXT")],
    "case_truth": [("case_id", "TEXT PRIMARY KEY"), ("data", "JSON")],
    "ai_queries": [("case_id", "TEXT"), ("id", "INTEGER"), ("ts", "TEXT"), ("question", "TEXT"),
                   ("answer", "TEXT"), ("evidence", "JSON"), ("mode", "TEXT")],
    "timeline_events": [("case_id", "TEXT"), ("ref", "TEXT"), ("minute", "INTEGER"), ("ts", "TEXT"),
                        ("label", "TEXT"), ("kind", "TEXT"), ("type", "TEXT"), ("actors", "JSON"),
                        ("device_ref", "TEXT"), ("location_ref", "TEXT"), ("evidence_id", "TEXT")],
    "feed": [("case_id", "TEXT"), ("id", "INTEGER"), ("ts", "TEXT"), ("kind", "TEXT"),
             ("text", "TEXT"), ("evidence_id", "TEXT")],
    "achievements": [("key", "TEXT PRIMARY KEY"), ("unlocked_at", "TEXT"), ("progress", "JSON")],
}

# Tables that make up one case (for export/import/delete). Order matters for import.
CASE_TABLES = ["suspects", "victims", "witnesses", "devices", "locations", "emails", "messages",
               "files", "images", "events", "relationships", "evidence", "timeline_events",
               "case_truth"]

JSON_COLS = {t: {c for c, ty in cols if ty == "JSON"} for t, cols in TABLES.items()}


def _coltype(ty):
    return "TEXT" if ty == "JSON" else ty


def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    with connect() as c:
        for name, cols in TABLES.items():
            ddl = ", ".join(f"{col} {_coltype(ty)}" for col, ty in cols)
            c.execute(f"CREATE TABLE IF NOT EXISTS {name} ({ddl})")
        for t in CASE_TABLES + ["hypotheses", "ai_queries", "feed"]:
            if t != "case_truth":
                c.execute(f"CREATE INDEX IF NOT EXISTS idx_{t}_case ON {t}(case_id)")


@contextmanager
def connect():
    conn = sqlite3.connect(DB_PATH, timeout=15)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def _dec(table, row):
    if row is None:
        return None
    d = dict(row)
    for col in JSON_COLS.get(table, ()):
        if col in d and isinstance(d[col], str):
            try:
                d[col] = json.loads(d[col])
            except ValueError:
                pass
    return d


def _enc(table, col, val):
    if col in JSON_COLS.get(table, ()) and not isinstance(val, str):
        return json.dumps(val, ensure_ascii=False)
    if col in JSON_COLS.get(table, ()) and isinstance(val, str):
        return json.dumps(val, ensure_ascii=False)
    return val


def insert_rows(conn, table, rows):
    """Insert dict rows; unknown keys are ignored, missing keys become NULL."""
    cols = [c for c, _ in TABLES[table]]
    sql = f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({', '.join('?' for _ in cols)})"
    conn.executemany(sql, [[_enc(table, c, r.get(c)) for c in cols] for r in rows])


def select(table, where="", args=(), order=""):
    with connect() as c:
        sql = f"SELECT * FROM {table}"
        if where:
            sql += f" WHERE {where}"
        if order:
            sql += f" ORDER BY {order}"
        return [_dec(table, r) for r in c.execute(sql, args).fetchall()]


def one(table, where, args=()):
    rows = select(table, where, args)
    return rows[0] if rows else None


def execute(sql, args=()):
    with connect() as c:
        cur = c.execute(sql, args)
        return cur.lastrowid


def update(table, where, args, **vals):
    sets = ", ".join(f"{k}=?" for k in vals)
    params = [_enc(table, k, v) for k, v in vals.items()] + list(args)
    with connect() as c:
        c.execute(f"UPDATE {table} SET {sets} WHERE {where}", params)


def delete_case(case_id):
    with connect() as c:
        for t in CASE_TABLES + ["hypotheses", "ai_queries", "feed"]:
            if t == "case_truth":
                c.execute("DELETE FROM case_truth WHERE case_id=?", (case_id,))
            else:
                c.execute(f"DELETE FROM {t} WHERE case_id=?", (case_id,))
        c.execute("DELETE FROM investigations WHERE case_id=?", (case_id,))
        c.execute("DELETE FROM cases WHERE id=?", (case_id,))


def load_bundle(case_id, include_truth=False):
    """Return the whole case as plain python structures (the shape the analysts consume)."""
    case = one("cases", "id=?", (case_id,))
    if not case:
        return None
    b = {"case": case}
    for t in ["suspects", "victims", "witnesses", "devices", "locations", "emails", "messages",
              "files", "images", "events", "relationships", "evidence", "timeline_events"]:
        order = "minute" if t in ("events", "timeline_events") else ""
        b[t] = select(t, "case_id=?", (case_id,), order)
    for e in b["evidence"]:
        e["discovered"] = bool(e["discovered"])
    if include_truth:
        row = one("case_truth", "case_id=?", (case_id,))
        b["truth"] = row["data"] if row else None
    return b


def dump_case(case_id):
    """Everything needed to recreate a case + the player's progress, as one JSON-able dict."""
    out = {"format": "digital-crime-scene-case", "version": 1}
    out["cases"] = select("cases", "id=?", (case_id,))
    for t in CASE_TABLES:
        out[t] = select(t, "case_id=?", (case_id,))
    for t in ["hypotheses", "feed", "ai_queries", "investigations"]:
        out[t] = select(t, "case_id=?", (case_id,))
    return out


def restore_case(dump):
    if dump.get("format") != "digital-crime-scene-case" or not dump.get("cases"):
        raise ValueError("Not a Digital Crime Scene case file")
    case_id = dump["cases"][0]["id"]
    delete_case(case_id)
    with connect() as c:
        insert_rows(c, "cases", dump["cases"])
        for t in CASE_TABLES + ["hypotheses", "feed", "ai_queries", "investigations"]:
            if dump.get(t):
                insert_rows(c, t, dump[t])
    return case_id
