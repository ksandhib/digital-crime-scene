"""Hypothesis Analyst - evidence chains and hypothesis scoring (deterministic)."""
from .common import fmt, ACTION_TYPES
from . import timeline_analyst as tl

CHAIN_STEPS = [
    ("person_device", "Person \u2192 Device"),
    ("login", "Login / active session"),
    ("file_access", "File access"),
    ("file_modify", "File modification"),
    ("ext_connect", "External device"),
    ("ext_action", "Transfer"),
    ("location", "Presence at location"),
]


def chain(v, ref):
    """Strength of the evidence chain linking suspect `ref` to the incident."""
    ws, we, exact, tm = tl.window(v)
    pres = tl.presence(v)
    p = pres.get(ref, {})
    dev = tl.incident_device(v)
    steps = []
    if not dev:
        for key, label in CHAIN_STEPS:
            steps.append({"key": key, "label": label, "strength": 0.0, "status": "missing", "evidence": [],
                          "note": "No modification event has been found yet."})
        return _finish(ref, steps)

    d = v.devices[dev]
    dloc = d.get("location_ref")
    ex = tl.last_exit(pres, ref)
    absent = bool(ex and ex[0] < ws - 5)
    mod_t = tm if tm is not None else tl.window(v)[3]

    def evs(types, lo, hi, device=dev):
        return [e for e in v.events if e["type"] in types and e["device_ref"] == device and lo <= e["minute"] <= hi]

    unlock = evs({"device_unlock", "session_active"}, ws - 10, we)
    access = evs({"file_access"}, ws, we)
    modify = evs({"file_modify"}, ws, we + 5)
    extc = evs({"ext_connect"}, ws, we + 10)
    exta = evs({"ext_action"}, ws, we + 10)
    serial = (extc[0].get("data") or {}).get("serial") if extc else None

    # 1 person -> device
    links = []
    if d.get("owner_ref") == ref:
        links.append((0.5, [], "Assigned owner of the device"))
    for e in extc[:1]:
        for a in v.ev.values():
            ad = (a.get("data") or {}).get("asset")
            if a["id"] in v.disc and ad and ad["person"] == ref and ad["serial"] == serial:
                links.append((0.95, [a["id"], e["evidence_id"]], "Registered owner of the external device"))
    rooms = [(m, l, eid) for m, l, eid in p.get("rooms", []) if l == dloc and ws - 25 <= m <= we]
    if rooms:
        links.append((0.9, [rooms[0][2]], f"Entered {v.name(dloc)} at {fmt(rooms[0][0])}"))
    acct = [e for e in unlock + access + modify if e["actor_ref"] == ref]
    if acct:
        links.append((0.8, [acct[0]["evidence_id"]], "Their account was used on the device"))
    s1 = max([l[0] for l in links], default=0.0)
    if len([l for l in links if l[0] >= 0.8]) >= 2:
        s1 = 1.0
    ev1 = [i for l in links for i in l[2 - 1]][:4]
    note1 = "; ".join(l[2] for l in links) or "No link between this person and the device"
    status1 = "ok" if s1 >= 0.8 else ("partial" if s1 > 0 else "missing")
    if absent and s1 > 0:
        s1 = min(s1, 0.25)
        status1 = "contradicted"
        ev1 = ev1 + [ex[1]]
        note1 += f". But they badged out at {fmt(ex[0])}."
    steps.append({"key": "person_device", "label": CHAIN_STEPS[0][1], "strength": s1, "status": status1,
                  "evidence": ev1, "note": note1})
    link = s1

    # 2 login
    if unlock:
        e = unlock[0]
        if e["actor_ref"] == ref and not absent:
            s2, st, note = 1.0, "ok", f"Login by their account at {fmt(e['minute'])}"
        elif p.get("rooms") and any(l == dloc and abs(m - e["minute"]) <= 25 for m, l, _ in p["rooms"]):
            s2, st, note = 0.8, "partial", f"Session activity at {fmt(e['minute'])} while they were in the room"
        elif e["actor_ref"] == ref and absent:
            s2, st, note = 0.3, "contradicted", "Their account was active while they were outside the building"
        else:
            s2, st, note = 0.2, "partial", "Session belongs to another account / cannot be attributed"
        steps.append({"key": "login", "label": CHAIN_STEPS[1][1], "strength": s2, "status": st,
                      "evidence": [e["evidence_id"]], "note": note})
    else:
        steps.append({"key": "login", "label": CHAIN_STEPS[1][1], "strength": 0.0, "status": "missing",
                      "evidence": [], "note": "No login or session event found"})

    # 3-6 device-side events, attributed through the link
    for key, label, found in (("file_access", CHAIN_STEPS[2][1], access), ("file_modify", CHAIN_STEPS[3][1], modify),
                              ("ext_connect", CHAIN_STEPS[4][1], extc), ("ext_action", CHAIN_STEPS[5][1], exta)):
        if found:
            steps.append({"key": key, "label": label, "strength": round(link, 2),
                          "status": "ok" if link >= 0.8 else ("partial" if link > 0 else "missing"),
                          "evidence": [found[0]["evidence_id"]],
                          "note": f"{found[0]['description']} ({fmt(found[0]['minute'])})"
                                  + ("" if link >= 0.8 else " - not firmly attributed to this person")})
        else:
            steps.append({"key": key, "label": label, "strength": 0.0, "status": "missing", "evidence": [],
                          "note": "No evidence found yet"})

    # 7 location
    if absent:
        steps.append({"key": "location", "label": CHAIN_STEPS[6][1], "strength": 0.0, "status": "contradicted",
                      "evidence": [ex[1]], "note": f"Badge record shows they left the building at {fmt(ex[0])}"})
    elif rooms:
        steps.append({"key": "location", "label": CHAIN_STEPS[6][1], "strength": 1.0, "status": "ok",
                      "evidence": [rooms[0][2]], "note": f"Badge entry to {v.name(dloc)} at {fmt(rooms[0][0])}"})
    else:
        steps.append({"key": "location", "label": CHAIN_STEPS[6][1], "strength": 0.0, "status": "missing",
                      "evidence": [], "note": "No evidence placing them at the device location"})
    return _finish(ref, steps)


