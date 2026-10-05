"""Service layer. main.py is a thin HTTP wrapper around these functions.

Hard rule: nothing returned to the player may contain the hidden ground truth until the
case is closed (accusation submitted) or the player explicitly views the solution.
"""
import json
import os
import re
from datetime import datetime

from .database import db
from .database.db import ROOT
from .agents.common import View, fmt, parse_hhmm, ACTION_TYPES, EVENT_LABELS, REL_W
from .agents import evidence_analyst as ea, hypothesis_analyst as ha, timeline_analyst as tl
from .agents import relationship_analyst as ra
from .case_generator import generator as gen
from .case_generator.content import DIFF, INCIDENTS, METHODS, MOTIVES
from .scoring import scoring
from .rag import retriever
from .ai import nexus, ollama

CASES_DIR = os.path.join(ROOT, "cases")
REPORTS_DIR = os.path.join(ROOT, "reports")
SAVES_DIR = os.path.join(ROOT, "saves")

ACHIEVEMENTS = {
    "first_clue": ("First Clue", "Found your first piece of evidence.", "\U0001F50E"),
    "pattern_hunter": ("Pattern Hunter", "Detected 5 correlations.", "\U0001F9E0"),
    "master_investigator": ("Master Investigator", "Solved a HARD or EXPERT case.", "\U0001F575"),
    "perfect_case": ("Perfect Case", "Solved without following a red herring.", "\U0001F3AF"),
    "speed_detective": ("Speed Detective", "Solved a case in under 20 minutes.", "\u26A1"),
    "no_guessing": ("No Guessing", "Final accusation supported by evidence only.", "\U0001F9E9"),
}
SPEED_LIMIT = 20 * 60

TYPE_FILTERS = {
    "PEOPLE": {"WITNESS"}, "DEVICES": {"DEVICE_LOG"}, "FILES": {"FILE"}, "MESSAGES": {"MESSAGE"},
    "EMAILS": {"EMAIL"}, "LOCATIONS": {"ACCESS_LOG", "IMAGE"}, "EVENTS": {"DEVICE_LOG", "ACCESS_LOG", "SYSTEM", "IMAGE"},
}


class GameError(Exception):
    def __init__(self, msg, code=400):
        super().__init__(msg)
        self.code = code


def now():
    return datetime.now().isoformat(timespec="seconds")


def clock():
    return datetime.now().strftime("%H:%M:%S")


def next_id(table, case_id):
    rows = db.select(table, "case_id=?", (case_id,))
    return max([r["id"] or 0 for r in rows], default=0) + 1


def init():
    db.init_db()
    for d in (CASES_DIR, REPORTS_DIR, SAVES_DIR):
        os.makedirs(d, exist_ok=True)


# ------------------------------------------------------------------ helpers
def bundle(case_id, truth=False):
    b = db.load_bundle(case_id, include_truth=truth)
    if not b:
        raise GameError("Case not found", 404)
    return b


def inv(case_id):
    row = db.one("investigations", "case_id=?", (case_id,))
    if not row:
        raise GameError("Investigation not found", 404)
    row["state"] = row["state"] or {}
    return row


def save_state(case_id, state):
    db.update("investigations", "case_id=?", (case_id,), state=state)


def feed(case_id, kind, text, evidence_id=None):
    db.execute("INSERT INTO feed (case_id, id, ts, kind, text, evidence_id) VALUES (?,?,?,?,?,?)",
               (case_id, next_id("feed", case_id), clock(), kind, text, evidence_id))


def closed(case_id):
    return inv(case_id)["status"] in ("CLOSED", "REVEALED")


def unlock(key, progress=None):
    row = db.one("achievements", "key=?", (key,))
    if row and row["unlocked_at"]:
        return False
    if row:
        db.update("achievements", "key=?", (key,), unlocked_at=now(), progress=progress or row["progress"])
    else:
        with db.connect() as c:
            db.insert_rows(c, "achievements", [{"key": key, "unlocked_at": now(), "progress": progress}])
    return True


def achievements():
    rows = {r["key"]: r for r in db.select("achievements")}
    out = []
    for k, (name, desc, icon) in ACHIEVEMENTS.items():
        r = rows.get(k)
        prog = None
        if k == "pattern_hunter":
            p = db.one("achievements", "key=?", ("_corr_ids",))
            prog = len((p["progress"] or {}).get("ids", [])) if p else 0
        out.append({"key": k, "name": name, "description": desc, "icon": icon,
                    "unlocked": bool(r and r["unlocked_at"]), "progress": prog})
    return out


def _corr_total(new_ids):
    row = db.one("achievements", "key=?", ("_corr_ids",))
    ids = set((row["progress"] or {}).get("ids", [])) if row else set()
    before = len(ids)
    ids |= set(new_ids)
    if row:
        db.update("achievements", "key=?", ("_corr_ids",), progress={"ids": sorted(ids)})
    else:
        with db.connect() as c:
            db.insert_rows(c, "achievements", [{"key": "_corr_ids", "unlocked_at": None, "progress": {"ids": sorted(ids)}}])
    return len(ids), before


