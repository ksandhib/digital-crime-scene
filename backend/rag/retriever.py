"""Dependency-free retrieval for NEXUS.

Documents are built from DISCOVERED evidence only (plus the public cast list), so the AI can
never quote something the player has not found. TF-IDF cosine is plenty at this scale and
keeps the app instant and fully offline; swap in ChromaDB later if you want embeddings.
"""
import math
import re
from collections import Counter

from ..agents.common import fmt

STOP = set("the a an of to and or is was were who what which show me all in on at by for with from about "
           "that this it as be are did do does had has have their there them they we you i my our any "
           "everything connected between".split())


def tokens(text):
    return [t for t in re.findall(r"[a-z0-9#\-]+", (text or "").lower()) if t not in STOP and len(t) > 1]


def evidence_text(v, e):
    """Flatten an evidence item (and its source record) into searchable text."""
    parts = [e["id"], e["type"], e["title"], e["summary"], e["reliability"], fmt(e["minute"])]
    for ref in e.get("entities") or []:
        parts.append(v.name(ref))
        parts.append(ref)
    d = e.get("data") or {}
    parts.append(d.get("text", ""))
    for c in d.get("claims", []) or []:
        parts.append(c.get("quote", ""))
    for em in v.emails:
        if em["evidence_id"] == e["id"]:
            parts += [em["subject"], em["body"], v.name(em["sender"])]
    for m in v.messages:
        if m["evidence_id"] == e["id"]:
            parts += [l["text"] + " " + l["name"] for l in m["lines"]]
    for ev in v.events:
        if ev["evidence_id"] == e["id"]:
            parts += [ev["description"], ev["type"].replace("_", " "), v.name(ev["actor_ref"]), v.name(ev["device_ref"])]
    for i in v.images:
        if i["evidence_id"] == e["id"]:
            parts += [i["caption"]]
    return " ".join(str(p) for p in parts if p)


def retrieve(v, question, k=8):
    docs = []
    for eid in sorted(v.disc):
        e = v.ev[eid]
        docs.append((eid, tokens(evidence_text(v, e))))
    if not docs:
        return []
    q = tokens(question)
    if not q:
        return []
    df = Counter()
    for _, toks in docs:
        for t in set(toks):
            df[t] += 1
    n = len(docs)
    idf = lambda t: math.log(1 + n / (1 + df.get(t, 0)))
    qv = Counter(q)
    scored = []
    for eid, toks in docs:
        tf = Counter(toks)
        dot = sum(qv[t] * tf[t] * idf(t) ** 2 for t in qv if t in tf)
        if dot <= 0:
            continue
        norm = math.sqrt(sum((c * idf(t)) ** 2 for t, c in tf.items())) or 1
        scored.append((dot / norm, eid))
    scored.sort(key=lambda x: (-x[0], x[1]))
    return [{"id": eid, "score": round(s, 3)} for s, eid in scored[:k]]
