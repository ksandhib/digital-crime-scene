"""NEXUS - the investigation assistant.

CASE DATABASE -> RETRIEVAL -> RELEVANT EVIDENCE -> (deterministic facts) -> optional local LLM -> answer

Facts are always computed deterministically from discovered evidence. The LLM, when available,
only rewrites them into concise prose; its output is rejected if it cites an evidence id that was
not supplied. It never receives, and cannot reveal, the hidden ground truth.
"""
import re

from ..agents.common import View, fmt, evid_list, parse_hhmm, ACTION_TYPES
from ..agents import evidence_analyst as ea, hypothesis_analyst as ha, timeline_analyst as tl
from ..agents import relationship_analyst as ra
from ..rag import retriever
from . import ollama

SYSTEM = ("You are NEXUS, a forensic analysis assistant inside a fictional detective game. Answer ONLY from the "
          "FACTS and EVIDENCE provided. Be concise (max 120 words), cite evidence ids like E-012, never invent "
          "evidence, never reveal reasoning steps, and say so if the evidence is insufficient.")


def _match_people(v, q):
    ql = q.lower()
    out = []
    for ref, p in v.persons.items():
        full = p["name"].lower()
        first = full.replace("dr. ", "").split()[0]
        last = full.split()[-1]
        if full in ql or re.search(r"\b%s\b" % re.escape(first), ql) or re.search(r"\b%s\b" % re.escape(last), ql) \
                or re.search(r"\b%s\b" % ref.lower(), ql):
            out.append(ref)
    return out


def _match_devices(v, q):
    ql = q.lower()
    out = []
    for ref, d in v.devices.items():
        m = re.search(r"#(\d+)", d["name"])
        if d["name"].lower() in ql or ref.lower() in ql or (m and re.search(r"(laptop|workstation|device)\s*#?0*%s\b" % m.group(1).lstrip("0"), ql)):
            out.append(ref)
    return out


def _times(q):
    return [int(h) * 60 + int(m) for h, m in re.findall(r"\b([01]?\d|2[0-3])[:.]([0-5]\d)\b", q)]


def classify(q):
    ql = q.lower()
    if "contradict" in ql or "conflict" in ql or "lying" in ql or "alibi" in ql:
        return "contradict"
    if "missing" in ql or "what evidence is" in ql or "what do i need" in ql or "gap" in ql:
        return "missing"
    if "opportunity" in ql:
        return "opportunity"
    if "strongest" in ql or "best evidence" in ql or "key evidence" in ql:
        return "strongest"
    if "access" in ql and ("who" in ql or "had" in ql):
        return "access"
    if ("near" in ql or "who was" in ql or "present" in ql) and _times(q):
        return "near"
    if "between" in ql or re.search(r"\bat \d", ql) or "what happened" in ql:
        return "window"
    if "everything" in ql or "connected" in ql or "about" in ql or "tell me" in ql:
        return "person"
    if "suspect" in ql or "who did" in ql or "who is" in ql or "lead" in ql or "summary" in ql or "what do we know" in ql:
        return "summary"
    return "search"


def _line(v, eid):
    e = v.ev[eid]
    return f"{eid} ({e['reliability'].lower()}): {e['summary']}"