# ------------------------------------------------------------------ case lifecycle
def create_case(difficulty="MEDIUM", ctype="RANDOM", seed=None):
    b = gen.generate_case(seed, difficulty, ctype)
    c = b["case"]
    cid = c["id"]
    db.delete_case(cid)
    with db.connect() as conn:
        db.insert_rows(conn, "cases", [c])
        for t in ("suspects", "victims", "witnesses", "devices", "locations", "emails", "messages", "files", "images",
                  "events", "relationships", "evidence", "timeline_events"):
            db.insert_rows(conn, t, [dict(r, case_id=cid) for r in b[t]])
        db.insert_rows(conn, "case_truth", [{"case_id": cid, "data": b["truth"]}])
        db.insert_rows(conn, "investigations", [{"case_id": cid, "started_at": now(), "elapsed": 0,
                                                 "state": {"reviewed": [], "seen": [], "examined": []},
                                                 "status": "ACTIVE"}])
    with open(os.path.join(CASES_DIR, cid + ".json"), "w", encoding="utf-8") as f:
        json.dump({"seed": c["seed"], "difficulty": c["difficulty"], "type": c["incident_type"],
                   "title": c["title"], "note": "Regenerate with this seed + difficulty."}, f, indent=2)
    feed(cid, "system", "Case file initialised. Investigation begins.")
    feed(cid, "evidence", "Initial evidence preserved by the security team.")
    return overview(cid)


def list_cases():
    out = []
    for c in db.select("cases", order="created_at DESC"):
        i = db.one("investigations", "case_id=?", (c["id"],)) or {}
        res = i.get("result") or {}
        out.append({"id": c["id"], "seed": c["seed"], "difficulty": c["difficulty"], "title": c["title"],
                    "case_number": c["case_number"], "status": i.get("status"), "elapsed": i.get("elapsed"),
                    "grade": res.get("grade"), "total": res.get("total"), "solved": res.get("solved")})
    return out


def delete_case(case_id):
    db.delete_case(case_id)
    return {"deleted": case_id}


def retry_case(case_id):
    c = bundle(case_id)["case"]
    return create_case(c["difficulty"], c["incident_type"], c["seed"])


def heartbeat(case_id, elapsed):
    i = inv(case_id)
    if i["status"] == "ACTIVE":
        db.update("investigations", "case_id=?", (case_id,), elapsed=int(max(i["elapsed"] or 0, elapsed)))
    return {"elapsed": elapsed}


def overview(case_id):
    b = bundle(case_id)
    v = View(b)
    c = b["case"]
    i = inv(case_id)
    contr = ea.contradictions(v)
    sus = ea.suspicion(v, contr)
    lead_ref, conf, _ = ea.lead(v, sus)
    total = len(b["evidence"])
    disc = len(v.disc)
    counts = c["data"]["counts"]
    victim = b["victims"][0]
    dt = c["data"]
    return {
        "id": case_id, "seed": c["seed"], "difficulty": c["difficulty"], "case_number": c["case_number"],
        "title": c["title"], "company": c["company"], "summary": c["summary"], "severity": c["severity"],
        "incident_time": c["incident_time"], "date": dt["date"], "project": dt.get("project"),
        "location": v.name(c["location_ref"]), "status": i["status"], "elapsed": i["elapsed"] or 0,
        "evidence": {"discovered": disc, "total": total}, "confidence": conf,
        "victim": {"ref": victim["ref"], "name": victim["name"], "role": victim["role"]},
        "counts": counts, "closed": i["status"] in ("CLOSED", "REVEALED"), "case_status": c["status"],
        "suspects": [{"ref": s["ref"], "name": s["name"], "role": s["role"]} for s in b["suspects"]],
        "witnesses": [{"ref": s["ref"], "name": s["name"], "role": s["role"]} for s in b["witnesses"]],
        "devices": [{"ref": d["ref"], "name": d["name"], "kind": d["kind"]} for d in b["devices"]],
        "locations": [{"ref": l["ref"], "name": l["name"]} for l in b["locations"]],
        "opening": [
            "SYSTEM INITIALIZING...", "DIGITAL CRIME SCENE AI", f"CASE #{c['case_number']}", "INCIDENT DETECTED",
            c["title"].split(" - ")[0], "STATUS: UNSOLVED", f"EVIDENCE: {total} ITEMS", f"SUSPECTS: {counts['suspects']}",
            "NEXUS AI: ONLINE", "Investigation begins."],
    }


# ------------------------------------------------------------------ evidence
def _insights(case_id, b=None):
    """Detect new contradictions / correlations and push them to the live feed."""
    b = b or bundle(case_id)
    v = View(b)
    i = inv(case_id)
    st = i["state"]
    seen = set(st.get("seen", []))
    contr = ea.contradictions(v)
    corr = ea.correlations(v)
    new = []
    for c in contr:
        if c["id"] not in seen:
            seen.add(c["id"])
            feed(case_id, "contradiction", c["text"], c["evidence_ids"][0])
            new.append({"kind": "contradiction", "text": c["text"]})
    for c in corr:
        if c["id"] not in seen:
            seen.add(c["id"])
            feed(case_id, "correlation", f"{c['label']}: {c['text']} Confidence {c['confidence']}%.", c["evidence_ids"][0])
            new.append({"kind": "correlation", "text": c["text"]})
    st["seen"] = sorted(seen)
    save_state(case_id, st)
    total, before = _corr_total([c["id"] for c in corr])
    unlocked = []
    if total >= 5 and unlock("pattern_hunter"):
        unlocked.append("pattern_hunter")
    return new, unlocked


def evidence_row(v, e):
    return {"id": e["id"], "type": e["type"], "title": e["title"], "minute": e["minute"], "time": fmt(e["minute"]),
            "reliability": e["reliability"], "summary": e["summary"], "source_ref": e["source_ref"],
            "entities": e["entities"]}


