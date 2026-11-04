"""VibeEduTwin learner store: SQLite memory + ChromaDB writing samples.

SQLite (learners.db) holds structured records:
  - learners: one row per student
  - skill_scores: skill name -> score snapshots over time
  - drafts: writing drafts plus the feedback given
  - event_log: audit trail of practice-loop steps (Write -> Diagnose -> ...)
  - teacher_sets: published practice sets served in learners' Practice

ChromaDB (./chroma_db) holds one collection per learner,
named "learner_<id>_writing", so the twin can search past work.

Usage:
  python learner_store.py     # runs the sample test at the bottom
"""

import json
import os
import sqlite3
from datetime import date, datetime, timezone
from pathlib import Path

# --- Locations ----------------------------------------------------------------
ROOT = Path(__file__).resolve().parent
# VIBEEDUTWIN_DB / VIBEEDUTWIN_CHROMA redirect storage (tests, demo resets).
DB_PATH = Path(os.environ.get("VIBEEDUTWIN_DB") or ROOT / "learners.db")
CHROMA_DIR = Path(os.environ.get("VIBEEDUTWIN_CHROMA") or ROOT / "chroma_db")


# --- Schema -------------------------------------------------------------------
DISCIPLINES = ("Sciences", "Technology", "Medicine", "Arts & Humanities",
               "Commerce & Management", "Social Sciences")

# Pre-curriculum discipline names -> current names (data migration).
OLD_DISCIPLINES = {"Science": "Sciences", "Humanities": "Arts & Humanities",
                   "Commerce": "Commerce & Management"}

SCHEMA = """
CREATE TABLE IF NOT EXISTS learners (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    year TEXT NOT NULL,
    subject TEXT NOT NULL,
    language_preference TEXT NOT NULL,
    discipline TEXT NOT NULL DEFAULT 'Sciences',
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS skill_scores (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    learner_id INTEGER NOT NULL REFERENCES learners(id),
    skill_name TEXT NOT NULL,
    score REAL NOT NULL,
    reason TEXT,
    evidence TEXT,
    date TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS drafts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    learner_id INTEGER NOT NULL REFERENCES learners(id),
    content TEXT NOT NULL,
    feedback TEXT NOT NULL,
    source TEXT NOT NULL DEFAULT 'typed',
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS event_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    learner_id INTEGER NOT NULL REFERENCES learners(id),
    step TEXT NOT NULL,
    agent TEXT NOT NULL,
    tool TEXT NOT NULL,
    result TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS teacher_sets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    skill TEXT NOT NULL,
    level INTEGER NOT NULL,
    discipline TEXT,
    items TEXT NOT NULL,
    request TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS practice_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    learner_id INTEGER NOT NULL REFERENCES learners(id),
    skill_name TEXT NOT NULL,
    accuracy REAL NOT NULL,
    date TEXT NOT NULL
);
"""


def _utcnow() -> str:
    """Current UTC time as an ISO string for created_at columns."""
    return datetime.now(timezone.utc).isoformat()


def _connect() -> sqlite3.Connection:
    """Open the database, creating the file and tables on first use.

    TEXT is stored and returned as UTF-8 so Indic scripts round-trip intact.
    """
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row  # rows behave like dicts
    conn.text_factory = str  # decode TEXT columns as UTF-8 str, never bytes
    conn.execute('PRAGMA encoding = "UTF-8"')
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA)  # no-op once tables exist
    _ensure_discipline_column(conn)  # migrate pre-discipline databases
    _migrate_discipline_values(conn)  # map pre-curriculum names to current ones
    _ensure_draft_source_column(conn)  # migrate pre-scan databases
    _ensure_skill_detail_columns(conn)  # migrate pre-feedback databases
    return conn


def _ensure_discipline_column(conn: sqlite3.Connection) -> None:
    """Add learners.discipline to databases created before it existed.

    Existing rows (e.g. the demo learner) default to Science.
    """
    columns = [row[1] for row in conn.execute("PRAGMA table_info(learners)")]
    if "discipline" not in columns:
        conn.execute(
            "ALTER TABLE learners ADD COLUMN discipline TEXT NOT NULL DEFAULT 'Sciences'"
        )


def _migrate_discipline_values(conn: sqlite3.Connection) -> None:
    """Rewrite pre-curriculum discipline names to the current six."""
    for old, new in OLD_DISCIPLINES.items():
        conn.execute("UPDATE learners SET discipline = ? WHERE discipline = ?",
                     (new, old))


