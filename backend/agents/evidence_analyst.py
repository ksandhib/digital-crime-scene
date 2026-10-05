"""Evidence Analyst - deterministic contradiction, correlation and suspicion engines.

Everything here is computed from DISCOVERED evidence only, so the analysis grows
as the player investigates and can never leak the hidden ground truth.
"""
import math
from .common import fmt, ACTION_TYPES, REL_W
from . import timeline_analyst as tl


# ------------------------------------------------------------------ contradictions
def contradictions(v):
    ws, we, exact, tm = tl.window(v)
    pres = tl.presence(v)
    out = []

    def in_window(m):
        return ws - 20 <= m <= we + 45

    for s in v.suspects:
        ref = s["ref"]
        claim = (s.get("extra") or {}).get("alibi_claim")
        if not claim or claim.get("type") != "left":
            continue
        L = claim["minute"]
        p = pres.get(ref, {})
        later = []
        for m, eid in p.get("out", []):
            if m > L + 8:
                later.append((m, eid, "Badge record shows exit at %s" % fmt(m)))
        for m, loc, eid in p.get("rooms", []):
            if m > L + 8:
                later.append((m, eid, "Badge record shows entry to %s at %s" % (v.name(loc), fmt(m))))
        if later:
            later.sort()
            crit = any(in_window(m) for m, _, _ in later)
            eids = []
            for _, eid, _ in later:
                if eid not in eids:
                    eids.append(eid)
            out.append({
                "id": f"alibi:{ref}:{'/'.join(eids)}", "kind": "alibi", "person": ref,
                "severity": "CRITICAL" if crit else "MINOR", "evidence_ids": eids, "claim_ev": None,
                "text": f"{s['name']} says they left the building at {fmt(L)}. "
                        f"{later[0][2]}"
                        + (f"; further records place them there as late as {fmt(later[-1][0])}." if len(later) > 1 else ".")})
        # account activity after the stated departure while the badge says they were gone
        outs = p.get("out", [])
        acct = [(m, eid) for m, dev, eid, t in p.get("dev", []) if t in ACTION_TYPES and m > L + 8]
        if acct and outs and max(outs)[0] <= L + 8:
            eids = [outs[-1][1]] + [eid for _, eid in acct[:3]]
            out.append({
                "id": f"account:{ref}:{'/'.join(eids)}", "kind": "account", "person": ref,
                "severity": "CONTESTED", "evidence_ids": eids, "claim_ev": None,
                "text": f"{s['name']}'s account was active at {fmt(acct[0][0])}, after they badged out at "
                        f"{fmt(max(outs)[0])}. The account may have been used by someone else."})

    # witness / tip claims vs badge records
    for eid in sorted(v.disc):
        ev = v.ev[eid]
        for claim in (ev.get("data") or {}).get("claims", []) or []:
            ref = claim.get("person")
            if not ref or ref not in v.persons:
                continue
            outs = (pres.get(ref) or {}).get("out", [])
            if outs and max(outs)[0] < claim["minute"] - 10:
                ex = max(outs)
                eids = [eid, ex[1]]
                cams = [ce for cm, ce in (pres.get(ref) or {}).get("cam", []) if cm >= ex[0]]
                eids += cams[:1]
                out.append({
                    "id": f"claim:{ref}:{eid}", "kind": "claim", "person": ref,
                    "severity": "CRITICAL" if in_window(claim["minute"]) else "MINOR",
                    "evidence_ids": eids, "claim_ev": eid,
                    "text": f"{ev['title']} places {v.name(ref)} near {v.name(claim.get('location_ref'))} "
                            f"at about {fmt(claim['minute'])}, but their badge exit is logged at {fmt(ex[0])}."})
    return out