def evidence_list(case_id, type_filter="ALL", q="", flag=""):
    b = bundle(case_id)
    v = View(b)
    st = inv(case_id)["state"]
    contr = ea.contradictions(v)
    corr = ea.correlations(v)
    sus_ids = {i for c in corr if c["label"].startswith("SUSPICIOUS") for i in c["evidence_ids"]}
    contr_ids = {i for c in contr for i in c["evidence_ids"]}
    ws, we, exact, tm = tl.window(v)
    rows = []
    reviewed = set(st.get("reviewed", []))
    for eid in sorted(v.disc):
        e = v.ev[eid]
        if type_filter and type_filter != "ALL" and e["type"] not in TYPE_FILTERS.get(type_filter, {type_filter}):
            continue
        if q:
            ql = q.strip().lower()
            if ql.upper() == eid or ql == eid.lower():
                pass
            elif ql not in retriever.evidence_text(v, e).lower():
                continue
        if flag == "HIGH" and e["reliability"] != "HIGH":
            continue
        if flag == "SUSPICIOUS" and eid not in sus_ids and not (exact and ws <= e["minute"] <= we and e["type"] in ("DEVICE_LOG", "ACCESS_LOG")):
            continue
        if flag == "CONTRADICTIONS" and eid not in contr_ids:
            continue
        if flag == "UNRESOLVED" and eid in reviewed:
            continue
        r = evidence_row(v, e)
        r["reviewed"] = eid in reviewed
        r["flags"] = [f for f, ok in (("contradiction", eid in contr_ids), ("cluster", eid in sus_ids)) if ok]
        rows.append(r)
    return {"items": rows, "discovered": len(v.disc), "total": len(b["evidence"])}


def evidence_detail(case_id, eid):
    b = bundle(case_id)
    v = View(b)
    if eid not in v.disc:
        raise GameError("Evidence not discovered", 403)
    e = v.ev[eid]
    out = evidence_row(v, e)
    out["data"] = {k: x for k, x in (e.get("data") or {}).items() if k in ("text", "claims")}
    out["entity_names"] = [{"ref": r, "name": v.name(r)} for r in e["entities"]]
    for em in b["emails"]:
        if em["evidence_id"] == eid:
            out["email"] = {"from": f"{v.name(em['sender'])} <{_addr(b, em['sender'])}>",
                            "to": [f"{v.name(r)} <{_addr(b, r)}>" for r in em["recipients"]],
                            "cc": em["cc"], "subject": em["subject"], "time": em["ts"], "body": em["body"],
                            "attachments": em["attachments"], "ref": em["ref"],
                            "origin": v.name((em.get("extra") or {}).get("origin_device")) if str((em.get("extra") or {}).get("origin_device") or "").startswith("D-") else (em.get("extra") or {}).get("origin_device")}
    for m in b["messages"]:
        if m["evidence_id"] == eid:
            out["message"] = {"ref": m["ref"], "a": m["extra"]["a_name"], "b": m["extra"]["b_name"],
                              "lines": [dict(l, time=fmt(l["minute"])) for l in m["lines"]], "label": m["extra"]["label"]}
    for f in b["files"]:
        if f["evidence_id"] == eid:
            out["file"] = _file_view(v, b, f)
    for im in b["images"]:
        if im["evidence_id"] == eid:
            out["image"] = {"ref": im["ref"], "time": im["ts"], "location": v.name(im["location_ref"]),
                            "device": v.name(im["device_ref"]), "caption": im["caption"], "metadata": im["metadata"],
                            "scene": (im["extra"] or {}).get("scene"), "seed": b["case"]["seed"]}
    evs = [x for x in v.events if x["evidence_id"] == eid]
    if evs:
        out["events"] = [{"ref": x["ref"], "time": fmt(x["minute"]), "type": x["type"], "label": EVENT_LABELS.get(x["type"], x["type"]),
                          "description": x["description"], "actor": v.name(x["actor_ref"]) if x["actor_ref"] else "shared / system",
                          "device": v.name(x["device_ref"]) if x["device_ref"] else None,
                          "location": v.name(x["location_ref"]) if x["location_ref"] else None} for x in evs]
    contr = [c for c in ea.contradictions(v) if eid in c["evidence_ids"]]
    out["contradictions"] = [{"severity": c["severity"], "text": c["text"], "evidence_ids": c["evidence_ids"]} for c in contr]
    out["related"] = [{"id": c["id"], "kind": c["kind"], "label": c["label"], "confidence": c["confidence"]}
                      for c in ea.correlations(v) if eid in c["evidence_ids"]]
    out["reliability_note"] = {
        "HIGH": "System-generated record. Highly dependable unless the system itself is compromised.",
        "MEDIUM": "Human statement or unverified-content record. Cross-check it against system logs.",
        "LOW": "Anonymous or uncorroborated source. Do not rely on it alone.",
        "QUESTIONABLE": "Unverified or degraded source. Treat as a lead, not as proof."}[e["reliability"]]
    st = inv(case_id)["state"]
    if eid not in st.get("reviewed", []):
        st.setdefault("reviewed", []).append(eid)
        save_state(case_id, st)
    return out


def _addr(b, ref):
    for p in b["suspects"] + b["victims"] + b["witnesses"]:
        if p["ref"] == ref:
            return p["email"]
    return ref if "@" in str(ref) else "external"