def _ensure_draft_source_column(conn: sqlite3.Connection) -> None:
    """Add drafts.source to databases created before Scan my paper.

    Existing rows (typed paragraphs) default to 'typed'.
    """
    columns = [row[1] for row in conn.execute("PRAGMA table_info(drafts)")]
    if "source" not in columns:
        conn.execute(
            "ALTER TABLE drafts ADD COLUMN source TEXT NOT NULL DEFAULT 'typed'"
        )


def _ensure_skill_detail_columns(conn: sqlite3.Connection) -> None:
    """Add skill_scores.reason/evidence (older rows keep NULL = no detail)."""
    columns = [row[1] for row in conn.execute("PRAGMA table_info(skill_scores)")]
    if "reason" not in columns:
        conn.execute("ALTER TABLE skill_scores ADD COLUMN reason TEXT")
    if "evidence" not in columns:
        conn.execute("ALTER TABLE skill_scores ADD COLUMN evidence TEXT")


# --- Learners -----------------------------------------------------------------
def create_learner(name: str, year: str, subject: str, language: str,
                   discipline: str = "Sciences") -> int:
    """Register a learner; returns the new learner id.

    discipline must be one of the six curriculum disciplines.
    """
    if discipline not in DISCIPLINES:
        raise ValueError(
            f"Unknown discipline {discipline!r}. Choose from: {', '.join(DISCIPLINES)}"
        )
    with _connect() as conn:
        cur = conn.execute(
            "INSERT INTO learners (name, year, subject, language_preference,"
            " discipline, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (name, year, subject, language, discipline, _utcnow()),
        )
        return cur.lastrowid


def get_learner(learner_id: int) -> dict | None:
    """Fetch one learner as a dict, or None if the id is unknown."""
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM learners WHERE id = ?", (learner_id,)
        ).fetchone()
        return dict(row) if row else None


def reset_learner(learner_id: int, discipline: str = "Sciences",
                  include_memory: bool = True) -> None:
    """Clear one learner back to no history (demo re-recordings).

    Keeps the learner row (same id) on the given discipline; deletes drafts,
    scores, events, and practice results. Also drops the learner's writing
    collection unless include_memory is False.
    """
    if discipline not in DISCIPLINES:
        raise ValueError(
            f"Unknown discipline {discipline!r}. Choose from: {', '.join(DISCIPLINES)}"
        )
    with _connect() as conn:
        row = conn.execute(
            "SELECT id FROM learners WHERE id = ?", (learner_id,)
        ).fetchone()
        if row is None:
            conn.execute(
                "INSERT INTO learners (id, name, year, subject,"
                " language_preference, discipline, created_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?)",
                (learner_id, "Demo", "10", "English", "Malayalam",
                 discipline, _utcnow()),
            )
        else:
            conn.execute(
                "UPDATE learners SET discipline = ? WHERE id = ?",
                (discipline, learner_id),
            )
        for table in ("skill_scores", "drafts", "event_log",
                      "practice_results"):
            conn.execute(
                f"DELETE FROM {table} WHERE learner_id = ?", (learner_id,)
            )
    if include_memory:
        delete_writing_samples(learner_id)


def delete_writing_samples(learner_id: int) -> None:
    """Drop one learner's writing collection; missing collection is fine."""
    try:
        _get_chroma_client().delete_collection(f"learner_{learner_id}_writing")
    except ValueError:
        pass  # nothing stored yet


# --- Skill scores ---------------------------------------------------------------
def save_skill_scores(learner_id: int, scores_dict: dict,
                      details: dict | None = None) -> None:
    """Save one snapshot of {skill_name: score} stamped with today's date.

    details optionally carries {skill_name: {"reason", "evidence"}} from the
    diagnosis; bumps without details store NULL (shown as level only).
    """
    today = date.today().isoformat()
    details = details or {}
    rows = [(learner_id, skill, float(score),
             (details.get(skill) or {}).get("reason"),
             (details.get(skill) or {}).get("evidence"), today)
            for skill, score in scores_dict.items()]
    with _connect() as conn:
        conn.executemany(
            "INSERT INTO skill_scores (learner_id, skill_name, score, reason,"
            " evidence, date) VALUES (?, ?, ?, ?, ?, ?)",
            rows,
        )


