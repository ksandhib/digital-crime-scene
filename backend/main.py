"""DIGITAL CRIME SCENE AI - FastAPI entry point.

Run:  python -m uvicorn backend.main:app --port 8047
Everything is local. No cloud API is used; Ollama is optional.
"""
import os
import threading
import webbrowser
from typing import List, Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import engine
from .ai import ollama
from .database.db import ROOT

PORT = int(os.environ.get("DCS_PORT", "8047"))
FRONTEND = os.path.join(ROOT, "frontend")

app = FastAPI(title="Digital Crime Scene AI", version="1.0")


@app.on_event("startup")
def _startup():
    engine.init()
    if os.environ.get("DCS_OPEN_BROWSER") == "1":
        threading.Timer(1.2, lambda: webbrowser.open(f"http://127.0.0.1:{PORT}")).start()


@app.exception_handler(engine.GameError)
async def _game_error(request: Request, exc: engine.GameError):
    return JSONResponse({"detail": str(exc)}, status_code=exc.code)


class NewCase(BaseModel):
    difficulty: str = "MEDIUM"
    type: str = "RANDOM"
    seed: Optional[str] = None


class Heartbeat(BaseModel):
    elapsed: int


class Examine(BaseModel):
    ref: str


class Question(BaseModel):
    question: str


class HypothesisIn(BaseModel):
    title: str
    suspect_ref: Optional[str] = None
    kind: str = "who"
    notes: str = ""


class Pin(BaseModel):
    evidence_id: str
    side: str  # support | against | none


class Accusation(BaseModel):
    suspect_ref: Optional[str] = None
    motive_key: Optional[str] = None
    method_key: Optional[str] = None
    time: str = ""
    evidence: List[str] = []
    explanation: str = ""
    elapsed: Optional[int] = None


class SaveName(BaseModel):
    name: str


class Settings(BaseModel):
    use_llm: Optional[bool] = None
    model: Optional[str] = None


# ---------------------------------------------------------------- system
@app.get("/api/health")
def health():
    return engine.health()


@app.get("/api/settings")
def get_settings():
    return {"settings": ollama.settings(), "ollama": ollama.status()}


@app.post("/api/settings")
def set_settings(s: Settings):
    ollama.save_settings({k: v for k, v in s.dict().items() if v is not None})
    return {"settings": ollama.settings(), "ollama": ollama.status()}


@app.get("/api/achievements")
def achievements():
    return engine.achievements()


# ---------------------------------------------------------------- cases
@app.get("/api/cases")
def cases():
    return engine.list_cases()


@app.post("/api/case/new")
def new_case(body: NewCase):
    return engine.create_case(body.difficulty, body.type, body.seed)


@app.post("/api/import")
async def import_case(request: Request):
    return engine.import_case(await request.json())


@app.get("/api/saves")
def saves():
    return engine.list_saves()


@app.post("/api/saves/load")
def load_save(body: SaveName):
    return engine.load_save(body.name)


@app.get("/api/case/{cid}")
def overview(cid: str):
    return engine.overview(cid)


@app.delete("/api/case/{cid}")
def delete_case(cid: str):
    return engine.delete_case(cid)


@app.post("/api/case/{cid}/retry")
def retry(cid: str):
    return engine.retry_case(cid)


@app.post("/api/case/{cid}/heartbeat")
def heartbeat(cid: str, body: Heartbeat):
    return engine.heartbeat(cid, body.elapsed)


@app.get("/api/case/{cid}/feed")
def feed(cid: str):
    return engine.feed_list(cid)


@app.get("/api/case/{cid}/options")
def options(cid: str):
    return engine.options(cid)


# ---------------------------------------------------------------- investigation data
@app.get("/api/case/{cid}/evidence")
def evidence(cid: str, type: str = "ALL", q: str = "", flag: str = ""):
    return engine.evidence_list(cid, type, q, flag)


@app.get("/api/case/{cid}/evidence/{eid}")
def evidence_detail(cid: str, eid: str):
    return engine.evidence_detail(cid, eid)


@app.post("/api/case/{cid}/examine")
def examine(cid: str, body: Examine):
    return engine.examine(cid, body.ref)


@app.get("/api/case/{cid}/graph")
def graph(cid: str):
    return engine.graph(cid)


@app.get("/api/case/{cid}/timeline")
def timeline(cid: str):
    return engine.timeline(cid)


@app.get("/api/case/{cid}/people")
def people(cid: str):
    return engine.people(cid)


@app.get("/api/case/{cid}/devices")
def devices(cid: str):
    return engine.devices(cid)


@app.get("/api/case/{cid}/locations")
def locations(cid: str):
    return engine.locations(cid)


@app.get("/api/case/{cid}/entity/{ref}")
def entity(cid: str, ref: str):
    return engine.entity(cid, ref)


@app.get("/api/case/{cid}/analysis")
def analysis(cid: str):
    return engine.analysis(cid)


@app.get("/api/case/{cid}/chain/{ref}")
def chain(cid: str, ref: str):
    return engine.chain(cid, ref)


# ---------------------------------------------------------------- NEXUS, hypotheses
@app.post("/api/case/{cid}/nexus")
def nexus(cid: str, body: Question):
    return engine.ask_nexus(cid, body.question)


@app.get("/api/case/{cid}/nexus/history")
def nexus_history(cid: str):
    return engine.nexus_history(cid)


@app.get("/api/case/{cid}/hypotheses")
def hypotheses(cid: str):
    return engine.hypotheses(cid)


@app.post("/api/case/{cid}/hypotheses")
def add_hypothesis(cid: str, body: HypothesisIn):
    return engine.add_hypothesis(cid, body.title, body.suspect_ref, body.kind, body.notes)


@app.post("/api/case/{cid}/hypotheses/{hid}/pin")
def pin(cid: str, hid: int, body: Pin):
    return engine.pin_hypothesis(cid, hid, body.evidence_id, body.side)


@app.delete("/api/case/{cid}/hypotheses/{hid}")
def del_hypothesis(cid: str, hid: int):
    return engine.delete_hypothesis(cid, hid)


# ---------------------------------------------------------------- ending
@app.post("/api/case/{cid}/accuse")
def accuse(cid: str, body: Accusation):
    return engine.accuse(cid, body.dict())


@app.get("/api/case/{cid}/result")
def result(cid: str):
    return engine.reveal_payload(cid)


@app.post("/api/case/{cid}/solution")
def solution(cid: str):
    return engine.solution(cid)


@app.get("/api/case/{cid}/report", response_class=HTMLResponse)
def report(cid: str):
    return HTMLResponse(engine.report_html(cid))


@app.get("/api/case/{cid}/export")
def export(cid: str):
    data = engine.export_case(cid)
    return JSONResponse(data, headers={"Content-Disposition": f'attachment; filename="case_{cid}.json"'})


@app.post("/api/case/{cid}/save")
def save(cid: str):
    return engine.save_snapshot(cid)


# ---------------------------------------------------------------- frontend
@app.get("/")
def index():
    return FileResponse(os.path.join(FRONTEND, "index.html"))


app.mount("/", StaticFiles(directory=FRONTEND), name="frontend")