def _file_view(v, b, f):
    hard = b["case"]["difficulty"] in ("HARD", "EXPERT")
    mod_known = any(e["type"] == "file_modify" for e in v.events)
    hist = []
    for h in f["access_history"] or []:
        row = {"time": fmt(h["minute"]), "action": h["action"], "who": h["who"], "device": v.name(h["device"]) if h["device"] else None}
        if h["evidence_id"]:
            if h["evidence_id"] in v.disc:
                ev = next((e for e in v.events if e["evidence_id"] == h["evidence_id"]), None)
                row["who"] = ("account: " + v.name(ev["actor_ref"])) if ev and ev["actor_ref"] else "shared / unattributed account"
                row["evidence_id"] = h["evidence_id"]
            else:
                row = {"time": "\u2592\u2592:\u2592\u2592", "action": "restricted entry", "who": "examine the source device",
                       "device": None, "restricted": True}
        hist.append(row)
    target = (f.get("extra") or {}).get("target")
    modified = fmt(f["modified"])
    if target and hard and not mod_known:
        modified = "\u2592\u2592:\u2592\u2592 (server clock drift, see device logs)"
    return {"ref": f["ref"], "filename": f["filename"], "created": fmt(f["created"]), "modified": modified,
            "owner": v.name(f["owner_ref"]), "size": f["size"], "location": v.name(f["location_ref"]),
            "hash": f["hash"], "history": hist, "target": bool(target),
            "authorized": [{"ref": r, "name": v.name(r)} for r in (f.get("extra") or {}).get("access_list", [])] if target else []}


def examine(case_id, ref):
    if closed(case_id):
        raise GameError("Case is closed")
    b = bundle(case_id)
    if not any(ref in [x["ref"] for x in b[k]] for k in ("suspects", "victims", "witnesses", "devices", "locations", "files")):
        raise GameError("Unknown entity", 404)
    v = View(b)
    cand = [e for e in b["evidence"] if not e["discovered"] and ref in (e["entities"] or [])]
    cand.sort(key=lambda e: (e["depth"], e["id"]))
    batch = cand[:3]
    for e in batch:
        db.execute("UPDATE evidence SET discovered=1 WHERE case_id=? AND id=?", (case_id, e["id"]))
    i = inv(case_id)
    st = i["state"]
    st.setdefault("examined", [])
    if ref not in st["examined"]:
        st["examined"].append(ref)
    save_state(case_id, st)
    name = v.name(ref)
    if batch:
        feed(case_id, "system", f"Examined {name}: {len(batch)} new item(s) recovered.")
        for e in batch:
            feed(case_id, "evidence", f"{e['summary']}", e["id"])
        if unlock("first_clue"):
            feed(case_id, "achievement", "Achievement unlocked: First Clue")
    else:
        feed(case_id, "system", f"Examined {name}: nothing further recoverable.")
    new, unl = _insights(case_id)
    remaining = len(cand) - len(batch)
    return {"ref": ref, "name": name, "new": [evidence_row(v, e) for e in batch], "remaining": remaining > 0,
            "insights": new}


def more_data(case_id, ref):
    b = bundle(case_id)
    return any(not e["discovered"] and ref in (e["entities"] or []) for e in b["evidence"])


# ------------------------------------------------------------------ views
def graph(case_id):
    b = bundle(case_id)
    v = View(b)
    g = ra.graph(v)
    examined = set(inv(case_id)["state"].get("examined", []))
    for n in g["nodes"]:
        n["examined"] = n["id"] in examined
        n["more"] = n["type"] in ("person", "device", "location", "file") and any(
            not e["discovered"] and n["id"] in (e["entities"] or []) for e in b["evidence"])
    return g


def timeline(case_id):
    b = bundle(case_id)
    v = View(b)
    contr = ea.contradictions(v)
    cids = {i for c in contr if c["severity"] != "CONTESTED" for i in c["evidence_ids"][:2]}
    rows = tl.entries(v, cids)
    for r in rows:
        r["actor_names"] = [v.name(a) for a in r["actors"]]
    ws, we, exact, tm = tl.window(v)
    return {"entries": rows, "window": {"start": ws, "end": we, "exact": exact},
            "people": [{"ref": p["ref"], "name": p["name"]} for p in b["suspects"] + b["victims"] + b["witnesses"]],
            "devices": [{"ref": d["ref"], "name": d["name"]} for d in b["devices"]],
            "types": sorted({r["type"] for r in rows})}


def analysis(case_id):
    b = bundle(case_id)
    v = View(b)
    contr = ea.contradictions(v)
    sus = ea.suspicion(v, contr)
    corr = ea.correlations(v)
    lead_ref, conf, _ = ea.lead(v, sus)
    ch = ha.chain(v, lead_ref) if lead_ref else None
    chain_ev = [i for s in (ch["steps"] if ch else []) for i in s["evidence"]]
    ws, we, exact, tm = tl.window(v)
    hints = nexus._unexamined(v, b)
    return {
        "window": {"start": ws, "end": we, "exact": exact},
        "contradictions": contr, "correlations": corr,
        "suspicion": {r: {k: s[k] for k in ("score", "opportunity", "consistency", "alibi_status")} for r, s in sus.items()},
        "lead": {"ref": lead_ref, "name": v.name(lead_ref) if lead_ref else None, "confidence": conf},
        "chain": ch,
        "strongest": [dict(s, **{"title": v.ev[s["id"]]["title"], "reliability": v.ev[s["id"]]["reliability"]})
                      for s in ea.strongest(v, contr, corr, chain_ev, 6)],
        "unexamined": [{"ref": r, "name": v.name(r)} for r in hints[:6]],
        "reliability_mix": {k: sum(1 for i in v.disc if v.ev[i]["reliability"] == k) for k in REL_W},
    }


def chain(case_id, ref):
    b = bundle(case_id)
    v = View(b)
    ch = ha.chain(v, ref)
    ch["name"] = v.name(ref)
    return ch


