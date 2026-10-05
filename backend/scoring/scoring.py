"""Investigation scoring - fully deterministic, no LLM."""
from ..agents.common import View, parse_hhmm
from ..agents import evidence_analyst as ea, hypothesis_analyst as ha

WEIGHTS = {"evidence": 15, "interpretation": 15, "false_leads": 15, "timeline": 15, "suspects": 15, "conclusion": 25}


def grade(total):
    for cut, g in ((97, "S+"), (92, "S"), (85, "A"), (75, "B"), (62, "C"), (45, "D")):
        if total >= cut:
            return g
    return "F"


def time_score(guess, actual):
    if guess is None:
        return 0
    d = abs(guess - actual)
    return 100 if d <= 5 else 60 if d <= 15 else 30 if d <= 30 else 0


def score(bundle, truth, acc, hypotheses):
    roles = truth["roles"]
    key = set(truth["key_evidence"])
    decoy_ev = {e for d in truth["decoys"] for e in d["evidence"]} | {i for i, r in roles.items() if r == "decoy"}
    disc = {e["id"] for e in bundle["evidence"] if e["discovered"]}
    perp = truth["perpetrator_ref"]
    decoy_suspects = {d["suspect"] for d in truth["decoys"]}

    who_ok = acc.get("suspect_ref") == perp
    motive_ok = acc.get("motive_key") == truth["motive_key"]
    method_ok = acc.get("method_key") == truth["method_key"]
    guess = parse_hhmm(acc.get("time", ""))
    t_sc = time_score(guess, truth["minute"])
    conclusion = round(50 * who_ok + 20 * method_ok + 15 * motive_ok + 0.15 * t_sc)

    key_found = len(key & disc) / max(1, len(key))
    overall = len(disc) / max(1, len(bundle["evidence"]))
    ev_score = round(100 * (0.7 * key_found + 0.3 * overall))

    cited = [e for e in acc.get("evidence", []) if e in disc]
    good = [e for e in cited if e in key or roles.get(e) in ("support", "exculpatory", "decoy_resolution", "context")]
    bad = [e for e in cited if e in decoy_ev]
    if cited:
        interp = round(100 * len(good) / len(cited)) - 15 * len(bad)
        interp = min(100, interp + (10 if len([e for e in cited if e in key]) >= 3 else 0))
    else:
        interp = 15
    interp = max(0, interp)

    innocent_h = [h for h in hypotheses if h.get("suspect_ref") and h["suspect_ref"] != perp and h["suspect_ref"] in decoy_suspects]
    leads = 100 - 10 * len(innocent_h) - 15 * len(bad) - (30 if acc.get("suspect_ref") in decoy_suspects else 0)
    leads = max(0, min(100, leads))

    act_ev = [t["evidence_id"] for t in truth["actual_timeline"]]
    tl_cov = len([e for e in act_ev if e in disc]) / max(1, len(act_ev))
    timeline = round(0.6 * t_sc + 0.4 * 100 * tl_cov)

    v = View(bundle)
    sus = ea.suspicion(v)
    ranked = [r for r, _ in sorted(sus.items(), key=lambda kv: -kv[1]["score"])]
    rank_sc = 100 if ranked and ranked[0] == perp else 55 if perp in ranked[:2] else 20
    ch = ha.chain(v, acc.get("suspect_ref") or perp)["strength"]
    suspects = round(0.5 * rank_sc + 0.5 * ch) if who_ok else round(0.4 * rank_sc)

    cats = {"evidence": ev_score, "interpretation": interp, "false_leads": leads, "timeline": timeline,
            "suspects": suspects, "conclusion": conclusion}
    total = round(sum(cats[k] * w for k, w in WEIGHTS.items()) / sum(WEIGHTS.values()))
    if not who_ok:
        total = min(total, 59)
    return {"categories": cats, "total": total, "grade": grade(total), "who_correct": who_ok,
            "motive_correct": motive_ok, "method_correct": method_ok, "time_score": t_sc,
            "decoys_cited": bad, "innocent_hypotheses": len(innocent_h), "solved": who_ok}
