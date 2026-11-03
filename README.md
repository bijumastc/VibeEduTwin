# VibeEduTwin — Knowledge Ingest

Practice loop: Write → Diagnose → Bridge → Practise → Grow.
This step builds the retrieval knowledge base from openly licensed books only.

## Setup (Windows PowerShell)

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install --no-cache-dir -r requirements.txt
```

(`--no-cache-dir`: this machine's pip HTTP cache is corrupted and makes
pip hang; bypassing it installs normally.)

First ingest downloads the ~83MB default embedding model once into
`.chroma_cache/` (gitignored, stays inside the repo).

## 1. Add PDFs

The guide PDFs are gitignored, so a fresh clone starts with an empty
`data/knowledge/`. `data/knowledge/manifest.json` is the download list:
41 openly licensed books with exact filenames and verified licenses.
Get them from their open publishers — OpenStax (https://openstax.org),
the Open Textbook Library (https://open.umn.edu), LibreTexts, BCcampus
Pressbooks (https://pressbooks.bccampus.ca), eCampusOntario
(https://ecampusontario.pressbooks.pub), and Writing Spaces
(https://writingspaces.org) — save each PDF in `data/knowledge/` with
the exact manifest filename, then ingest:

```powershell
python scripts/ingest_knowledge.py --reset
```

Filenames and licenses must match `data/knowledge/manifest.json`; the
ingest refuses ND-licensed and unlisted files. See
[data/knowledge/README.md](data/knowledge/README.md) and step 2 below.

## Single-file version

`knowledge_base.py` (repo root) does the whole pipeline in one commented
file: read PDFs → clean → 400-word/50-overlap chunks → tag
(`source, license, subject, skill`) → store in collection `knowledge_base`
→ run the 5-question search test.

```powershell
python knowledge_base.py --reset
```

## Learner store

`learner_store.py` (repo root) keeps per-student state: SQLite
(`learners.db`: learners, skill_scores, drafts, event_log) plus one
ChromaDB collection per learner (`learner_<id>_writing`) for past work.

```powershell
python learner_store.py   # sample test: 1 learner, scores, draft, memory search
```

## Backend API

`main.py` serves the practice loop with FastAPI:

```powershell
.venv\Scripts\python.exe -m uvicorn main:app --reload
```

| Method | Path | Purpose |
|---|---|---|
| POST | `/drafts` | Save a learner paragraph |
| POST | `/diagnose` | Score 7 skills, return weakest |
| GET | `/practice?learner_id=1` | Set for weakest skill + level |
| POST | `/practice/answers` | Score answers, bump skill if ≥80% |
| POST | `/level-check` | Current levels + recent level-ups |
| GET | `/growth?learner_id=1` | Scores for the growth chart |
| POST | `/teacher/practice-sets` | Generate + verify a set |
| GET | `/drafts?learner_id=1` | List drafts with feedback |
| POST | `/twin/ask` | Short scaffolded twin reply |

## Frontend app (mobile-first)

`frontend/` is a Vite + React app: bottom nav (Home, Write, Practice,
My Writing, My Growth), one-question-at-a-time practice, twin side panel
on Write/Practice, growth chart that unlocks after the first level-up.

```powershell
cd frontend
npm install
npm run dev
```

Then open http://localhost:5173 in a browser. The backend must run too
(`uvicorn main:app` from the repo root), and learner 1 must exist
(run `python learner_store.py` once). Point at another backend with
`VITE_API_URL` in `frontend/.env`.

Diagnose/practice use simple heuristic logic for now (each scorer is one
function in `main.py`); the twin system prompt is defined there for the
Muse Spark step. Every endpoint logs to the event log ("How it decided").

## 2. Ingest into ChromaDB

```powershell
python scripts/ingest_knowledge.py --reset
```

- Cleans headers, page numbers, index lines.
- Splits into ~400-word chunks with 50-word overlap.
- Tags: `source, chapter, license, subject, skill`.
- Stores in `./chroma_db/`, collection `vibeedutwin_knowledge`.
- Refuses files without an open license in the manifest.

Note: the scripts use ChromaDB's Python segment backend
(see `scripts/chroma_setup.py`) because the default Rust backend fails
to open its database file on this machine (sqlite code 14).

## 3. Test search

```powershell
python scripts/test_search.py
```

Runs 5 sample student questions and prints top-3 hits with metadata.

## 4. Unit tests

```powershell
python -m pytest tests/ -q
```