def people(case_id):
    b = bundle(case_id)
    v = View(b)
    contr = ea.contradictions(v)
    sus = ea.suspicion(v, contr)
    pres = tl.presence(v)
    examined = set(inv(case_id)["state"].get("examined", []))
    out = []
    for kind, rows in (("suspect", b["suspects"]), ("victim", b["victims"]), ("witness", b["witnesses"])):
        for p in rows:
            ref = p["ref"]
            card = {"ref": ref, "kind": kind, "name": p["name"], "role": p["role"], "age": p["age"],
                    "access_level": p["access_level"], "email": p["email"], "bio": p["bio"],
                    "alibi": p["alibi"], "examined": ref in examined, "more": more_data(case_id, ref) if kind != "x" else False}
            devs = [d for d in b["devices"] if d["owner_ref"] == ref]
            card["known_devices"] = len(devs)
            card["devices"] = [d["name"] for d in devs]
            pr = pres.get(ref, {})
            last = []
            if pr.get("out"):
                m = max(pr["out"])[0]
                last.append((m, f"Left the building at {fmt(m)}"))
            for m, l, eid in pr.get("rooms", []):
                last.append((m, f"{v.name(l)} at {fmt(m)}"))
            card["last_seen"] = max(last)[1] if last else "Unknown"
            if kind == "suspect":
                s = sus[ref]
                ch = ha.chain(v, ref)
                card.update(suspicion=s["score"], consistency=s["consistency"], alibi_status=s["alibi_status"],
                            opportunity=s["opportunity"], chain=ch["strength"])
                motives = [v.ev[e]["data"]["motive_label"] for e in sorted(v.disc)
                           if (v.ev[e].get("data") or {}).get("motive_for") == ref]
                card["motive"] = "; ".join(motives) if motives else "UNKNOWN"
                chk = []
                acl = (v.target_file.get("extra") or {}).get("access_list", []) if v.target_file else []
                if ref in acl:
                    chk.append({"icon": "ok", "text": "Authorized to access the target file", "evidence": [v.target_file["evidence_id"]]})
                for f in s["factors"]:
                    if f["weight"] >= 10 and f["key"] not in ("acl",):
                        chk.append({"icon": "ok", "text": f["label"], "evidence": f["evidence"]})
                for f in s["factors"]:
                    if f["weight"] < 0:
                        chk.append({"icon": "clear", "text": f["label"], "evidence": f["evidence"]})
                for c in contr:
                    if c["person"] == ref:
                        chk.append({"icon": "warn", "text": ("Alibi contradiction" if c["kind"] == "alibi" else "Statement conflict" if c["kind"] == "claim" else "Contested account activity") + f" ({c['severity'].lower()})",
                                    "evidence": c["evidence_ids"]})
                for f in s["factors"]:
                    if f["key"] in ("deleted_resolved",):
                        chk.append({"icon": "clear", "text": f["label"], "evidence": f["evidence"]})
                if ch["missing"] and s["score"] > 0:
                    chk.append({"icon": "no", "text": "No direct evidence: " + ch["missing"][0], "evidence": []})
                card["checklist"] = chk[:7]
            else:
                card["statements"] = [e for e in sorted(v.disc) if ref in v.ev[e]["entities"] and v.ev[e]["type"] == "WITNESS"]
            out.append(card)
    return out


def entity(case_id, ref):
    b = bundle(case_id)
    v = View(b)
    kind = None
    for k, key in (("person", "suspects"), ("person", "victims"), ("person", "witnesses"), ("device", "devices"),
                   ("location", "locations"), ("file", "files")):
        if any(r["ref"] == ref for r in b[key]):
            kind = k
    if ref.startswith("ORG"):
        kind = "org"
    if not kind:
        raise GameError("Unknown entity", 404)
    evs = [evidence_row(v, e) for e in v.evidence_of(ref)]
    conns = [dict(c, other_name=v.name(c["other"])) for c in ra.connected_to(v, ref)]
    out = {"ref": ref, "kind": kind, "name": v.name(ref), "evidence": evs, "connections": conns,
           "more": more_data(case_id, ref)}
    if kind == "person":
        out["profile"] = next(p for p in people(case_id) if p["ref"] == ref)
    elif kind == "device":
        d = v.devices[ref]
        out["device"] = {"kind": d["kind"], "owner": v.name(d["owner_ref"]) if d["owner_ref"] else "none (shared / system)",
                         "location": v.name(d["location_ref"]) if d["location_ref"] else "n/a",
                         "log": [{"time": fmt(e["minute"]), "description": e["description"], "evidence_id": e["evidence_id"],
                                  "actor": v.name(e["actor_ref"]) if e["actor_ref"] else "-"} for e in v.events if e["device_ref"] == ref]}
    elif kind == "location":
        pres = tl.presence(v)
        rows = []
        for p, pr in pres.items():
            for m, l, eid in pr["rooms"]:
                if l == ref:
                    rows.append({"time": fmt(m), "minute": m, "who": v.name(p), "evidence_id": eid})
            if ref == "L-01":
                for m, eid in pr["in"]:
                    rows.append({"time": fmt(m), "minute": m, "who": v.name(p) + " (entered)", "evidence_id": eid})
                for m, eid in pr["out"]:
                    rows.append({"time": fmt(m), "minute": m, "who": v.name(p) + " (left)", "evidence_id": eid})
        out["location"] = {"building": next(l["building"] for l in b["locations"] if l["ref"] == ref),
                           "people": sorted(rows, key=lambda r: r["minute"]),
                           "devices": [d["name"] for d in b["devices"] if d["location_ref"] == ref]}
    elif kind == "file":
        out["file"] = _file_view(v, b, next(f for f in b["files"] if f["ref"] == ref))
    return out