def _finish(ref, steps):
    strength = int(round(100 * sum(s["strength"] for s in steps) / len(steps)))
    missing = [s["label"] for s in steps if s["status"] in ("missing", "contradicted")]
    complete = strength >= 85 and not missing
    return {"suspect": ref, "steps": steps, "strength": min(strength, 98) if complete else strength,
            "complete": complete, "missing": missing}


def evaluate(v, hyp, sus, ch):
    """Support / against lists and confidence for a hypothesis about a suspect."""
    ref = hyp.get("suspect_ref")
    s = sus.get(ref)
    if not s:
        return {"support": [], "against": [], "confidence": 0}
    support, against = [], []
    for f in s["factors"]:
        row = {"text": f["label"], "evidence": f["evidence"]}
        if f["weight"] > 0:
            support.append(row)
        elif f["weight"] < 0 or f.get("info"):
            against.append(row)
    for st in ch["steps"]:
        if st["status"] in ("missing", "contradicted"):
            against.append({"text": "No evidence: " + st["label"] if st["status"] == "missing"
                            else "Contradicted: " + st["label"] + " - " + st["note"], "evidence": st["evidence"]})
    pinned_for = [e for e in (hyp.get("support") or []) if isinstance(e, str)]
    pinned_against = [e for e in (hyp.get("against") or []) if isinstance(e, str)]
    conf = 0.55 * s["score"] + 0.45 * ch["strength"] + 2 * len(pinned_for) - 3 * len(pinned_against)
    return {"support": support[:8], "against": against[:8], "confidence": int(max(0, min(97, round(conf))))}
