import sys, os, tempfile, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ["DCS_DB"] = os.path.join(tempfile.mkdtemp(), "t.db")
from backend import engine
engine.init()
for diff in ["EASY","MEDIUM","HARD","EXPERT"]:
    ov = engine.create_case(diff, "RANDOM", "D7A9-42F1")
    cid = ov["id"]; print(diff, cid, ov["evidence"], ov["title"][:40])
    # public API must never leak truth
    for fn in (engine.overview, engine.graph, engine.timeline, engine.analysis, engine.people, engine.devices, engine.locations, engine.hypotheses):
        blob = json.dumps(fn(cid), default=str)
        assert "perpetrator_ref" not in blob and "key_evidence" not in blob, fn
    # examine everything repeatedly
    refs = [d["ref"] for d in ov["devices"]] + [l["ref"] for l in ov["locations"]] + [s["ref"] for s in ov["suspects"]] + [w["ref"] for w in ov["witnesses"]] + [ov["victim"]["ref"]]
    for _ in range(12):
        for r in refs: engine.examine(cid, r)
    ov2 = engine.overview(cid); print("  discovered", ov2["evidence"], "conf", ov2["confidence"])
    a = engine.analysis(cid); print("  lead", a["lead"], "chain", a["chain"]["strength"], "contr", len(a["contradictions"]), "corr", len(a["correlations"]))
    for q in ["Who had access to the stolen file?", "What happened between 23:00 and 23:30?", "Which evidence contradicts "+ov["suspects"][0]["name"].split()[0]+"'s statement?", "What evidence is missing?", "Which suspects had opportunity?", "Show me the strongest evidence", "Show me everything connected to "+ov["suspects"][1]["name"].split()[0], "Who was near Laptop #04 at 23:20?", "USB"]:
        r = engine.ask_nexus(cid, q); assert r["text"]
    print("  nexus ok:", r["intent"], r["evidence"][:3])
    e0 = engine.evidence_list(cid)["items"]; print("  evidence list", len(e0), "search USB", len(engine.evidence_list(cid, q="USB")["items"]))
    for it in e0[:60]: engine.evidence_detail(cid, it["id"])
    p = engine.people(cid); sp = [x for x in p if x["kind"]=="suspect"]; print("  top susp", sorted([(x["suspicion"], x["name"]) for x in sp])[-1])
    engine.add_hypothesis(cid, "test", a["lead"]["ref"]); print("  hyp", engine.hypotheses(cid)[0]["analysis"]["confidence"])
    engine.add_hypothesis(cid, "other", ov["suspects"][0]["ref"])
    res = engine.accuse(cid, {"suspect_ref": a["lead"]["ref"], "motive_key": "financial", "method_key": "own_workstation", "time": "23:10", "evidence": [i["id"] for i in a["strongest"][:4]], "explanation": "He had access and the badge log contradicts him.", "elapsed": 600})
    print("  RESULT", res["headline"], res["grade"], res["total"], res["categories"], res["achievements"], res["messages"])
    html = engine.report_html(cid); assert "Actual solution" in html
    d = engine.export_case(cid); engine.import_case(json.loads(json.dumps(d))); 
print(engine.achievements()[:3]); print("ALL OK")