def devices(case_id):
    b = bundle(case_id)
    v = View(b)
    examined = set(inv(case_id)["state"].get("examined", []))
    rows = []
    for d in b["devices"]:
        evs = [e for e in v.events if e["device_ref"] == d["ref"]]
        last = max(evs, key=lambda e: e["minute"]) if evs else None
        conns = [e for e in evs if e["type"] in ("ext_connect", "badge_room", "camera_detect")]
        rows.append({"ref": d["ref"], "name": d["name"], "kind": d["kind"],
                     "owner": v.name(d["owner_ref"]) if d["owner_ref"] else "shared / system",
                     "location": v.name(d["location_ref"]) if d["location_ref"] else "n/a",
                     "last_activity": f"{fmt(last['minute'])} - {last['description']}" if last else "No activity recovered",
                     "connections": len([e for e in evs if e["type"] == "ext_connect"]),
                     "events": len(evs), "examined": d["ref"] in examined, "more": more_data(case_id, d["ref"])})
    return rows


def locations(case_id):
    b = bundle(case_id)
    v = View(b)
    examined = set(inv(case_id)["state"].get("examined", []))
    out = []
    for l in b["locations"]:
        e = entity(case_id, l["ref"])
        out.append({"ref": l["ref"], "name": l["name"], "building": l["building"], "examined": l["ref"] in examined,
                    "more": e["more"], "people": e["location"]["people"][-6:], "devices": e["location"]["devices"],
                    "evidence_count": len(e["evidence"])})
    return out


def feed_list(case_id, limit=60):
    rows = db.select("feed", "case_id=?", (case_id,), "id DESC")[:limit]
    return rows


# ------------------------------------------------------------------ NEXUS & hypotheses
def ask_nexus(case_id, question):
    b = bundle(case_id)
    res = nexus.answer(b, question, ollama.settings()["use_llm"])
    with db.connect() as c:
        db.insert_rows(c, "ai_queries", [{"case_id": case_id, "id": next_id("ai_queries", case_id), "ts": now(),
                                          "question": question, "answer": res["text"], "evidence": res["evidence"],
                                          "mode": res["mode"]}])
    return res


def nexus_history(case_id):
    return db.select("ai_queries", "case_id=?", (case_id,), "id")


def hypotheses(case_id):
    b = bundle(case_id)
    v = View(b)
    sus = ea.suspicion(v)
    out = []
    for h in db.select("hypotheses", "case_id=?", (case_id,), "id"):
        ev = {"support": [], "against": [], "confidence": 0}
        if h["suspect_ref"] in sus:
            ch = ha.chain(v, h["suspect_ref"])
            ev = ha.evaluate(v, h, sus, ch)
        h["analysis"] = ev
        h["suspect_name"] = v.name(h["suspect_ref"]) if h["suspect_ref"] else None
        h["pinned_support"] = h["support"] or []
        h["pinned_against"] = h["against"] or []
        out.append(h)
    return out


def add_hypothesis(case_id, title, suspect_ref, kind="who", notes=""):
    if closed(case_id):
        raise GameError("Case is closed")
    if not title.strip():
        raise GameError("Give the hypothesis a statement")
    hid = next_id("hypotheses", case_id)
    with db.connect() as c:
        db.insert_rows(c, "hypotheses", [{"case_id": case_id, "id": hid, "title": title.strip(), "suspect_ref": suspect_ref or None,
                                          "kind": kind, "notes": notes, "support": [], "against": [], "created_at": now()}])
    feed(case_id, "hypothesis", f"Hypothesis #{hid:02d} recorded: {title.strip()}")
    return hypotheses(case_id)


def pin_hypothesis(case_id, hid, evidence_id, side):
    h = db.one("hypotheses", "case_id=? AND id=?", (case_id, hid))
    if not h:
        raise GameError("Hypothesis not found", 404)
    v = View(bundle(case_id))
    if evidence_id not in v.disc:
        raise GameError("Evidence not discovered", 403)
    sup, ag = list(h["support"] or []), list(h["against"] or [])
    for l in (sup, ag):
        if evidence_id in l:
            l.remove(evidence_id)
    if side == "support":
        sup.append(evidence_id)
    elif side == "against":
        ag.append(evidence_id)
    db.update("hypotheses", "case_id=? AND id=?", (case_id, hid), support=sup, against=ag)
    return hypotheses(case_id)


def delete_hypothesis(case_id, hid):
    db.execute("DELETE FROM hypotheses WHERE case_id=? AND id=?", (case_id, hid))
    return hypotheses(case_id)


# ------------------------------------------------------------------ accusation & reveal
def _truth_public(b, truth):
    v = View(b, True)
    return {
        "perpetrator": {"ref": truth["perpetrator_ref"], "name": truth["perpetrator_name"]},
        "motive": {"key": truth["motive_key"], "label": truth["motive_label"]},
        "method": {"key": truth["method_key"], "label": truth["method_label"], "detail": truth["method_detail"]},
        "time": truth["time"], "location": truth["location_name"], "device": v.name(truth["device_ref"]),
        "stated_departure": fmt(truth["stated_departure"]), "actual_departure": fmt(truth["perp_exit"]),
        "timeline": [dict(t, time=fmt(t["minute"])) for t in truth["actual_timeline"]],
        "key_evidence": truth["key_evidence"],
        "red_herrings": [{"kind": d["kind"], "suspect": v.name(d["suspect"]), "explanation": d["explanation"],
                          "evidence": d["evidence"]} for d in truth["decoys"]],
    }


def options(case_id):
    b = bundle(case_id)
    return {"suspects": [{"ref": s["ref"], "name": s["name"]} for s in b["suspects"]],
            "motives": [{"key": k, "label": l} for k, l in MOTIVES.items()],
            "methods": [{"key": k, "label": l} for k, l in METHODS.items()]}


