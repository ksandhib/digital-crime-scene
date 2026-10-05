"""Case Director - consistency checks run on every generated case before the player sees it.

Guarantees (with ALL evidence discovered):
  * the real perpetrator has the highest suspicion, by a margin that depends on difficulty
  * the perpetrator's evidence chain is complete, nobody else's is
  * the perpetrator has a critical alibi contradiction
  * red herrings never outrank the solution
"""
from .common import View
from . import evidence_analyst as ea
from . import hypothesis_analyst as ha
from ..case_generator.content import DIFF


def validate(bundle):
    truth = bundle["truth"]
    v = View(bundle, all_discovered=True)
    contr = ea.contradictions(v)
    sus = ea.suspicion(v, contr)
    perp = truth["perpetrator_ref"]
    ranked = sorted(sus.items(), key=lambda kv: -kv[1]["score"])
    report = {"ranked": [(r, s["score"]) for r, s in ranked]}
    if ranked[0][0] != perp:
        return False, dict(report, reason="perpetrator not top")
    second = ranked[1][1]["score"] if len(ranked) > 1 else 0
    if ranked[0][1]["score"] - second < DIFF[bundle["case"]["difficulty"]]["margin"]:
        return False, dict(report, reason="margin too small")
    if not any(c["person"] == perp and c["kind"] == "alibi" and c["severity"] == "CRITICAL" for c in contr):
        return False, dict(report, reason="no critical contradiction for perpetrator")
    ch = ha.chain(v, perp)
    if ch["strength"] < 80:
        return False, dict(report, reason="perpetrator chain weak %s" % ch["strength"])
    for ref in sus:
        if ref != perp and ha.chain(v, ref)["strength"] >= 70:
            return False, dict(report, reason="innocent chain too strong")
    return True, report
