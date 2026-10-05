"""Tiny Ollama client using only the standard library. Every call fails soft: if Ollama
is not running the game keeps working with deterministic answers."""
import json
import os
import urllib.request

from ..database.db import DATA_DIR

HOST = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434")
SETTINGS_PATH = os.path.join(DATA_DIR, "settings.json")
DEFAULTS = {"use_llm": True, "model": "", "timeout": 40}


def settings():
    s = dict(DEFAULTS)
    try:
        with open(SETTINGS_PATH, encoding="utf-8") as f:
            s.update(json.load(f))
    except (OSError, ValueError):
        pass
    return s


def save_settings(new):
    s = settings()
    for k in DEFAULTS:
        if k in new:
            s[k] = new[k]
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
        json.dump(s, f, indent=2)
    return s


def models():
    try:
        with urllib.request.urlopen(HOST + "/api/tags", timeout=1.5) as r:
            return [m["name"] for m in json.load(r).get("models", [])]
    except Exception:
        return None  # None = unreachable


def status():
    ms = models()
    s = settings()
    chosen = s["model"] if s["model"] in (ms or []) else (ms[0] if ms else "")
    return {"online": ms is not None, "models": ms or [], "model": chosen, "use_llm": s["use_llm"]}


def generate(system, prompt, max_tokens=320):
    """Return generated text or None when Ollama is unavailable / disabled."""
    st = status()
    if not (st["online"] and st["model"] and st["use_llm"]):
        return None
    body = json.dumps({"model": st["model"], "stream": False, "system": system, "prompt": prompt,
                       "options": {"temperature": 0.2, "num_predict": max_tokens}}).encode()
    req = urllib.request.Request(HOST + "/api/generate", data=body, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=settings()["timeout"]) as r:
            return (json.load(r).get("response") or "").strip() or None
    except Exception:
        return None