def answer(bundle, question, use_llm=True):
    v = View(bundle)
    contr = ea.contradictions(v)
    sus = ea.suspicion(v, contr)
    intent = classify(question)
    people = _match_people(v, question)
    devices = _match_devices(v, question)
    times = _times(question)
    retrieved = retriever.retrieve(v, question, 8)
    lines, evidence, conf_hint = [], [], None

    def cite(ids):
        for i in ids:
            if i and i in v.disc and i not in evidence:
                evidence.append(i)

    if not v.disc:
        return {"text": "No evidence has been discovered yet.", "evidence": [], "confidence": 0, "mode": "deterministic", "intent": intent}

    if intent == "access":
        tf = v.target_file
        acl = (tf.get("extra") or {}).get("access_list", []) if tf else []
        lines.append(f"{len(acl)} people are authorized to access {tf['filename']}:")
        for i, ref in enumerate(acl, 1):
            lines.append(f"{i}. {v.name(ref)} - {v.persons[ref]['role']}")
        cite([tf["evidence_id"]])
        touched = {}
        for e in v.events:
            if e["type"] in ("file_access", "file_modify", "ext_action", "server_access"):
                touched.setdefault(e["actor_ref"] or "shared account", []).append(e)
        for who, evs in touched.items():
            nm = v.name(who) if who in v.persons else "an unattributed shared session"
            lines.append(f"Activity on the file under {nm}'s account at {', '.join(fmt(e['minute']) for e in evs[:3])}.")
            cite([e["evidence_id"] for e in evs[:3]])
        lines.append("Authorization is not the same as who actually acted: compare it with presence evidence.")
    elif intent == "person" and people:
        ref = people[0]
        s = sus.get(ref)
        evs = v.evidence_of(ref)
        kinds = {}
        for e in evs:
            kinds[e["type"]] = kinds.get(e["type"], 0) + 1
        lines.append(f"{v.name(ref)} ({v.persons[ref]['role']}) appears in {len(evs)} discovered evidence items: "
                     + ", ".join(f"{n} {k.lower()}" for k, n in sorted(kinds.items())) + ".")
        if s:
            for f in sorted(s["factors"], key=lambda f: -abs(f["weight"]))[:4]:
                lines.append(("+ " if f["weight"] > 0 else "- " if f["weight"] < 0 else "i ") + f["label"])
                cite(f["evidence"])
            lines.append(f"Current suspicion {s['score']}%.")
        cite([e["id"] for e in evs[:6]])
    elif intent == "window" or intent == "near":
        if len(times) >= 2:
            lo, hi = min(times[:2]), max(times[:2])
        elif times:
            lo, hi = times[0] - 15, times[0] + 15
        else:
            ws, we, ex, tm = tl.window(v)
            lo, hi = ws, we
        evs = [e for e in v.events if lo <= e["minute"] <= hi]
        if devices:
            evs = [e for e in evs if e["device_ref"] in devices] or evs
        if intent == "near":
            loc = None
            if devices:
                loc = v.devices[devices[0]]["location_ref"]
            pres = tl.presence(v)
            who = []
            for ref, p in pres.items():
                for m, l, eid in p["rooms"]:
                    if lo <= m <= hi and (loc is None or l == loc):
                        who.append((ref, m, l, eid))
            for e in evs:
                if e["actor_ref"] in v.persons and e["type"] in ACTION_TYPES:
                    who.append((e["actor_ref"], e["minute"], e["location_ref"], e["evidence_id"]))
            if who:
                lines.append(f"Between {fmt(lo)} and {fmt(hi)}"
                             + (f" around {v.name(devices[0])}" if devices else "") + ", discovered records show:")
                for ref, m, l, eid in sorted(set(who), key=lambda x: x[1]):
                    lines.append(f"- {v.name(ref)} at {v.name(l)} ({fmt(m)})")
                    cite([eid])
            else:
                lines.append("No discovered record places a named person there in that period. Unexamined sources may exist.")
            for e in evs[:4]:
                if e["actor_ref"] is None or e["actor_ref"] not in v.persons:
                    lines.append(f"- {fmt(e['minute'])}: {e['description']} (account not attributed to a person)")
                    cite([e["evidence_id"]])
        else:
            if evs:
                lines.append(f"{len(evs)} events between {fmt(lo)} and {fmt(hi)}:")
                for e in evs[:12]:
                    lines.append(f"{fmt(e['minute'])} - {e['description']}")
                    cite([e["evidence_id"]])
            else:
                lines.append(f"No discovered events between {fmt(lo)} and {fmt(hi)}.")
        for em in [x for x in v.emails if lo <= x["minute"] <= hi][:3]:
            lines.append(f"{fmt(em['minute'])} - email \"{em['subject']}\" from {v.name(em['sender'])}")
            cite([em["evidence_id"]])
    elif intent == "contradict":
        cs = [c for c in contr if not people or c["person"] in people]
        if not cs:
            lines.append("No contradictions are detectable in the evidence discovered so far."
                         + (" Their statement has not been tested against badge or device records yet." if people else ""))
        for c in cs:
            lines.append(f"[{c['severity']}] {c['text']}")
            cite(c["evidence_ids"])
        if people and not cs and v.persons[people[0]].get("alibi"):
            lines.append("Statement on record: " + v.persons[people[0]]["alibi"])
    elif intent == "missing":
        lead_ref, conf, _ = ea.lead(v, sus)
        if lead_ref:
            ch = ha.chain(v, lead_ref)
            lines.append(f"For the leading suspect ({v.name(lead_ref)}) the chain is {ch['strength']}% complete.")
            if ch["missing"]:
                lines.append("Missing or contradicted links: " + ", ".join(ch["missing"]) + ".")
            else:
                lines.append("No gaps in the chain. Check the alternatives are properly ruled out.")
        else:
            lines.append("No clear lead yet. Establish the incident window and who was present.")
        unexamined = _unexamined(v, bundle)
        if unexamined:
            lines.append("Sources with data you have not examined yet: " + ", ".join(v.name(r) for r in unexamined[:5]) + ".")
    elif intent == "opportunity":
        ws, we, exact, tm = tl.window(v)
        lines.append(("Incident window " + f"{fmt(ws)}-{fmt(we)}" if exact else "The exact incident window is not established yet") + ".")
        for s in v.suspects:
            o = sus[s["ref"]]
            word = {"present": "was in the building", "absent": "had left the building (cleared by records)",
                    "unknown": "presence not yet established"}[o["opportunity"]]
            lines.append(f"- {s['name']}: {word}")
            if o["exit"]:
                cite([o["exit"]["evidence"]])
    elif intent == "strongest":
        lead_ref, _, _ = ea.lead(v, sus)
        ch = ha.chain(v, lead_ref) if lead_ref else {"steps": []}
        corr = ea.correlations(v)
        top = ea.strongest(v, contr, corr, [i for s in ch["steps"] for i in s["evidence"]], 5)
        lines.append("Strongest evidence so far (reliability plus how much other evidence converges on it):")
        for t in top:
            lines.append("- " + _line(v, t["id"]))
            cite([t["id"]])
    elif intent == "summary":
        lead_ref, conf, second = ea.lead(v, sus)
        if lead_ref:
            s = sus[lead_ref]
            lines.append(f"Current lead: {v.name(lead_ref)} at {s['score']}% suspicion. Treat this as provisional.")
            for f in sorted(s["factors"], key=lambda f: -f["weight"])[:4]:
                if f["weight"] > 0:
                    lines.append("+ " + f["label"])
                    cite(f["evidence"])
        else:
            lines.append("No suspect stands out yet.")
    else:
        pass

    if not lines:  # generic retrieval answer
        if retrieved:
            lines.append("Most relevant evidence found:")
            for r in retrieved[:5]:
                lines.append("- " + _line(v, r["id"]))
                cite([r["id"]])
        else:
            lines.append("I can't find anything in the discovered evidence that matches. Try examining devices, people or locations to surface more.")
    cite([r["id"] for r in retrieved[:3]] if len(evidence) < 2 else [])
    avg = sum(v.rel(e) for e in evidence) / len(evidence) if evidence else 0.3
    conf = int(round(100 * min(0.95, 0.3 + 0.07 * len(evidence) + 0.3 * avg))) if evidence else 25
    facts = "\n".join(lines)
    out = {"text": facts, "evidence": evidence, "confidence": conf, "mode": "deterministic", "intent": intent}
    if use_llm and evidence:
        ctx = "\n".join(_line(v, i) for i in evidence[:12])
        gen = ollama.generate(SYSTEM, f"QUESTION: {question}\n\nFACTS:\n{facts}\n\nEVIDENCE:\n{ctx}\n\nAnswer:")
        if gen and set(evid_list(gen)) <= set(v.disc) and len(gen) < 1400:
            out["text"] = gen
            out["mode"] = "llm"
            out["facts"] = facts
    return out


def _unexamined(v, bundle):
    counts = {}
    for e in bundle["evidence"]:
        if not e["discovered"]:
            for ref in e.get("entities") or []:
                if ref.startswith(("D-", "L-")):
                    counts[ref] = counts.get(ref, 0) + 1
    return [r for r, _ in sorted(counts.items(), key=lambda kv: -kv[1])]
