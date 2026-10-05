"""Relationship Analyst - the evidence graph is derived only from stored rows.

Nodes for people / devices / locations / files / organisations always exist (they are the
cast of the case). Emails, messages, images and key events only appear once their
evidence has been discovered, and an edge is only drawn once the evidence behind it is known.
"""
from .common import fmt


def graph(v):
    b = v.b
    nodes = {}

    def add(ref, ntype, label, sub="", evidence_id=None, **extra):
        nodes[ref] = dict({"id": ref, "type": ntype, "label": label, "sub": sub, "evidence_id": evidence_id}, **extra)

    for s in b["suspects"]:
        add(s["ref"], "person", s["name"], s["role"], role="suspect")
    for s in b["victims"]:
        add(s["ref"], "person", s["name"], s["role"], role="victim")
    for s in b["witnesses"]:
        add(s["ref"], "person", s["name"], s["role"], role="witness")
    for d in b["devices"]:
        add(d["ref"], "device", d["name"], d["kind"])
    for l in b["locations"]:
        add(l["ref"], "location", l["name"], l["building"])
    for f in b["files"]:
        add(f["ref"], "file", f["filename"], "target file" if (f.get("extra") or {}).get("target") else "file",
            f["evidence_id"])
    for o in (v.case.get("data") or {}).get("orgs", []):
        add(o["ref"], "org", o["name"], o.get("sub", "organization"))
    for e in b["emails"]:
        if e["evidence_id"] in v.disc:
            add(e["ref"], "email", e["subject"][:28], fmt(e["minute"]), e["evidence_id"])
    for m in b["messages"]:
        if m["evidence_id"] in v.disc:
            add(m["ref"], "message", (m.get("extra") or {}).get("label", "Message thread")[:28], fmt(m["minute"]),
                m["evidence_id"])
    for i in b["images"]:
        if i["evidence_id"] in v.disc:
            add(i["ref"], "image", (i["caption"] or "Image")[:28], fmt(i["minute"]), i["evidence_id"])
    for e in b["events"]:
        if (e.get("data") or {}).get("node") and e["evidence_id"] in v.disc:
            add(e["ref"], "event", e["description"][:30], fmt(e["minute"]), e["evidence_id"])

    edges = []
    for r in b["relationships"]:
        if r["evidence_id"] and r["evidence_id"] not in v.disc:
            continue
        if r["src"] in nodes and r["dst"] in nodes:
            edges.append({"id": r["ref"], "source": r["src"], "target": r["dst"], "type": r["type"],
                          "label": r["label"], "minute": r["minute"], "evidence_id": r["evidence_id"]})
    deg = {}
    for e in edges:
        deg[e["source"]] = deg.get(e["source"], 0) + 1
        deg[e["target"]] = deg.get(e["target"], 0) + 1
    for n in nodes.values():
        n["degree"] = deg.get(n["id"], 0)
    return {"nodes": list(nodes.values()), "edges": edges}


def connected_to(v, ref):
    g = graph(v)
    out = []
    for e in g["edges"]:
        if ref in (e["source"], e["target"]):
            other = e["target"] if e["source"] == ref else e["source"]
            out.append({"type": e["type"], "other": other, "label": e["label"], "evidence_id": e["evidence_id"],
                        "minute": e["minute"]})
    return out
