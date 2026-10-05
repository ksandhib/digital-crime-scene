# DIGITAL CRIME SCENE AI
*Investigate. Connect. Reason. Solve.*

A local-first, fully fictional digital-investigation game. Each case is procedurally generated from a hidden ground truth (who, why, how, when). You investigate evidence, find contradictions, avoid red herrings, ask the AI assistant NEXUS, and make a final accusation.

## Run it (Windows)
Double-click **START.BAT**. It checks Python (3.9+), creates `.venv`, installs `fastapi` and `uvicorn` on first run, checks/starts Ollama if installed, starts the server and opens http://127.0.0.1:8047. Close the window to stop.

Manual: `python -m venv .venv`, install `requirements.txt`, then `python -m uvicorn backend.main:app --port 8047`.

## Ollama (optional)
Without Ollama, NEXUS uses a deterministic evidence engine and the game is fully playable. With Ollama running, NEXUS rephrases its facts with your local model (pick it in Settings). LLM output is rejected if it cites evidence you have not found.

## How to play
1. Pick difficulty and type (or enter a seed such as `D7A9-42F1`) and generate a case.
2. Start from the initial evidence. **Examine** devices, people and locations (graph node, People/Devices/Locations tabs) to recover more.
3. Use the Graph (evidence board), Timeline, NEXUS, and Hypotheses. Contradictions and correlations appear in the live feed as you find them.
4. Check evidence reliability (HIGH / MEDIUM / LOW / QUESTIONABLE). Anonymous tips and unverified images are leads, not proof.
5. Make the final accusation: who, why, when, how, and the evidence you rely on. Then the truth is revealed and scored.

The same seed and difficulty always rebuild the same case. Cases persist in `data/digital_crime_scene.db`. Export/import, snapshots (`saves/`) and HTML reports (`reports/`, print to PDF from the browser) are included.

## Design notes
- **Hidden truth**: stored in `case_truth`, never returned by any player-facing endpoint until the case is closed or the solution is viewed.
- **Case Director** (`backend/agents/case_director.py`) regenerates any case where the real culprit is not the top suspect, the culprit has no complete evidence chain, or a red herring is too strong.
- **Deterministic agents**: timeline, evidence (contradictions, correlations, suspicion), relationship (graph), hypothesis (chains) analysts. LLM only phrases answers.
- **RAG**: dependency-free TF-IDF over discovered evidence (`backend/rag`). ChromaDB can be swapped in.
- **Scope**: purely simulated. No real hacking, credentials, malware or surveillance.

## Layout
`frontend/` (HTML/CSS/JS, no CDN) · `backend/` (FastAPI, SQLite, `agents/`, `case_generator/`, `rag/`, `ai/`, `scoring/`) · `data/` `cases/` `reports/` `saves/` · `tests/`

## Tests
`python tests/test_generator.py 30` validates generated cases across all difficulties; `python tests/test_engine.py` plays full cases through the engine.