def get_skill_scores(learner_id: int) -> list[dict]:
    """Return all score snapshots for a learner, oldest first."""
    with _connect() as conn:
        rows = conn.execute(
            "SELECT skill_name, score, reason, evidence, date FROM skill_scores"
            " WHERE learner_id = ? ORDER BY date, id",
            (learner_id,),
        ).fetchall()
        return [dict(r) for r in rows]


def save_practice_result(learner_id: int, skill: str, accuracy: float) -> None:
    """Stamp one set accuracy for mastery tracking."""
    with _connect() as conn:
        conn.execute(
            "INSERT INTO practice_results (learner_id, skill_name, accuracy,"
            " date) VALUES (?, ?, ?, ?)",
            (learner_id, skill, float(accuracy), date.today().isoformat()),
        )


def get_practice_results(learner_id: int, skill: str) -> list[dict]:
    """Accuracy history for a skill, oldest first."""
    with _connect() as conn:
        rows = conn.execute(
            "SELECT accuracy, date FROM practice_results"
            " WHERE learner_id = ? AND skill_name = ? ORDER BY date, id",
            (learner_id, skill),
        ).fetchall()
        return [dict(r) for r in rows]


# --- Drafts ---------------------------------------------------------------------
def save_draft(learner_id: int, content: str, feedback: str,
               source: str = "typed") -> int:
    """Save a draft plus its feedback; returns the new draft id."""
    with _connect() as conn:
        cur = conn.execute(
            "INSERT INTO drafts (learner_id, content, feedback, source,"
            " created_at) VALUES (?, ?, ?, ?, ?)",
            (learner_id, content, feedback, source, _utcnow()),
        )
        return cur.lastrowid


def get_drafts(learner_id: int) -> list[dict]:
    """Return all drafts for a learner, oldest first."""
    with _connect() as conn:
        rows = conn.execute(
            "SELECT id, content, feedback, source, created_at FROM drafts"
            " WHERE learner_id = ? ORDER BY id",
            (learner_id,),
        ).fetchall()
        return [dict(r) for r in rows]


def update_draft_feedback(draft_id: int, feedback: str) -> None:
    """Stamp a diagnosis's feedback onto its draft."""
    with _connect() as conn:
        conn.execute(
            "UPDATE drafts SET feedback = ? WHERE id = ?",
            (feedback, draft_id),
        )


def count_drafts_today(learner_id: int) -> int:
    """Paragraphs submitted today (UTC) for the daily goal."""
    with _connect() as conn:
        return conn.execute(
            "SELECT COUNT(*) FROM drafts WHERE learner_id = ?"
            " AND date(created_at) = date('now')",
            (learner_id,),
        ).fetchone()[0]


# --- Event log ------------------------------------------------------------------
def log_event(learner_id: int, step: str, agent: str, tool: str, result: str) -> int:
    """Append one audit row (practice-loop step); returns the new event id."""
    with _connect() as conn:
        cur = conn.execute(
            "INSERT INTO event_log (learner_id, step, agent, tool, result, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (learner_id, step, agent, tool, result, _utcnow()),
        )
        return cur.lastrowid


def get_events(learner_id: int) -> list[dict]:
    """Return the audit trail for a learner, oldest first."""
    with _connect() as conn:
        rows = conn.execute(
            "SELECT step, agent, tool, result, created_at FROM event_log"
            " WHERE learner_id = ? ORDER BY id",
            (learner_id,),
        ).fetchall()
        return [dict(r) for r in rows]


def get_scaffold_events(learner_id: int) -> list[dict]:
    """Return scaffold-ladder rows (tool, result) for a learner, oldest first."""
    with _connect() as conn:
        rows = conn.execute(
            "SELECT tool, result FROM event_log"
            " WHERE learner_id = ? AND step = 'Scaffold' ORDER BY id",
            (learner_id,),
        ).fetchall()
        return [dict(r) for r in rows]


def get_recent_events(learner_id: int, limit: int = 6) -> list[dict]:
    """Return the most recent audit rows (step, agent, tool, result) first."""
    with _connect() as conn:
        rows = conn.execute(
            "SELECT step, agent, tool, result FROM event_log"
            " WHERE learner_id = ? ORDER BY id DESC LIMIT ?",
            (learner_id, limit),
        ).fetchall()
        return [dict(r) for r in rows]