def accuse(case_id, payload):
    i = inv(case_id)
    if i["status"] in ("CLOSED", "REVEALED"):
        raise GameError("This case is already closed")
    b = bundle(case_id, truth=True)
    truth = b["truth"]
    acc = {"suspect_ref": payload.get("suspect_ref"), "motive_key": payload.get("motive_key"),
           "method_key": payload.get("method_key"), "time": payload.get("time", ""),
           "evidence": [e for e in payload.get("evidence", []) if re.fullmatch(r"E-\d{3}", e)],
           "explanation": (payload.get("explanation") or "").strip()}
    if not acc["suspect_ref"]:
        raise GameError("Choose who you are accusing")
    hyps = db.select("hypotheses", "case_id=?", (case_id,))
    res = scoring.score(b, truth, acc, hyps)
    st = i["state"]
    elapsed = int(payload.get("elapsed") or i["elapsed"] or 0)
    unlocked = []
    if res["solved"]:
        if b["case"]["difficulty"] in ("HARD", "EXPERT") and unlock("master_investigator"):
            unlocked.append("master_investigator")
        if not res["decoys_cited"] and res["innocent_hypotheses"] == 0 and unlock("perfect_case"):
            unlocked.append("perfect_case")
        if elapsed <= SPEED_LIMIT and unlock("speed_detective"):
            unlocked.append("speed_detective")
    cited_disc = [e for e in acc["evidence"] if any(x["id"] == e and x["discovered"] for x in b["evidence"])]
    if res["solved"] and len(cited_disc) >= 3 and len(acc["explanation"]) >= 20 and not res["decoys_cited"] \
            and any(e["reliability"] == "HIGH" for e in b["evidence"] if e["id"] in cited_disc):
        if unlock("no_guessing"):
            unlocked.append("no_guessing")
    res["achievements"] = unlocked
    res["elapsed"] = elapsed
    for k in unlocked:
        feed(case_id, "achievement", "Achievement unlocked: " + ACHIEVEMENTS[k][0])
    result = dict(res, truth=_truth_public(b, truth), accusation=acc)
    db.update("investigations", "case_id=?", (case_id,), status="CLOSED", accusation=acc, result=result, elapsed=elapsed)
    db.update("cases", "id=?", (case_id,), status="SOLVED" if res["solved"] else "UNSOLVED")
    feed(case_id, "system", "Final accusation submitted. Case closed.")
    out = reveal_payload(case_id, b)
    out["report_url"] = f"/api/case/{case_id}/report"
    return out


def reveal_payload(case_id, b=None):
    i = inv(case_id)
    b = b or bundle(case_id, truth=True)
    res = i["result"]
    if not res:
        raise GameError("No result yet")
    acc = res["accusation"]
    v = View(b, True)
    msgs = []
    t = res["truth"]
    if res["who_correct"]:
        msgs.append(f"You identified {t['perpetrator']['name']} correctly.")
    else:
        msgs.append(f"You accused {v.name(acc['suspect_ref'])}. The real perpetrator was {t['perpetrator']['name']}.")
    if res["who_correct"] and not res["method_correct"]:
        msgs.append("Your proposed method was incorrect.")
    if res["who_correct"] and not res["motive_correct"]:
        msgs.append("Your proposed motive was incorrect.")
    your = {"who": v.name(acc["suspect_ref"]), "motive": MOTIVES.get(acc["motive_key"], "not stated"),
            "method": METHODS.get(acc["method_key"], "not stated"), "time": acc["time"] or "not stated",
            "explanation": acc["explanation"], "evidence": acc["evidence"]}
    return dict(res, headline="CASE SOLVED" if res["solved"] else "CASE UNSOLVED", messages=msgs, your_theory=your)


def solution(case_id):
    i = inv(case_id)
    if i["status"] == "CLOSED":
        return reveal_payload(case_id)
    b = bundle(case_id, truth=True)
    st = i["state"]
    st["solution_viewed"] = True
    save_state(case_id, st)
    db.update("investigations", "case_id=?", (case_id,), status="REVEALED",
              result={"truth": _truth_public(b, b["truth"]), "solved": False, "grade": "-", "total": 0,
                      "categories": {}, "revealed_only": True, "accusation": {}})
    db.update("cases", "id=?", (case_id,), status="REVEALED")
    return {"truth": _truth_public(b, b["truth"]), "revealed_only": True}