# ------------------------------------------------------------------ suspicion
def suspicion(v, contr=None):
    ws, we, exact, tm = tl.window(v)
    pres = tl.presence(v)
    contr = contradictions(v) if contr is None else contr
    bad_claims = {c["claim_ev"] for c in contr if c["kind"] == "claim"}
    inc_dev = tl.incident_device(v)
    ext = [e for e in v.events if e["type"] == "ext_connect"]
    serial = (ext[0].get("data") or {}).get("serial") if ext else None
    assets = [e for e in v.ev.values() if e["id"] in v.disc and (e.get("data") or {}).get("asset")]
    tf = v.target_file
    acl = (tf.get("extra") or {}).get("access_list", []) if tf else []
    out = {}
    for s in v.suspects:
        ref = s["ref"]
        p = pres.get(ref, {})
        F = []

        def add(label, w, eids=(), key=None, info=False):
            eids = [e for e in eids if e]
            F.append({"label": label, "weight": round(w * (v.relf(eids) if eids else 1.0), 1),
                      "evidence": eids, "key": key, "info": info})

        opp = "unknown"
        if tf and ref in acl:
            add("Authorized to access the target file", 7, [tf["evidence_id"]], "acl")
        if s.get("access_level") == "HIGH":
            add("High-level clearance", 3, [], "clearance")
        ex = tl.last_exit(pres, ref)
        if exact:
            if ex:
                if ex[0] < ws - 5:
                    add(f"Left the building at {fmt(ex[0])}, before the incident window", -34, [ex[1]], "absent")
                    opp = "absent"
                else:
                    add(f"Still in the building at {fmt(ex[0])}, after the incident began", 13, [ex[1]], "present")
                    opp = "present"
            for m, loc, eid in p.get("rooms", []):
                if ws - 5 <= m <= we:
                    if loc == v.target_loc or loc == (v.devices.get(inc_dev) or {}).get("location_ref"):
                        add(f"Entered {v.name(loc)} at {fmt(m)}, inside the incident window", 24, [eid], "room")
                    else:
                        add(f"In {v.name(loc)} at {fmt(m)} (not the incident location)", 5, [eid], "elsewhere")
            if inc_dev:
                evs = [e for e in v.events if e["device_ref"] == inc_dev and e["actor_ref"] == ref
                       and e["type"] in ACTION_TYPES and ws <= e["minute"] <= we]
                if evs:
                    add(f"Account active on {v.name(inc_dev)} during the window", 16,
                        [e["evidence_id"] for e in evs[:3]], "account")
        # alibi
        for c in contr:
            if c["person"] != ref:
                continue
            if c["kind"] == "alibi":
                add("Alibi contradiction" if c["severity"] == "CRITICAL" else "Minor alibi discrepancy",
                    24 if c["severity"] == "CRITICAL" else 6, c["evidence_ids"][:3], "alibi_" + c["severity"].lower())
            elif c["kind"] == "account":
                add("Account activity after departure (contested)", 0, c["evidence_ids"][:3], "contested", info=True)
            elif c["kind"] == "claim":
                add("Claim placing them at the scene is contradicted", 0, c["evidence_ids"][:3], "claim_bad", info=True)
        # motive
        for eid in sorted(v.disc):
            d = v.ev[eid].get("data") or {}
            if d.get("motive_for") == ref:
                w = 8 if d.get("motive_tag") == "dispute" else 10
                add(d.get("motive_label") or "Possible motive", w, [eid], "motive")
        # deleted messages
        for e in v.events:
            if e["type"] == "message_deleted" and e["actor_ref"] == ref:
                exp = (e.get("data") or {}).get("explained_by")
                if exp and exp in v.disc:
                    add("Deleted message explained by an automatic retention policy", 0, [e["evidence_id"], exp],
                        "deleted_resolved", info=True)
                else:
                    add("Message thread deleted from their account", 9, [e["evidence_id"]], "deleted")
        # activity after claimed departure
        claim = (s.get("extra") or {}).get("alibi_claim")
        if claim and claim.get("type") == "left":
            for em in v.emails:
                if em["sender"] == ref and em["minute"] > claim["minute"] + 8:
                    add(f"Email sent at {fmt(em['minute'])}, after their stated departure", 6, [em["evidence_id"]], "late_email")
        # external drive attribution
        for a in assets:
            ad = a["data"]["asset"]
            if ad["person"] != ref:
                continue
            if serial and ad["serial"] == serial:
                add("The external device used in the incident is registered to them", 20,
                    [a["id"], ext[0]["evidence_id"]], "ext_match")
            elif serial and ad["serial"] != serial:
                add("A different external device was assigned to them (does not match)", -8, [a["id"]], "ext_mismatch")
        # claims by witnesses / anonymous tips
        for eid in sorted(v.disc):
            for cl in (v.ev[eid].get("data") or {}).get("claims", []) or []:
                if cl.get("person") == ref and eid not in bad_claims:
                    add(f"Reported near {v.name(cl.get('location_ref'))} at about {fmt(cl['minute'])}", 11, [eid], "claim")
        # earlier legitimate-looking server access
        for e in v.events:
            if e["type"] == "server_access" and e["actor_ref"] == ref:
                add(f"Read the target file at {fmt(e['minute'])} (earlier that evening)", 4, [e["evidence_id"]], "early_access")

        raw = sum(f["weight"] for f in F)
        score = int(round(100 * (1 - math.exp(-max(raw, 0) / 50.0))))
        crit = [c for c in contr if c["person"] == ref and c["kind"] == "alibi" and c["severity"] == "CRITICAL"]
        minor = [c for c in contr if c["person"] == ref and c["kind"] in ("alibi",) and c["severity"] == "MINOR"]
        tested = bool(claim and (ex or crit or minor))
        if claim and claim.get("type") == "stayed":
            tested = bool(ex)
        consistency = None
        status = "untested"
        if tested:
            consistency = max(5, 100 - 42 * len(crit) - 14 * len(minor))
            status = "contradicted" if (crit or minor) else "corroborated"
        out[ref] = {"score": score, "raw": round(raw, 1), "factors": F, "opportunity": opp,
                    "consistency": consistency, "alibi_status": status,
                    "exit": ({"minute": ex[0], "evidence": ex[1]} if ex else None)}
    return out