# --- Teacher sets ---------------------------------------------------------------
def save_teacher_set(skill: str, level: int, discipline: str | None,
                     items: list[dict], request_text: str) -> int:
    """Publish a teacher set; returns the new set id. discipline None = all."""
    with _connect() as conn:
        cur = conn.execute(
            "INSERT INTO teacher_sets (skill, level, discipline, items, request,"
            " created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (skill, level, discipline, json.dumps(items, ensure_ascii=False),
             request_text, _utcnow()),
        )
        return cur.lastrowid


def get_teacher_set(skill: str, level: int, discipline: str) -> dict | None:
    """Newest set for a skill + level: discipline-specific wins over generic."""
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM teacher_sets WHERE skill = ? AND level = ?"
            " AND (discipline IS NULL OR discipline = ?)"
            " ORDER BY discipline IS NULL, id DESC LIMIT 1",
            (skill, level, discipline),
        ).fetchone()
        if row is None:
            return None
        found = dict(row)
        found["items"] = json.loads(found["items"])
        return found


# --- Writing samples (ChromaDB, one collection per learner) ----------------------
def _get_chroma_client():
    """Persistent local client (pure-Python backend; see knowledge_base.py)."""
    import chromadb
    from chromadb.config import Settings

    return chromadb.Client(
        Settings(
            is_persistent=True,
            persist_directory=str(CHROMA_DIR),
            chroma_api_impl="chromadb.api.segment.SegmentAPI",
            anonymized_telemetry=False,
        )
    )


def _get_embedding_function():
    """Default embeddings, cached inside the repo instead of the home dir."""
    from chromadb.utils.embedding_functions import ONNXMiniLM_L6_V2

    ef = ONNXMiniLM_L6_V2()
    ef.DOWNLOAD_PATH = ROOT / ".chroma_cache" / "onnx_models" / ef.MODEL_NAME
    return ef


def get_writing_collection(learner_id: int):
    """Open (or create) the ChromaDB collection for one learner's past work."""
    return _get_chroma_client().get_or_create_collection(
        f"learner_{learner_id}_writing",
        embedding_function=_get_embedding_function(),
    )


def save_writing_sample(learner_id: int, content: str, label: str = "draft") -> str:
    """Store a writing sample so the twin can find it later; returns its id."""
    collection = get_writing_collection(learner_id)
    sample_id = f"learner-{learner_id}-{label}-{collection.count() + 1}"
    collection.add(
        ids=[sample_id],
        documents=[content],
        metadatas=[{"learner_id": learner_id, "label": label}],
    )
    return sample_id


def search_writing_samples(learner_id: int, query: str, n_results: int = 3) -> list[dict]:
    """Search one learner's past writing; returns [{text, label, distance}]."""
    collection = get_writing_collection(learner_id)
    if collection.count() == 0:
        return []
    n_results = min(n_results, collection.count())  # hnswlib warns otherwise
    result = collection.query(query_texts=[query], n_results=n_results)
    docs = result.get("documents", [[]])[0]
    metas = result.get("metadatas", [[]])[0]
    distances = result.get("distances", [[]])[0]
    return [
        {"text": doc, "label": meta.get("label"), "distance": dist}
        for doc, meta, dist in zip(docs, metas, distances)
    ]


# --- Sample test ------------------------------------------------------------------
def _sample_test() -> None:
    """Create one learner, save scores + draft + sample, print everything back."""
    learner_id = create_learner("Meera", "10", "English", "Malayalam",
                                discipline="Sciences")
    print(f"Created learner id={learner_id}")

    save_skill_scores(learner_id, {
        "paragraphing": 62,
        "grammar": 55,
        "vocabulary": 70,
    })
    save_draft(
        learner_id,
        content="My favourite festival is Onam. People wear new clothes.",
        feedback="Good topic sentence. Add two supporting details.",
    )
    log_event(learner_id, "Diagnose", "diagnose-agent", "skill-scorer", "grammar=55")
    save_writing_sample(learner_id, "My favourite festival is Onam. People wear new clothes.")

    print("Learner:", get_learner(learner_id))
    print("Scores:", get_skill_scores(learner_id))
    print("Drafts:", get_drafts(learner_id))
    print("Events:", get_events(learner_id))
    print("Memory search:", search_writing_samples(learner_id, "festival clothes"))


if __name__ == "__main__":
    _sample_test()