# ------------------------------------------------------------------ report
def report_html(case_id):
    i = inv(case_id)
    if i["status"] not in ("CLOSED", "REVEALED"):
        raise GameError("The report is available once the case is closed", 403)
    b = bundle(case_id, truth=True)
    v = View(b)  # report shows player's findings
    va = View(b, True)
    res = i["result"] or {}
    truth = res.get("truth") or _truth_public(b, b["truth"])
    contr = ea.contradictions(v)
    sus = ea.suspicion(va)
    acc = res.get("accusation") or {}
    c = b["case"]
    esc = lambda s: (str(s or "")).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    cats = res.get("categories") or {}
    assess = _assessment(res, truth)
    rows = "".join(f"<tr><td>{esc(s['name'])}</td><td>{esc(s['role'])}</td><td>{esc(s['alibi'])}</td><td>{sus[s['ref']]['score']}%</td></tr>" for s in b["suspects"])
    tlrows = "".join(f"<tr><td>{t['time']}</td><td>{esc(t['text'])}</td><td>{t['evidence_id']}</td></tr>" for t in truth["timeline"])
    keyrows = "".join(f"<li><b>{e}</b> ({va.ev[e]['reliability']}) {esc(va.ev[e]['summary'])}</li>" for e in truth["key_evidence"] if e in va.ev)
    corows = "".join(f"<li>[{x['severity']}] {esc(x['text'])} <i>{', '.join(x['evidence_ids'])}</i></li>" for x in contr) or "<li>None detected from discovered evidence.</li>"
    chain = ha.chain(va, truth["perpetrator"]["ref"])
    chrows = "".join(f"<li>{esc(s['label'])}: {s['status']} - {esc(s['note'])}</li>" for s in chain["steps"])
    catrows = "".join(f"<tr><td>{k.replace('_', ' ').title()}</td><td>{v_}/100</td></tr>" for k, v_ in cats.items())
    hyps = "".join(f"<li>{esc(h['title'])}</li>" for h in db.select("hypotheses", "case_id=?", (case_id,))) or "<li>None recorded.</li>"
    html = f"""<!doctype html><html><head><meta charset="utf-8"><title>Case #{c['case_number']} - Investigation Report</title>
<style>body{{font-family:Georgia,serif;max-width:860px;margin:32px auto;color:#1b2430;line-height:1.5;padding:0 18px}}
h1{{font-size:26px;margin:0}}h2{{border-bottom:2px solid #1b2430;padding-bottom:4px;margin-top:28px;font-size:18px}}
table{{border-collapse:collapse;width:100%;font-size:14px}}td,th{{border:1px solid #c9d1da;padding:6px 8px;text-align:left}}
.grade{{font-size:44px;font-weight:bold}}.meta{{color:#5b6877;font-family:Segoe UI,sans-serif;font-size:13px}}
@media print{{body{{margin:0}}}}</style></head><body>
<p class="meta">DIGITAL CRIME SCENE AI - FICTIONAL CASE FILE</p>
<h1>Case #{c['case_number']}: {esc(c['title'])}</h1>
<p class="meta">Seed {c['seed']} - {c['difficulty']} - {esc(c['company'])} - {c['data']['date']} - Result: {'SOLVED' if res.get('solved') else 'UNSOLVED' if not res.get('revealed_only') else 'SOLUTION VIEWED'}</p>
<h2>Incident</h2><p>{esc(c['summary'])}</p><p><b>Victim / asset owner:</b> {esc(b['victims'][0]['name'])}, {esc(b['victims'][0]['role'])}</p>
<h2>Suspects</h2><table><tr><th>Name</th><th>Role</th><th>Statement</th><th>Final suspicion</th></tr>{rows}</table>
<h2>Actual timeline</h2><table><tr><th>Time</th><th>Event</th><th>Evidence</th></tr>{tlrows}</table>
<h2>Key evidence</h2><ul>{keyrows}</ul>
<h2>Contradictions you surfaced</h2><ul>{corows}</ul>
<h2>Evidence chain (actual perpetrator)</h2><p>Strength {chain['strength']}%</p><ul>{chrows}</ul>
<h2>Your hypotheses</h2><ul>{hyps}</ul>
<h2>Your accusation</h2><p>{esc(acc.get('explanation') or 'No accusation submitted.')}</p>
<h2>Actual solution</h2><p><b>{esc(truth['perpetrator']['name'])}</b> - motive: {esc(truth['motive']['label'])}. Method: {esc(truth['method']['detail'])} At {truth['time']} in {esc(truth['location'])}.</p>
<ul>{''.join(f"<li><b>{esc(r['suspect'])}</b>: {esc(r['explanation'])}</li>" for r in truth['red_herrings'])}</ul>
<h2>Investigation score</h2><p class="grade">{res.get('grade', '-')} <span style="font-size:20px">{res.get('total', 0)}%</span></p><table>{catrows}</table>
<h2>AI assessment</h2><p>{esc(assess)}</p></body></html>"""
    path = os.path.join(REPORTS_DIR, f"report_{case_id}.html")
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)
    return html


def _assessment(res, truth):
    base = (f"Grade {res.get('grade', '-')} ({res.get('total', 0)}%). "
            + ("The accusation identified the right person. " if res.get("who_correct") else "The accusation named the wrong person. ")
            + ("The proposed method matched the evidence. " if res.get("method_correct") else "The method differed from what the evidence supports. ")
            + (f"{len(res.get('decoys_cited', []))} cited item(s) were red herrings. " if res.get("decoys_cited") else ""))
    llm = ollama.generate("You are NEXUS. Write a 2-sentence neutral assessment of a detective's performance. Do not invent facts.",
                          base + f"Weakest category: {min((res.get('categories') or {'-': 0}).items(), key=lambda kv: kv[1])[0]}.", 120)
    return llm or base + "Revisit the weakest scoring category on the next case."


# ------------------------------------------------------------------ export / import / saves
def export_case(case_id):
    bundle(case_id)
    return db.dump_case(case_id)


def import_case(dump):
    try:
        cid = db.restore_case(dump)
    except Exception as e:
        raise GameError(f"Could not import case: {e}")
    return overview(cid)


def save_snapshot(case_id):
    d = export_case(case_id)
    name = f"{case_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(os.path.join(SAVES_DIR, name), "w", encoding="utf-8") as f:
        json.dump(d, f)
    return {"name": name}


def list_saves():
    out = []
    for fn in sorted(os.listdir(SAVES_DIR), reverse=True):
        if fn.endswith(".json"):
            out.append({"name": fn, "size": os.path.getsize(os.path.join(SAVES_DIR, fn))})
    return out


def load_save(name):
    path = os.path.join(SAVES_DIR, os.path.basename(name))
    if not os.path.exists(path):
        raise GameError("Save not found", 404)
    with open(path, encoding="utf-8") as f:
        return import_case(json.load(f))


def health():
    return {"ok": True, "ollama": ollama.status(), "version": "1.0"}