def lead(v, sus):
    ranked = sorted(sus.items(), key=lambda kv: -kv[1]["score"])
    if not ranked or ranked[0][1]["score"] <= 0:
        return None, 0, 0
    top = ranked[0]
    second = ranked[1][1]["score"] if len(ranked) > 1 else 0
    conf = int(min(96, round(top[1]["score"] * 0.6 + max(0, top[1]["score"] - second) * 0.8)))
    return top[0], conf, second


# ------------------------------------------------------------------ correlations
def correlations(v):
    """Cluster action events per device, then pull in nearby presence / communication evidence."""
    found = []
    by_dev = {}
    for e in v.events:
        if e["type"] in ACTION_TYPES and e["device_ref"]:
            by_dev.setdefault(e["device_ref"], []).append(e)
    for dev, evs in by_dev.items():
        evs.sort(key=lambda e: e["minute"])
        cluster = [evs[0]]
        clusters = []
        for e in evs[1:]:
            if e["minute"] - cluster[-1]["minute"] <= 10:
                cluster.append(e)
            else:
                clusters.append(cluster)
                cluster = [e]
        clusters.append(cluster)
        for cl in clusters:
            if len(cl) < 3:
                continue
            start, end = cl[0]["minute"], cl[-1]["minute"]
            items = {e["evidence_id"]: e["minute"] for e in cl}
            loc = (v.devices.get(dev) or {}).get("location_ref")
            for e in v.events:
                if e["type"] == "badge_room" and e["location_ref"] == loc and start - 25 <= e["minute"] <= end:
                    items[e["evidence_id"]] = e["minute"]
            accts = {e["actor_ref"] for e in cl if e["actor_ref"]}
            for em in v.emails:
                if em["sender"] in accts and start - 20 <= em["minute"] <= end + 5:
                    items[em["evidence_id"]] = em["minute"]
            kinds = {v.ev[i]["type"] for i in items}
            has_mod = any(e["type"] in ("file_modify", "ext_action") for e in cl)
            avg_rel = sum(v.rel(i) for i in items) / len(items)
            conf = int(min(97, 30 + 8 * len(items) + 6 * len(kinds) + (10 if has_mod else 0) + 12 * avg_rel))
            ids = sorted(items, key=lambda i: items[i])
            found.append({
                "id": "cluster:" + dev + ":" + ids[0], "kind": "cluster",
                "label": "SUSPICIOUS ACTIVITY CLUSTER" if has_mod else "ACTIVITY CLUSTER",
                "confidence": conf, "evidence_ids": ids, "device": dev,
                "start": start, "end": end,
                "text": f"{len(ids)} evidence items between {fmt(min(items.values()))} and {fmt(max(items.values()))} "
                        f"converge on {v.name(dev)} ({', '.join(sorted(kinds)).lower()})."})
    # presence correlation: person entered the room that hosts an active device inside the window
    ws, we, exact, tm = tl.window(v)
    pres = tl.presence(v)
    for f in list(found):
        loc = (v.devices.get(f["device"]) or {}).get("location_ref")
        for ref, p in pres.items():
            for m, l, eid in p["rooms"]:
                if l == loc and f["start"] - 25 <= m <= f["end"]:
                    found.append({
                        "id": f"presence:{ref}:{eid}:{f['device']}", "kind": "presence",
                        "label": "PRESENCE CORRELATION", "confidence": int(min(95, 55 + 20 * v.rel(eid) + 8 * (len(f['evidence_ids']) > 4))),
                        "evidence_ids": [eid] + [i for i in f["evidence_ids"] if i != eid][:4],
                        "device": f["device"], "person": ref, "start": m, "end": f["end"],
                        "text": f"{v.name(ref)} entered {v.name(l)} at {fmt(m)}, minutes before activity on "
                                f"{v.name(f['device'])}."})
    return found


def strongest(v, contr, corr, chain_evids, k=6):
    score = {}
    for eid in v.disc:
        e = v.ev[eid]
        if e["type"] == "SYSTEM" and e.get("title", "").startswith("Incident"):
            continue
        score[eid] = v.rel(eid)
    for c in corr:
        for i in c["evidence_ids"]:
            score[i] = score.get(i, 0) + 0.8
    for c in contr:
        if c["severity"] == "CRITICAL":
            for i in c["evidence_ids"]:
                score[i] = score.get(i, 0) + 1.1
    for i in chain_evids:
        score[i] = score.get(i, 0) + 0.6
    ranked = sorted(score.items(), key=lambda kv: (-kv[1], kv[0]))
    return [{"id": i, "score": round(s, 2)} for i, s in ranked[:k]]
