"""Timeline Analyst - deterministic. No LLM involved."""
from .common import fmt, ACTION_TYPES, EVENT_LABELS


def window(v):
    """Incident window as far as the discovered evidence allows.
    Returns (start, end, exact, modify_minute)."""
    mods = [e for e in v.events if e["type"] == "file_modify"]
    if mods:
        m = min(e["minute"] for e in mods)
        return m - 35, m + 20, True, m
    tf = v.target_file
    if v.case["difficulty"] in ("EASY", "MEDIUM") and tf and tf["evidence_id"] in v.disc and tf.get("modified"):
        m = tf["modified"]
        return m - 35, m + 20, True, m
    a = v.alert_minute
    return a - 110, a, False, None


def presence(v):
    """person ref -> dict of badge / camera / device facts (discovered evidence only)."""
    out = {}

    def slot(ref):
        return out.setdefault(ref, {"in": [], "out": [], "rooms": [], "cam": [], "dev": []})

    for e in v.events:
        a = e["actor_ref"]
        if not a or a not in v.persons:
            continue
        s = slot(a)
        t = e["type"]
        if t == "badge_in":
            s["in"].append((e["minute"], e["evidence_id"]))
        elif t == "badge_out":
            s["out"].append((e["minute"], e["evidence_id"]))
        elif t == "badge_room":
            s["rooms"].append((e["minute"], e["location_ref"], e["evidence_id"]))
        elif t == "camera_detect":
            s["cam"].append((e["minute"], e["evidence_id"]))
        elif t in ACTION_TYPES or t in ("server_access", "message_deleted"):
            s["dev"].append((e["minute"], e["device_ref"], e["evidence_id"], t))
    return out


def last_exit(pres, ref):
    outs = (pres.get(ref) or {}).get("out") or []
    return max(outs) if outs else None


def incident_device(v):
    mods = [e for e in v.events if e["type"] == "file_modify"]
    return mods[0]["device_ref"] if mods else None


def entries(v, contradiction_evids=()):
    """Player-visible timeline: one entry per discovered event / email / message / image."""
    ws, we, exact, tm = window(v)
    rows = []
    for t in v.b["timeline_events"]:
        if t["evidence_id"] not in v.disc:
            continue
        r = dict(t)
        r["time"] = fmt(t["minute"])
        r["reliability"] = v.ev[t["evidence_id"]]["reliability"]
        sus = False
        if exact and ws <= t["minute"] <= we and (
                t["type"] in ACTION_TYPES or (t["type"] == "badge_room" and t["location_ref"] == v.target_loc)):
            sus = True
        if t["evidence_id"] in contradiction_evids:
            sus = True
        r["suspicious"] = sus
        rows.append(r)
    rows.sort(key=lambda r: (r["minute"], r["ref"]))
    return rows


def label_for(etype):
    return EVENT_LABELS.get(etype, etype.replace("_", " ").title())
