"""VibeEduTwin FastAPI backend: the practice loop as HTTP endpoints.

Loop: Write -> Diagnose -> Bridge -> Practise -> Grow.

Endpoints:
  POST /learners             sign up a learner (name + discipline)
  POST /drafts               save a learner paragraph
  POST /diagnose             score a draft on 7 skills, find the weakest
  GET  /curriculum           disciplines + module unlock states for a learner
  GET  /curriculum/modules   one module's verified rule + example excerpts
  GET  /practice             practice set for the weakest skill + level
  POST /practice/answers     score answers, bump the skill if they did well
  POST /level-check          report current levels and recent level-ups
  GET  /growth               current skill scores for the growth chart
  GET  /independence         hint-use trend ("working more independently")
  POST /scaffold/start        hand out a module task (try with no help)
  POST /scaffold/help         one rung up the ladder (question/hint/excerpt)
  POST /scaffold/show         "Show me now": jump to the book excerpt
  POST /scaffold/steps        "Just show me the steps": the worked answer
  POST /scaffold/rewrite      accept the learner's rewrite
  WS   /ws/transcribe         stream mic audio, get the transcript
  POST /teacher/practice-sets  generate a set from library excerpts + verify it
  POST /teacher/publish        publish a set into learners' Practice
  GET  /events                 latest audit rows for the How-it-decided panel

Every endpoint writes to the event log (learner_store), so the app can
later show "How it decided". Skill scoring is simple heuristic logic for
now; each scorer is one function so Muse Spark can replace it later.

Run:
  .venv\\Scripts\\python.exe -m uvicorn main:app --reload     (dev)
  .venv\\Scripts\\python.exe main.py                          (direct)
"""

import asyncio
import json
import os
import re
from datetime import datetime, timezone
import urllib.error
import urllib.request
import uuid
from pathlib import Path

from fastapi import FastAPI, HTTPException, WebSocket
from fastapi.encoders import jsonable_encoder
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

import learner_store as store

# --- Twin system prompt ---------------------------------------------------------
# Used by every LLM call once Muse Spark is wired in. The twin speaks as the
# learner's future self, guides instead of answering, in simple English only.
TWIN_SYSTEM_PROMPT = (
    "You are the learner's future self: a confident student who writes well. "
    "Speak warmly, in second person, with specific next steps. Never pretend "
    "you shared their struggle. Reply ONLY in simple, short "
    "English: basic words, short sentences. Never write in Malayalam or any "
    "other language. Every word you write must be simple English. "
    "NEVER write full answers, "
    "paragraphs, or essays for the learner - only hints, questions, and tiny "
    "examples they must complete themselves. If the learner writes in any "
    "language except English, first reflect their idea back in "
    "simple English starting with 'You are saying that...', then give one "
    "English sentence starter for them to complete. Be honest, never "
    "sycophantic. No generic praise: "
    "never write 'great job', 'excellent', 'amazing', or any other empty "
    "compliment. Praise only when you can name the exact improvement, "
    "compared with the previous draft. Always state the main problem first, "
    "plainly and kindly, quoting the learner's own English words, or "
    "reflecting their idea in simple English when they did not write in "
    "English. Never call weak "
    "writing good. Use at most one positive sentence per reply. Keep every "
    "reply to 2-4 short sentences."
)

# --- Constants ------------------------------------------------------------------
SKILLS = ["Grammar", "Vocabulary", "Sentence structure", "Paragraphing",
          "Argument", "Using sources", "Academic tone"]

# Score -> level bands. Keep in sync with level_for_score().
# Practice scoring is per answer now (see ASSESS_BUMPS with the assessor):
# each answer earns 0-2 and the set bump is the sum, so no pass threshold.

# Issued practice sets: set_id -> {learner_id, skill, level, answers}.
# In-memory for the demo; a real deployment would persist these.
ISSUED_SETS: dict = {}

# Open scaffold attempts: attempt_id -> {learner_id, discipline, module, skill,
# level, step, q_index}. Steps: try -> question -> hint -> excerpt -> rewrite
# -> done ("Show me now" jumps straight to excerpt).
SCAFFOLD_ATTEMPTS: dict = {}

class UTF8JSONResponse(JSONResponse):
    """JSON responses as raw UTF-8 with an explicit charset.

    ensure_ascii=False keeps Indic scripts (Malayalam, Tamil, ...) as
    readable UTF-8 instead of \\uXXXX escapes.
    """
    media_type = "application/json; charset=utf-8"

    def render(self, content) -> bytes:
        return json.dumps(
            jsonable_encoder(content),
            ensure_ascii=False,
            allow_nan=False,
            indent=None,
            separators=(",", ":"),
        ).encode("utf-8")


app = FastAPI(title="VibeEduTwin", default_response_class=UTF8JSONResponse)

# Let the Vite dev server (port 5173) call this API from the browser.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- Request models ---------------------------------------------------------------
class LearnerIn(BaseModel):
    name: str = Field(min_length=1, description="The learner's name")
    year: str = "10"
    subject: str = "English"
    language: str = "Malayalam"
    discipline: str = Field(description="One of the six curriculum disciplines")


class DraftIn(BaseModel):
    learner_id: int
    content: str = Field(min_length=1, description="The learner's paragraph")
    source: str = "typed"  # typed | scan


class DraftScanIn(BaseModel):
    learner_id: int
    image: str = ""  # base64 photo (data URL), compressed under 1 MB


class DiagnoseIn(BaseModel):
    learner_id: int
    draft_id: int | None = None   # either draft_id or raw content is required
    content: str | None = None


class PolishIn(BaseModel):
    learner_id: int
    draft_id: int = 0
    content: str = ""  # Learn path: polish the rewritten attempt, no draft


class PracticeAnswersIn(BaseModel):
    learner_id: int
    set_id: str
    answers: dict[str, str]  # item_id -> learner's answer


class LevelCheckIn(BaseModel):
    learner_id: int


class TeacherSetIn(BaseModel):
    request: str = Field(min_length=1, description="Plain-language practice request")
    note: str = Field(default="", description="Optional one-line steer for regenerate")


class TeacherPublishIn(BaseModel):
    request: str = ""
    skill: str
    level: int
    discipline: str | None = None
    items: list[dict]


class TwinAskIn(BaseModel):
    learner_id: int
    message: str = Field(min_length=1, description="Learner's chat message")
    screen: str = "write"  # where the panel was opened: write | practice


class ScaffoldStartIn(BaseModel):
    learner_id: int
    discipline: str
    module: str


class ScaffoldHelpIn(BaseModel):
    learner_id: int
    attempt_id: str
    attempt_text: str = ""


class ScaffoldShowIn(BaseModel):
    learner_id: int
    attempt_id: str


class ScaffoldStepsIn(BaseModel):
    learner_id: int
    attempt_id: str


class ScaffoldRewriteIn(BaseModel):
    learner_id: int
    attempt_id: str
    text: str = ""


class DeleteDataIn(BaseModel):
    learner_id: int


# --- Helpers ----------------------------------------------------------------------
def level_for_score(score: float) -> int:
    """Map a 0-100 skill score to levels 1-5."""
    if score < 20:
        return 1
    if score < 40:
        return 2
    if score < 60:
        return 3
    if score < 80:
        return 4
    return 5


def latest_scores(learner_id: int) -> dict[str, float]:
    """Most recent score per skill (rows come back oldest-first)."""
    scores: dict[str, float] = {}
    for row in store.get_skill_scores(learner_id):
        scores[row["skill_name"]] = row["score"]
    return scores


def weakest_skill(scores: dict[str, float]) -> tuple[str, int]:
    """Weakest skill and its level (1-5); defaults to Paragraphing L1 with no data."""
    if not scores:
        return "Paragraphing", 1
    skill = min(SKILLS, key=lambda s: scores.get(s, 0))
    return skill, level_for_score(scores.get(skill, 0))


LEVEL_NAMES = {1: "Starter", 2: "Elementary", 3: "Intermediate",
               4: "Upper-Intermediate", 5: "Advanced"}

SESSION_WORD_TARGETS = {1: 50, 2: 80, 3: 120, 4: 160, 5: 200}
SESSIONS_PER_DAY = 3
GUIDED_ACTIVITIES = 6  # guided mode until 6 activities or Level 3


def overall_level(levels: dict[str, int]) -> int:
    """The learner's working level: the weakest skill's level (min 1)."""
    return min([levels.get(s, 1) for s in SKILLS] or [1])


def session_state(learner_id: int) -> dict:
    """Today's session: unit at their level, 3 steps, sessions done of 3.

    Derived from today's drafts and practice sets in time order, so
    leaving mid-session resumes exactly where they stopped: step 1 needs
    a paragraph on their discipline topic meeting the word target, step 2
    a rewrite, step 3 one practice set.
    """
    learner = store.get_learner(learner_id) or {}
    scores = latest_scores(learner_id)
    levels = {s: level_for_score(v) for s, v in scores.items()}
    overall = overall_level(levels)
    today = datetime.now(timezone.utc).date().isoformat()
    events = [(d["created_at"], "draft", d["content"])
              for d in store.get_drafts(learner_id)
              if d["created_at"][:10] == today]
    events += [(r["created_at"], "practice", "")
               for r in store.get_events(learner_id)
               if r["tool"] == "score_answers" and r["step"] == "Practise"
               and r["created_at"][:10] == today]
    events.sort(key=lambda e: (e[0], 0 if e[1] == "draft" else 1))
    target = SESSION_WORD_TARGETS[overall]
    sessions_done, step, just_completed = 0, 1, False
    for _, kind, content in events:
        if sessions_done >= SESSIONS_PER_DAY:
            break
        just_completed = False
        if step == 1 and kind == "draft" and len(content.split()) >= target:
            step = 2
        elif step == 2 and kind == "draft":
            step = 3
        elif step == 3 and kind == "practice":
            sessions_done += 1
            step = 1
            just_completed = True
    complete = sessions_done >= SESSIONS_PER_DAY
    discipline = learner.get("discipline") or "Sciences"
    return {"level": overall, "level_name": LEVEL_NAMES[overall],
            "topic": DISCIPLINE_TOPICS.get(discipline, "your studies"),
            "target": target, "sessions_done": sessions_done,
            "sessions_target": SESSIONS_PER_DAY, "step": step,
            "steps_done": [True, True, True] if complete
            else [step > 1, step > 2, False],
            "just_completed": just_completed and not complete,
            "started": bool(events)}


# Future-self next steps: specific, forward-looking, no shared struggle.
TWIN_NEXT_STEPS = {
    "Grammar": "checking the verbs in your first sentence",
    "Vocabulary": "replacing one vague word like 'nice'",
    "Sentence structure": "joining two short lines with 'and'",
    "Paragraphing": "fixing the first sentence",
    "Argument": "adding one reason with 'because'",
    "Using sources": "naming where one idea came from",
    "Academic tone": "replacing one chatty word",
}


def twin_note(weakest: str) -> str:
    """Short future-self note: specific next step, never shared struggle."""
    step = TWIN_NEXT_STEPS.get(weakest, TWIN_NEXT_STEPS["Paragraphing"])
    return f"You will get this: start by {step}."


# One friendly action per skill for the Home "next win" card.
NEXT_WIN_ACTIONS = {
    "Grammar": "Fix one verb ending",
    "Vocabulary": "Swap one vague word for an exact one",
    "Sentence structure": "Join two short lines with 'because'",
    "Paragraphing": "Make your first sentence say your main idea",
    "Argument": "Add one reason with 'because'",
    "Using sources": "Name one source",
    "Academic tone": "Swap one chatty word for a calm one",
}

# Signs the paragraph tries to use evidence or facts.
_EVIDENCE_SIGNS = ("according to", "says", "said", "study", "studies",
                   "research", "report", "reports", "book", "percent", "%",
                   "fact", "facts", "data", "survey")


def _tries_evidence(text: str) -> bool:
    """True when the paragraph attempts evidence: facts, figures, sources."""
    lowered = (text or "").lower()
    return bool(re.search(r"\d", lowered)) or any(
        sign in lowered for sign in _EVIDENCE_SIGNS)


def _first_words(text: str, n: int) -> str:
    """First n words; an ellipsis marks a cut (quotes stay short)."""
    words = (text or "").split()
    if len(words) <= n:
        return " ".join(words)
    return " ".join(words[:n]) + " …"


def next_win_skill(levels: dict[str, int], text: str) -> str:
    """The Home focus skill: weakest of the six craft skills first.

    Using sources wins only when it is the weakest AND the paragraph
    tries evidence or facts, or every other skill is already Level 3+.
    """
    six = [s for s in SKILLS if s != "Using sources"]
    weakest_six = min(six, key=lambda s: (levels.get(s, 1),
                                          SKILLS.index(s)))
    others_high = all(levels.get(s, 1) >= 3 for s in six)
    if levels.get("Using sources", 1) <= levels.get(weakest_six, 1) \
            and (_tries_evidence(text) or others_high):
        return "Using sources"
    return weakest_six


# Collection written by the scripts pipeline (see scripts/ingest_knowledge.py).
# study_material tries the single-file pipeline's collection first, then this.
SCRIPTS_KB_COLLECTION = "vibeedutwin_knowledge"


def _query_guides(query_text: str, n_results: int = 2) -> tuple[list, list]:
    """Raw (documents, metadatas) for a query from either KB collection.

    Returns ([], []) when no guides are ingested yet.
    """
    try:
        import knowledge_base as kb  # local import: only needed here

        client = kb.get_chroma_client(kb.DEFAULT_DB_DIR)
        for name in (kb.COLLECTION_NAME, SCRIPTS_KB_COLLECTION):
            try:
                collection = client.get_collection(
                    name, embedding_function=kb.get_embedding_function()
                )
            except Exception:
                continue  # collection not built yet -> try the next one
            if collection.count() == 0:
                continue
            result = collection.query(
                query_texts=[query_text], n_results=n_results
            )
            return (result.get("documents", [[]])[0],
                    result.get("metadatas", [[]])[0])
        return [], []
    except Exception:
        return [], []  # no guides ingested yet


def _query_guide_chunks(skill: str, n_results: int = 2) -> tuple[list, list]:
    """Raw (documents, metadatas) for a skill from either KB collection."""
    return _query_guides(f"{skill} academic writing", n_results)


def study_material(skill: str, n_results: int = 2) -> list[dict]:
    """Pull guide snippets for a skill from either KB collection; [] if unavailable."""
    docs, metas = _query_guide_chunks(skill, n_results)
    return [
        {"source": m.get("source"), "skill": m.get("skill"),
         "license": m.get("license"), "text": (d or "")[:400]}
        for d, m in zip(docs, metas)
    ]


def first_sentences(text: str, n: int = 3) -> str:
    """Trim text to its first n sentences for a short Learn card rule."""
    parts = [p.strip() for p in re.split(r"(?<=[.!?])\s+", (text or "").strip())]
    return " ".join(p for p in parts[:n] if p)


# Shown whenever the library has no suitable excerpt. Rules and examples are
# never generated or invented: they come from ChromaDB or this message shows.
NO_VERIFIED_EXAMPLE = "No verified example in our library yet."


# Fragments counted as damage. Short ones are never legitimate standalone
# words (vice/duct/port almost never are in writing guides); long ones are
# word-tails ("product" -> "pr oduct").
_DMG_FRAGS = ("ed|es|ly|ng|nd|nt|th|ou|ti|ts|st|sy|ny|ch|sh|wh|ck|gh|"
              "ry|ty|dy|py|qu|un|ing|dir|der|ter|ect|rect|vice|duct|port|ce|"
              "ow|ur|rt|ort|oduct|rvice|edures|ocedures|cedures|dures|ures")
_DMG_LONG = ("oduct|rvice|edures|ocedures|cedures|dures|ures|ing|der|ter|"
             "ect|rect")
# Split two-letter words. PASS_A runs before the single-letter rules (these
# would misglue otherwise: "an d cons" must heal left, not to "andcons");
# PASS_B runs after ("a t est" must heal right to "a test", not "at est").
# Case-insensitive with an uppercase-next guard so initials survive ("A S").
# The guard stays case-sensitive ((?-i:...) - without it the IGNORECASE flag
# would block every repair followed by a letter).
_PASS_A = (r"a nd|an d|i s|u s|u p|i t|o n|e nd|e ach|e very|e ven|"
            r"e xample|e specially|e ither|e ffect|e ffort|e vidence|e xact|"
            r"e xcept|e xplain|e arly|e asy|e nough|e ntire|e ssay")
_PASS_B = (r"o f|t o|i n|a t|b e|y ou|y our|o r|yo u|you r|fo r|ou r|"
           r"o ur|d o|g o|n o|m y|w e|h e|he re|s o|i f|i ts|a m|a s|p m|"
           r"o ld|o ff|o ut|u se|u pon|a re|a ll|a n|a ction|be gin|beg in|"
           r"ta ke|tak en|"
           r"ma ke|li ke|ti me|na me|sa me|ca me|be come|bec ome|beco me|"
           r"be fore|bef ore|befo re|be tween|bet ween|betw een|writ ten|"
           r"wri tten|wr itten|writt en|"
           r"th at|tha t|th is|th ey|th em|th en|th ere|th eir|th ose|th ink|"
           r"th ing|th rough|wh at|wha t|wh en|wh ere|whe re|wh ich|whi ch|"
           r"wh ile|whi le|ev en|ev ery|eve ry|al l|wit h|ha ve|fr om|fro m|"
           r"bu t|be cause|bec ause|beca use|becau se|wo uld|wou ld|woul d|"
           r"wi ll|wil l|wo rds|wor ds|wo rd|wor d|ca t|cu t|no t|do ne|h as|"
           r"w as|we re|the y|the m|the re|the ir|th an|tho se|th ese|"
           r"thr ough|thro ugh|thi nk|thin k|ge t|se t|le t|me t|"
           r"a bout|a fter|a gain|a cross|a lso|a lways|a nother|a round|"
           r"a bove|a long|e xample|e specially|e ither|e ffect|e ffort|"
           r"e vidence|e xact|e xcept|e xplain|e arly|e asy|e nough|"
           r"e ntire|e ssay|i nto|i dea|i mportant|i nclude|i nformation|"
           r"o ther|o nly|o ften|o rder|o rganize|u nder|u ntil|u seful|"
           r"u sual|u nit|y ear|y et|y oung|r eport|r eports|r esearch|"
           r"r esult|r esults|r eader|r eaders|r eview|r eviews|r eason|"
           r"r easons|r ule|r ules|es say|es says|a ny|an y|a ge|"
           r"pr actice|r ent|nar rate|we ak|wea k")


def _normalize_text_marks(text: str) -> str:
    """ASCII-fold the punctuation PDF extraction leaves behind."""
    marks = {"\u201c": '"', "\u201d": '"', "\u2018": "'", "\u2019": "'",
             "\u2013": "-", "\u2014": " - ", "\u2026": "...", "\xa0": " ",
             "\u2022": " ", "\u25aa": " ", "\u25cf": " ", "\u25e6": " ",
             "\u25e7": " ", "\u2023": " ", "\u2043": " ", "\u2219": " ",
             "\u00b7": " ", "\uf0b7": " ", "\ufffd": ""}
    text = text.replace(" \ufffd ", ". ")  # bullet marker is a boundary
    for old, new in marks.items():
        text = text.replace(old, new)
    text = text.replace("  ", " ")
    text = re.sub(r"\s+([.,;:!?])", r"\1", text)  # "aviation ."
    text = re.sub(r"([A-Za-z0-9])\(", r"\1 (", text)  # "guides(http"
    text = re.sub(r"(\w)- (\w)", r"\1\2", text)  # split words: "con- clude"
    # Letter-spacing damage, in dependency order. Single heads exclude
    # a/e/i/o/u/x/y ("a cat", "e mail", "x ray" stay) and r ("or not" stays).
    text = re.sub(rf"\b({_PASS_A})\b(?!\s+(?-i:[A-Z]))",
                  lambda m: m.group(1).replace(" ", ""), text, flags=re.IGNORECASE)
    text = re.sub(r"([A-Za-z]{2,}) (s)\b(?!-)", r"\1\2", text)  # plurals first
    text = re.sub(r"\b([b-df-hj-npqsvwz]) ([a-z]{2,})\b", r"\1\2", text)
    # Head "t" refuses a two-letter left word: "No t ever" heals to "Not
    # ever" via PASS_B, not to "No tever".
    text = re.sub(r"(?<![A-Za-z][A-Za-z] )\b(t) ([a-z]{2,})\b", r"\1\2", text)
    # Uppercase heads at sentence starts ("T able" -> "Table"). Mid-sentence
    # singles stay ("Box B contains" is a label, not damage). The guard keeps
    # compounds ("B team", "B minus", "T cell", "T shirt", "B flat", "Z axis",
    # "B vitamin", "C note", "B mark", "B average", "C section") safe.
    text = re.sub(r"(?:^|(?<=[.!?]\s))([B-DF-HJ-NPQSTVWZ]) "
                  r"((?!(?i:team\w*|side|plot\w*|plan\w*|movi\w+|grade\w*|"
                  r"level\w*|day|game\w*|minus|plus|string\w*|cells?|shirts?|"
                  r"section|flat|sharp|natural|axis|axes|vitamin\w*|note\w*|"
                  r"marks?|average\w*|tests?)\b)[A-Za-z]{2,})\b",
                  r"\1\2", text)
    # "ing" splits ("Sing ing") glue left, unless "incredible" follows.
    # Runs before "ly" so "are ly ing" heals to "are lying".
    text = re.sub(r"([a-z]{2,}) (ing)\b(?!-)(?!\s+credib\w*\b)", r"\1\2", text)
    for tail in ("ow", "n", "ur", "ou", "ck", "gh", "ng", "nd",
                 "nt", "ts", "ly", "ce", "uct", "rt", "ort", "oduct",
                 "rvice", "edures", "ocedures", "cedures", "dures", "ures",
                 "ect", "rect", "suasive", "suasively", "zation", "sation",
                 "tization", "ization", "isation", "tion", "sion", "ssion",
                 "ize", "ise", "yzed", "ysed", "ying", "ied", "ies", "yer",
                 "yers", "ers", "ation", "ition", "ction", "ay",
                 "egories", "ojects", "ge", "oduction", "duction",
                 "troduction", "ferent", "wings", "ilva", "ent",
                 "dination", "lem", "ance", "ormation", "rmation",
                 "mation", "formation", "ctions"):
        text = re.sub(rf"([A-Za-z]{{2,}}) ({tail})\b(?!-)", r"\1\2", text)
    # Tail "e" ("Th e"), but never after be/he/me/we/us ("Be early" stays).
    text = re.sub(r"(?<!\b(?i:be|he|me|we|us) )([A-Za-z]{2,}) (e)\b(?!-)",
                  r"\1\2", text)
    # Tail "t" ("repor t"), but never before "o": "And t o" heals right
    # ("And to" via PASS_B), not to "Andt o".
    text = re.sub(r"([a-z]{2,}) (t)\b(?!-)(?!\s+o\b)", r"\1\2", text)
    # "ed"/"es" with guards: "ed ucation" and "es say" split the other way.
    text = re.sub(r"([a-z]{2,}) (ed)\b(?!-)(?!\s+ucat(?:ion|or)\w*\b)",
                  r"\1\2", text)
    text = re.sub(r"([a-z]{2,}) (es)\b(?!-)(?!\s+sa(?:y|ys)\b)", r"\1\2", text)
    text = re.sub(rf"\b({_PASS_B})\b(?!\s+(?-i:[A-Z]))",
                  lambda m: m.group(1).replace(" ", ""), text, flags=re.IGNORECASE)
    text = re.sub(r"('s)([a-z])", r"\1 \2", text)  # "author'sfull"
    text = re.sub(r"(n't)([a-z])", r"\1 \2", text)  # "Don'twaste"
    for old, new in (("co-ed", "coed"), ("Co-ed", "Coed"), ("CO-ED", "COED")):
        text = text.replace(old, new)
    # Dropped periods ("APA Style Social Sciences generally use APA
    # Humanities ..."). An acronym + capital starts a new sentence unless
    # a style word or journal word follows ("APA Style", "IEEE
    # Transactions" stay).
    text = re.sub(r"\b([A-Z]{2,})\s+"
                  r"((?!(?:Style|Manual|Guide|Guides|Handbook|Format|"
                  r"Edition|Press|Transactions|Proceedings|Journals?|"
                  r"Magazine|Standards?|Review|Quarterly)\b)[A-Z][a-z]+)",
                  r"\1. \2", text)
    # A pronoun start after a lowercase word is a new sentence ("...
    # Chicago Style They show ..."), unless a quote verb leads ("said
    # They ..." stays). "It" excluded (mid-sentence "It" is usually a
    # typo for "it", and splitting there is worse than keeping it).
    _QUOTE_VERBS = {"said", "says", "say", "writes", "write", "wrote",
                    "notes", "note", "noted", "asks", "ask", "asked",
                    "states", "state", "stated", "claims", "claim",
                    "claimed", "argues", "argue", "argued", "shows",
                    "show", "showed", "suggests", "suggest", "adds",
                    "add", "added", "explains", "explain"}
    text = re.sub(r"(\b[a-z]+)\s+((?:They|He|She|We|You|This|These|Those)\s+[a-z])",
                  lambda m: m.group(0)
                  if m.group(1).lower() in _QUOTE_VERBS
                  else f"{m.group(1)}. {m.group(2)}", text)
    # A style word + The/This + capital ("APA Style The Sciences ...").
    text = re.sub(r"\b(Style|Manual|Guide|Guides|Handbook|Format|Edition)\s+"
                  r"((?:The|This|These|Those)\s+[A-Z][a-z]+)",
                  r"\1. \2", text)
    # A style word + field + lowercase verb ("APA Style Social Sciences
    # generally ..."). A second style word blocks it ("Style Guide
    # update" stays).
    text = re.sub(r"\b(Style|Manual|Guide|Handbook|Format)\s+"
                  r"((?!(?:Guide|Manual|Format|Handbook|Edition|Style|"
                  r"Press|Sheet|Book)\b)[A-Z][a-z]+(?:\s+[A-Z][a-z]+)?"
                  r"(?=\s+[a-z]))",
                  r"\1. \2", text)
    # A closing paren + capital starts a new sentence ("... future)
    # Abstracts ..."): the paren ends a heading or aside.
    text = re.sub(r"(\))\s+([A-Z][a-z]+)", r"\1. \2", text)
    # Doubled content words ("Citations Citations") are heading echoes;
    # doubled function words ("had had", "that that") are grammar.
    _DUP_OK = {"had", "that", "do", "can", "will", "would", "should",
               "could", "may", "might", "must", "shall", "is", "was",
               "are", "were", "be", "been", "it", "you", "we", "they",
               "he", "she", "on", "in", "at", "to", "of", "for", "as",
               "by", "a", "the", "and", "or", "but", "if", "so", "than",
               "then", "when", "while", "with", "from"}
    text = re.sub(r"\b([A-Za-z]{3,})\s+(\1)\b",
                  lambda m: m.group(0)
                  if m.group(1).lower() in _DUP_OK else m.group(1),
                  text)
    # A period without a space ("conventional.Moreover") still ends the
    # sentence. Abbreviations ("U.S.A", "e.g.X") stay glued.
    text = re.sub(r"(?<!e\.g)(?<!i\.e)(?<![A-Z])([.!?])([A-Z][a-z])",
                  r"\1 \2", text)
    return text


# s-endings that are never verbs (for the For-example stub rule).
_S_WORDS = {"his", "this", "that", "these", "those", "us", "as", "is",
            "has", "was", "does", "always", "sometimes", "often",
            "plus", "thus", "across", "unless", "yes", "its",
            "hers", "ours", "yours", "theirs", "thesis", "analysis",
            "basis", "crisis", "diagnosis", "emphasis", "oasis",
            "synopsis", "hypothesis", "species", "series", "news", "lens"}


def _has_verb_signal(sentence: str) -> bool:
    """An auxiliary, modal, -ed/-ing form, scenario framer or s-verb."""
    low = sentence.lower()
    if re.search(r"\b(is|are|was|were|be|been|being|has|have|had|do|does|"
                 r"did|will|would|can|could|should|shall|may|might|must|"
                 r"suppose|imagine|consider|say)\b", low):
        return True
    if re.search(r"\b\w+(ed|ing)\b", low):
        return True
    words = re.findall(r"\b\w+\b", low)
    for index, word in enumerate(words):
        if word.endswith("s") and word not in _S_WORDS and (
                len(words) <= 5 or index < len(words) / 2):
            return True  # early s-word ("zoos ..."); tail nouns ("... products") lie
    return False


def _is_junk_sentence(sentence: str) -> bool:
    """Headers, page numbers and pipe fragments like "| 25 •"."""
    s = sentence.strip()
    if not s or "|" in s:
        return True
    if "\u2192" in s or "\u21d2" in s or "[" in s or "__" in s:
        return True  # outline arrows, bracket insertions, blank lines
    if re.search(r"\b(\w+(?:\s+\w+){1,2})\s+\1\b", s, re.IGNORECASE):
        return True  # repeated-phrase outline runs
    if re.fullmatch(r"[\d\s.)\-–—]+", s):
        return True
    if re.fullmatch(r"(?i)pages?\s+\d+\.?", s):
        return True
    if re.search(r"\b\d+\.\d+\b", s):
        return True  # glued section headers ("9.4 SIGNAL PHRASES ...")
    if not re.search(r"[a-z]", s):
        return True  # ALL-CAPS header lines and fragments
    if re.search(r"(?i)\bchapter\s+\d+", s):
        return True  # syllabus cross-references ("see Chapter 6")
    if re.search(r"(?i)\b(readings|assignments?)\s*:", s):
        return True  # course-schedule headers
    if re.search(r"[A-Z][a-z]+\s+\d{2,3}\s+[A-Z]", s):
        return True  # glued running head ("Essentials 227 Writing")
    if re.search(r"\b(Edition|Chapter|Page|Section|Unit|Part|Volume|Book|"
                 r"Figure|Table)\s+\d{1,4}\s+[a-z]", s):
        return True  # cross-reference ("Edition 233 technical ...")
    if re.fullmatch(rf"(?:{_HEADINGS})(?:\s+[A-Z0-9]+)?[.!]?", s):
        return True  # bare heading remnant ("References", "Appendix A")
    if re.fullmatch(rf"(?:{_HEADINGS})\s*\(.*\)[.!]?", s):
        return True  # heading + paren fragment ("Recommendations (...)")
    if re.match(r"It (should|must)\s+(open|begin|start)\s+(with|by|using)\b", s):
        return True  # pronoun prescription ("It should open with ...")
    if re.match(r"It (should|must)\s+(contain|include)\s+(the\s+)?(data|parts?|"
                 r"thesis|arguments?|claims?|introduction|conclusion|summary|"
                 r"details?|evidence|examples?|citations?|sources?|facts?)\b", s):
        return True  # pronoun prescription ("It should contain data")
    if re.match(r"It (should|must)\s+(follow|state|present|describe|explain|"
                 r"discuss)\s+(a|an|the|this|that|these|those|each|every|all|"
                 r"both|such|same)\b", s):
        return True  # pronoun prescription ("It should follow a ...")
    if re.search(r"(?i)except where otherwise noted|all rights reserved", s):
        return True  # license boilerplate
    if re.search(r"(?i)\b(canvas|blackboard|moodle)\b", s):
        return True  # LMS instructions, not writing samples
    if re.search(r"\b[a-z0-9-]+\.(org|com|edu|net|gov|io)\b", s):
        return True  # link boilerplate ("Access for free at openstax.org")
    if re.search(r"\s\d{1,2}\.$", s):
        return True  # trailing list number ("activities 2.")
    if re.search(r"[a-z]\s+(Based|For|In|On|At|By|With|From|When|If|"
                 r"This|That|These|Those|It|They|He|She|We|You|"
                 rf"{_GLUE_IMPV_CAP})\b", s):
        return True  # glued sentences ("analysis Based on ...")
    if re.match(r"(?i)(its|their|his|her|the|this|that|a|an)\s+"
                r"(?:\w+\s+){0,3}?(purpose|function|role)\b.{0,25}"
                r"\bis\s+(not\s+)?to\b", s):
        return True  # context-needy purpose line ("Its purpose is to ...")
    if re.match(r"[A-Z][a-z]*(able|ible|ive|ful|less)\s+"
                r"((using|with|by|for|from|in|on|of)\b|i\.e\.|e\.g\.)"
                r"(?=\s|$)", s) and "," not in s:
        return True  # bullet fragment ("Supportable using ...")
    if re.match(r"For (example|instance)\b", s) and not _has_verb_signal(s):
        return True  # verbless stub ("For example, in his report ...")
    first_alpha = re.search(r"[A-Za-z]", s)
    if (first_alpha and first_alpha.group(0).islower()
            and not re.match(r"(?i)(e\.g\.|i\.e\.)", s)):
        return True  # mid-sentence chunk fragment
    return False


# Section headings that glue onto the next sentence ("Background Discuss
# the history ..."). Stripped only before a capital (so "Results show ..."
# survives) or with a colon ("Abstract: This study ..." -> the sentence).
_HEADINGS = ("Background|Introduction|Introductions|Methods|Methodology|"
             "Results|Conclusion|Conclusions|Abstract|Summary|Summaries|"
             "Overview|Discussion|Discussions|References|Appendix|"
             "Appendices|Foreword|Preface|Acknowledgements|Acknowledgments|"
             "Glossary|Index|Contents|Findings|Finding|Recommendation|"
             "Recommendations|Analysis|Further Reading|Note|Timeline|"
             "Budget|Schedule|Milestones|Deliverables|Scope|Objectives?|"
             "Cause and [Ee]ffect|Comparison|Contrast|Definition|"
             "Classification|Process|Narration|Description|"
             "Argumentation|Exemplification")


def clean_sentences(doc: str) -> list[str]:
    """Split a raw chunk into cleaned sentences, junk removed."""
    text = _normalize_text_marks(doc or "")
    for abbr in ("e.g.", "i.e.", "Mr.", "Ms.", "Mrs.", "Dr.", "vs.",
                 "U.S.", "U.K.", "St.", "Jr.", "Sr.", "Ph.D.", "M.D.",
                 "B.A.", "M.A.", "a.m.", "p.m.", "A.M.", "P.M.", "Fig.",
                 "Ch.", "Sec.", "Vol.", "No.", "pp.", "al."):
        text = text.replace(abbr, abbr.replace(".", "\x00"))
    cleaned = []
    for part in re.split(r"(?<=[.!?])\s+", text.strip()):
        part = part.replace("\x00", ".")
        part = re.sub(r"^\s*(?:[*o\-]|[0-9]{1,2}[.)])\s+", "", part).strip()
        # Page-number + running-head runs: "290 Suzan Last The study ..."
        part = re.sub(r"^\d{1,4}\s+(?:[A-Z][a-z]+\s+){1,2}(?=[A-Z])", "", part)
        part = re.sub(r"^\d{2,4}\s+(?=[A-Z])", "", part)
        # Doubled numbers are always pagination ("274 8 Analytical ...").
        part = re.sub(r"^\d{1,4}\s+\d{1,4}\s+(?=[A-Z])", "", part)
        part = re.sub(rf"^(?:{_HEADINGS})\s*:\s*", "", part)
        part = re.sub(rf"^(?:{_HEADINGS})\s+(?=[A-Z])", "", part)
        # ALL-CAPS label + colon ("TECHNICAL BACKGROUND: ...", "Q&A: ...").
        part = re.sub(r"^[A-Z][A-Z\d\s&'/\-]{2,}:\s*", "", part)
        # Glued ALL-CAPS header runs: "References CONSTRUCTING OUTLINES An ..."
        run = re.match(r"^((?:[A-Z][A-Za-z&'\-]*\s+){2,})(?=[A-Z])", part)
        if run and len(re.findall(r"\b[A-Z]{2,}\b", run.group(1))) >= 2:
            part = part[run.end(1):]
        part = re.sub(r"\s+", " ", part).strip()
        part = re.sub(r"\s+", " ", part).strip()
        if part and not _is_junk_sentence(part):
            cleaned.append(part)
    return cleaned


def clean_excerpt_text(doc: str) -> str:
    """One cleaned passage from a raw chunk."""
    return " ".join(clean_sentences(doc))


# Words that can legitimately precede "are"/"ere" (plural subjects).
_ARE_OK = {"you", "they", "we", "these", "those", "many", "few", "several",
           "all", "both", "most", "some", "who", "which", "that", "there",
           "here", "where", "what", "so", "nor", "neither", "and", "but",
           "or", "yet", "children", "men", "women", "people", "mice",
           "feet", "teeth", "oxen", "geese", "data", "media", "criteria",
           "phenomena", "fish", "sheep", "deer"}


def _artifact_count(sentence: str) -> int:
    """Letter-spacing damage ("f ollow") PDF extraction sometimes leaves."""
    singles = len(re.findall(r"\b(?![aAI]\b)[A-Za-z]\s+[A-Za-z]", sentence))
    frags = len(re.findall(rf"\b(?:{_DMG_FRAGS})\b(?=\s+[a-z]|[.?!]+$)",
                           sentence))
    frags += len(re.findall(rf"\b(?:{_DMG_LONG})\b(?=-)", sentence))
    mismatch = 0
    for match in re.finditer(r"\b([A-Za-z]+) (are)\b", sentence):
        word = match.group(1).lower()
        if word not in _ARE_OK and not word.endswith("s"):
            mismatch += 1  # "softw are", never "books are"
    mismatch += len(re.findall(r"\b[A-Za-z]+ (ere)\b", sentence))
    typos = len(re.findall(r"\b([b-df-hj-np-tv-zB-DF-HJ-NP-TV-Z])\1[a-z]{2,}\b",
                           sentence))
    return singles + frags + mismatch + typos


def verified_excerpt(query_text: str, sentences: int = 3,
                     prefer_discipline: str | None = None) -> dict:
    """Best library excerpt for a query, with book/chapter/license provenance.

    Returns {"text", "source", "chapter", "license"}; when nothing suitable
    exists, text is NO_VERIFIED_EXAMPLE and provenance is None. Text is
    always cleaned; with prefer_discipline, books matching the discipline
    win over higher-ranked off-topic ones.
    """
    n_results = 8 if prefer_discipline else 3
    docs, metas = _query_guides(query_text, n_results=n_results)
    cands = []
    for rank, (doc, meta) in enumerate(zip(docs, metas)):
        text = " ".join(clean_sentences(doc)[:sentences] if sentences else [])
        if not text.strip():
            continue
        meta = meta or {}
        book = _book_score(meta.get("source"), prefer_discipline) if prefer_discipline else 0
        chunk_ok = _artifact_count(doc or "") < _CHUNK_DIRT_LIMIT
        cands.append((chunk_ok, book, -rank, text, meta))
    if not cands:
        return {"text": NO_VERIFIED_EXAMPLE, "source": None,
                "chapter": None, "license": None}
    _, _, _, text, meta = max(cands, key=lambda c: (c[0], c[1], c[2]))
    return {"text": text, "source": meta.get("source"),
            "chapter": meta.get("chapter"), "license": meta.get("license")}


# Title/subject words that tie a book to a discipline (matched against the
# manifest title first, the file name second).
DISCIPLINE_BOOK_HINTS = {
    "Sciences": ["scien", "technical", "lab", "physics", "chemis", "biolog"],
    "Technology": ["technical", "technolog", "engineer", "professional"],
    "Medicine": ["medic", "health", "nurs", "clinic"],
    "Arts & Humanities": ["literature", "humanit", "arts", "history"],
    "Commerce & Management": ["business", "commerce", "manag", "professional", "communication"],
    "Social Sciences": ["social", "research", "psycholog", "sociolog"],
}


def _book_score(source: str | None, discipline: str | None) -> int:
    """How well a chunk's book matches a discipline (0 when unknown)."""
    if not discipline or discipline not in DISCIPLINE_BOOK_HINTS:
        return 0
    entry = _load_book_manifest().get(source or "", {})
    haystack = f"{entry.get('title', '')} {source or ''}".lower()
    return sum(1 for hint in DISCIPLINE_BOOK_HINTS[discipline] if hint in haystack)


_MANIFEST_CACHE: dict | None = None


def _load_book_manifest() -> dict:
    """filename -> manifest entry (title, license, ...); {} when missing."""
    global _MANIFEST_CACHE
    if _MANIFEST_CACHE is None:
        try:
            path = Path(__file__).resolve().parent / "data" / "knowledge" / "manifest.json"
            raw = json.loads(path.read_text(encoding="utf-8"))
            _MANIFEST_CACHE = {b.get("filename", ""): b for b in raw.get("books", [])}
        except Exception:
            _MANIFEST_CACHE = {}
    return _MANIFEST_CACHE


def humanize_book_title(source: str | None) -> str:
    """A display title from a file name (manifest titles win; this is backup)."""
    name = (source or "").rsplit("/", 1)[-1]
    if name.lower().endswith(".pdf"):
        name = name[:-4]
    name = re.sub(r"[-_]\d{5,}\s*$", "", name)  # trailing id stamps
    name = re.sub(r"[-_]+", " ", name)
    return re.sub(r"\s+", " ", name).strip() or "this guide"


def resolve_book(source: str | None, meta_license: str | None = None) -> dict:
    """{"title", "publisher", "license"} for a chunk source.

    The title is the manifest's real title (never a file name); publisher
    comes from the manifest when recorded, else None and the UI omits it.
    """
    entry = _load_book_manifest().get(source or "", {})
    return {"title": entry.get("title") or humanize_book_title(source),
            "publisher": entry.get("publisher"),
            "license": meta_license or entry.get("license")}


# Definition frames (skipped for examples) and show-frames (preferred).
DEFINITION_MARKERS = ["defin", "refers to", "is called", "is known as",
                      "means that", "is termed"]
# "such as"/"e.g." usually front meta-lists ("such as visual content"),
# while "for example"/"for instance" usually front real samples.
SHOW_BOOSTERS = ["for example", "for instance"]
# Linkers show flow (kept for coherence, never an example elsewhere).
_LINKERS = ("therefore|however|moreover|furthermore|consequently|"
            "nevertheless|nonetheless|accordingly|thus|hence|meanwhile|"
            "instead|otherwise|then|also")
_LINKER_START = re.compile(rf"^(?:{_LINKERS})\b,?|^So,", re.IGNORECASE)
_LINKER_MID = re.compile(rf"\b(?:{_LINKERS})\b")
# Mundane-name starts ("Nikki needs ...") are generic-guide filler, never a
# discipline example. Role subjects (Reader, Writer ...) stay: they address
# the learner. "It takes ..." stays too. Full names ("Marie Curie ...")
# are untouched (two capitals, never matched here).
_MUNDANE_START = re.compile(
    r"^(?:(?:Although|Though|When|While|If|After|Before|Because|"
    r"Since|As)\s+)?"
    r"(?!It\b)(?!(?:Reader|Writer|Student|Teacher|Author|Researcher|"
    r"Scientist|Doctor|Engineer|Manager|Leader|Experiment|Study|"
    r"Trial|Survey|Project|Report|Essay|Paper|Data|Results)\b)"
    r"[A-Z][a-z]+\s+"
    r"(?:needs?|needed|wants?|wanted|likes?|liked|loves?|loved|"
    r"hates?|hated|goes?|went|buys?|bought|"
    r"makes(?!\s+(?:clear|evident|apparent|plain)\b)|made|takes?|took|"
    r"gets?|got|gives?|gave|says?|said|thinks?|thought|feels?|felt|"
    r"eats?|ate|drinks?|drank|sleeps?|slept|walks?|walked|runs?|ran)\b")
# Glossary frames ("Statistics: Factual ...") define, never show. Example
# frames and genre section labels (Methods:, Results: ...) stay.
_GLOSSARY = re.compile(
    r"^(?!Example:|Methods?:|Results?:|Abstract:|Introduction:|"
    r"Discussion:|Conclusion:|References?:|Appendix:|Works Cited:)"
    r"[A-Z][a-z]+(?:\s+[A-Za-z]+){0,2}:\s+[A-Z]")
# Hedge starts ("Maybe ...") never show the thing.
_HEDGE_START = re.compile(r"^(?:Maybe|Perhaps)\b")
# Weak opinion frames ("It is important ...") never show the thing,
# except in genre modules where enumeration can show report form.
_WEAK_START = re.compile(
    r"^(?:It is (?:important|necessary|essential)|"
    r"It is (?:apparent|clear|obvious|evident) that|"
    r"There (?:are|is))\b")
# Conditional advice ("If you use ...") tells, never shows.
_IF_START = re.compile(r"^If\b")
# Dangling demonstratives ("These steps ...") need prior sentences the
# isolated card never shows.
_THIS_START = re.compile(r"^(?:This|These|Those|Such)\b")
# Qualifier frames ("For the most part ...") hedge, never show.
_QUAL_START = re.compile(
    r"^(?:For the most part|In general|On the whole|By and large)\b")
# Bare "It" dangles ("It reveals ..."); "It takes ..." is a keeper.
_IT_START = re.compile(r"^It\b(?!\s+takes?\b)")
# Textbook stage directions ("In this section you will ...").
_TEXTBOOK_YOU = re.compile(r"^In this (?:section|chapter|unit),? you\b")
# Emphasis caps ("ONE clear purpose ..."); citation acronyms stay.
_CAPS_START = re.compile(
    r"^(?!(?:APA|MLA|IEEE|Chicago|Harvard|CSE|AMA)\b)[A-Z]{2,}\b")
# Question-word starts are fragments or how-tos (real questions are
# filtered before scoring, so whatever remains never shows).
_QW_START = re.compile(r"^(?:Who|What|Where|When|Why|How)\b")
# Reader addresses ("As you write ...", "You need ...") tell, never show.
_YOU_START = re.compile(r"^(?:As you|When you|While you|You|Your)\b")
# Dangling place frames ("In each of these cases ...").
_ANAPHOR_PP = re.compile(r"^(?:In each of these|In these|In those|In such)\b")
# First-person anecdotes ("I went hiking ..."); the "i.e." guard keeps
# the Latin abbreviation safe.
_I_START = re.compile(r"^I\b(?!\.\s*e)(?!\s+(?:argue|claim)\b)",
                       re.IGNORECASE)
# Opinion frames mid-sentence (", it is clear that ...").
_MID_WEAK = re.compile(
    r", it is (?:important|necessary|essential)\b|"
    r", it is (?:apparent|clear|obvious|evident) that\b", re.IGNORECASE)
# Heading fragments ("... LEARNING OUTCOMES."). Citation acronyms after
# citation verbs ("uses IEEE.") stay.
_CAPS_END = re.compile(
    r"(?:^|\s)(?:(\S+)\s+)?([A-Z]{2,}(?:\s+[A-Z]{2,}){0,2}\b[.!?]?$)")
_CAPS_END_KEEP = {"uses", "use", "follows", "follow", "requires",
                  "require", "cites", "cite", "per", "in"}


def _is_caps_end(sentence: str) -> bool:
    """A trailing all-caps run that is not a cited acronym."""
    m = _CAPS_END.search(sentence or "")
    if not m:
        return False
    prev = (m.group(1) or "").lower().rstrip(",;:")
    return prev not in _CAPS_END_KEEP
# Presenter frames ("Here are some examples ...") point, never show.
_HERE_START = re.compile(r"^Here (?:are|is)\b")
# Reader advice ("you ... should ...", "Students should ...",
# "references should be flush ...").
_YOU_SHOULD = re.compile(
    r"\byou\b.{0,20}\bshould\b|\bshould\b.{0,20}\byou\b|"
    r"\b(?:students|writers|readers|learners|authors|researchers|"
    r"references|citations?|sources?|entries|titles?|headings?|margins?|"
    r"fonts?|pages?|paragraphs?|images|figures|tables|charts|graphs|"
    r"diagrams|photos|illustrations)\b"
    r".{0,20}\bshould\b", re.IGNORECASE)
# Demonstrative "that" + domain noun ("that contract") dangles; "that" +
# verb ("that highlights") is a relative clause and stays.
_THAT_NOUN = re.compile(
    r"\bthat\s+(?:contract|report|study|essay|paper|case|result|finding|"
    r"claim|argument|point|idea|method|approach|process|system|text|"
    r"book|article|section|chapter|paragraph|sentence|thesis|topic)\b",
    re.IGNORECASE)
# Reader addressed mid-sentence ("you provide ...").
_YOU_MID = re.compile(
    r"\byou\s+(?:provide|develop|write|use|need|should|must|can|will|may|"
    r"interpret|present|discuss|describe|explain|show|cite|cites|cited|"
    r"care|feel|help)\b",
    re.IGNORECASE)
# News events ("COVID-19", "during the pandemic") are not writing samples.
_NEWS_EVENT = re.compile(
    r"covid|coronavirus|(?:during|in|since|after|before|amid)\s+"
    r"(?:the\s+)?pandemic\b", re.IGNORECASE)
# Vague kind-talk ("this kind of information").
_VAGUE_KIND = re.compile(
    r"this kind of (?:information|thing|stuff|data)|"
    r"these kinds of (?:information|thing|stuff|data)", re.IGNORECASE)
# Textbook purpose frames ("For our purposes here ...").
_PURPOSES = re.compile(r"^[Ff]or (?:our|my|the) purposes\b")
# "In your ..." always addresses the reader.
_IN_YOUR = re.compile(r"^In your\b")
# Counted disease stats ("350,000 deaths", "20 million infections")
# are news, never writing samples. Uncounted claims ("Smoking causes
# deaths") stay: those can be thesis form.
_COUNTED_DISEASE = re.compile(
    r"\d[\d,]*\s+(?:million|billion|thousand\s+)?(?:\w+\s+)?"
    r"(?:deaths?|infections?|cases)\b", re.IGNORECASE)
# Year settings ("By the end of 2020 ...") set news scenes.
_YEAR_START = re.compile(
    r"^(?:In|By) \d{4}\b|^(?:In|By) the (?:end|middle|start) of \d{4}\b")
# "Other ..." always needs an antecedent the card never shows.
_OTHER_START = re.compile(r"^Other\b")
# Vague "Some ..." subjects never show strongly.
_SOME_START = re.compile(r"^Some\b")
# "below"/"above" point outside the isolated card, except measurements
# ("below zero" stays).
_BELOW_PTR = re.compile(
    r"\b(?:below|above)\b(?![\s-]+(?:zero|freezing|average|normal)\b)")
# Bare years ("(1973)", "2018") are citations or dates, never samples.
_YEAR_PAREN = re.compile(r"\b(?:19|20)\d{2}\b")
# Keyword stuffing ("Topic Sentence Reasoning Strategy ...").
_KEYWORD_RUN = re.compile(r"^(?:[A-Z][a-z]+\s+){3,}")
# Attribution fragments ("... Wikimedia Commons, Public Domain") are credits.
_CREDITS = re.compile(
    r"wikimedia|public domain|\bcc by\b|copyright|photo by|image by|"
    r"figure by|courtesy of", re.IGNORECASE)
# Punctuation starts (") ...") are mid-fragments.
_PUNCT_START = re.compile(r"^[\042'\]\)]")
# Dangling "them" needs an antecedent the card never shows.
_THEM_MID = re.compile(r"\bthem\b", re.IGNORECASE)
# "your ..." always addresses the reader.
_YOUR_MID = re.compile(r"\byour\b", re.IGNORECASE)
# Pronoun starts dangle ("They are positions ..."); "We recommend ..."
# stays (recommendations are report form).
_PRON_START = re.compile(r"^(?:They|He|She)\b")
_WE_START = re.compile(r"^We\b(?!\s+recommend\b)")
# Author addresses the reader ("I encourage you ...") instead of showing.
# "We recommend ..." stays everywhere: recommendations are report form.
# "I argue/claim/show ..." stay too: stance-taking is thesis form.
_META_ADDRESS = re.compile(
    rf"^(?:(?:{_LINKERS}),?\s+)?"
    r"(?:I\s+(?:encourage|suggest|recommend|invite|ask|urge|discuss|"
    r"describe|explain|examine|explore|consider|outline|summarize)|"
    r"We\s+(?:encourage|suggest|invite|ask|urge))\b", re.IGNORECASE)
# Genre words that promote a sentence for genre modules only ("This lab
# report examines ..."). Plurals-only where the singular is a verb
# ("result in") or gerund ("finding sources"); lab takes no digits.
_GENRE_SIGNAL = re.compile(
    r"\breports?\b|\bessays?\b|\bintroduction\b|\babstract\b|\bmethods?\b|"
    r"\bresults\b|\bfindings\b|\bexperiments?\b|\blaboratory\b|"
    r"\blab\b(?!\s*\d)|\bdata\b|\bcase[\s-]stud(y|ies)\b|\bpatients?\b|"
    r"\bproposal\b|\bcosts?\b|\bbenefits?\b|\bexecutive\b|"
    r"\bspecifications?\b|\bprocedures?\b|\bmanual\b|\bthesis\b|"
    r"\barguments?\b|\bmethodology\b|\bliterature review\b")
# Imperatives that also betray glued sentences mid-text ("conclusion
# Indicate ..."). Drops the ones that double as proper nouns or UI labels
# ("Schindler's List", "Edit menu"); hyphen guards keep compounds
# ("Write-Up", "Note-Taking", "Give-and-take") and "Outline View" safe.
_GLUE_IMPV = ("write(?![-])|add|draw|explain|describe|discuss|apply|"
              "implement|identify|analyze|compare|contrast(?!\\s+ratio\\b)|"
              "revise|choose|"
              "create|develop|draft|outline(?! View\\b)|organize|include|"
              "avoid|begin|keep|make(?![-])|take|give(?![-])(?! and take\\b)|"
              "provide|follow(?![-])|note(?![-])|click|formulate|indicate|"
              "conclude|summarize|finish|communicate|recognize|focus|"
              "combine|synthesize|use(?!\\s+cases?\\b)|notice|be|"
              "capitaliz\\w*\\b(?!\\s+on\\b)|have|has")
# Capitalized for the glue rule: a glued second sentence starts uppercase
# ("conclusion Indicate ..."), while lowercase verbs mid-sentence
# ("Details that follow ...") are legitimate and must survive.
_GLUE_IMPV_CAP = "|".join(w[0].upper() + w[1:] for w in _GLUE_IMPV.split("|"))


# Bare imperatives ("Write a report") demoted for genre modules (which want
# samples of the genre, not instructions). "use" excluded ("Use cases" is
# a noun); scenario framers (consider, suppose ...) never included; UI and
# idiom guards keep "Edit menu" and "give and take" safe.
_IMPERATIVES = ("write|add|draw|list|state|explain|describe|discuss|apply|"
                "implement|identify|analyze|compare|contrast(?!\\s+ratio\\b)|"
                "review|revise|edit(?!\\s+menu\\b)|check(?!\\s+box(es)?\\b)|"
                "choose|select(?!\\s+button\\b)|create|develop|draft|outline|"
                "plan|organize|include|avoid|begin|start(?!\\s+menu\\b)|"
                "continue(?!\\s+button\\b)|keep|make|take|"
                "give(?!\\s+and\\s+take\\b)|show|provide|follow|note|name|"
                "press(?!\\s+(release|corps|conference|kit)\\b)|"
                "click(?!\\s+(rates?|through|bait)\\b)|"
                "conclude|concludes(?!\\s+that\\b)|summarize|summarizes|"
                "communicate|communicates|recognize|recognizes|"
                "focus(?!\\s+groups?\\b)|focuses|combine|combines|"
                "synthesize|synthesizes|use(?!\\s+cases?\\b)|uses|"
                "notice|notices|be|capitaliz\\w*\\b(?!\\s+on\\b)|"
                "have|has|"
                "finish(?!\\s+line\\b)|"
                "structure(?=\\s+(?:your|the|a|an|this|that|these|those|each|"
                "every|all|both|such|content|paragraphs?|essays?|reports?|"
                "sentences?|ideas?|details?|sections?|drafts?|arguments?|"
                "points?|notes?|findings?|results?|data|text|paper|work|"
                "writing|response|answer|thoughts)\\b)|"
                "find(?!\\s+of\\b)|pick(?!\\s+of\\b)|locate|formulate|indicate|"
                "search(?!\\s+(results?|engine|history|quer(y|ies)|terms?)\\b)"
                "(?!\\s+and\\s+rescue\\b)")
_NEG_START = ("do not|don't|does not|doesn't|can not|cannot|can't|"
               "will not|won't|should not|shouldn't|never(?!\\s+events?\\b)")
_INSTRUCTION = re.compile(
    rf"^(?:(?:Then|Next(?! draft\b)|First(?! draft\b)|Finally|Now|Also)\s+)?"
    rf"(?:{_IMPERATIVES}|{_NEG_START})\b(?!\s*-)|"
    rf"[,;:]\s+(?:and\s+)?(?:{_IMPERATIVES}|{_NEG_START})\b(?!\s*-)",
    re.IGNORECASE)


def _is_instruction(sentence: str) -> bool:
    """An instruction, not a sample ("Write a report ...")."""
    return bool(_INSTRUCTION.search(sentence or ""))
# Meta-talk about the concept ("the topic sentence should be ...") describes
# instead of showing. The concept must follow the/a/an (so "my thesis is
# that ..." samples survive) with a copula or modal close behind (so "the
# report says sales are rising" samples survive).
_CONCEPTS = (r"topic sentence|thesis( statement)?|theses|paragraph|"
              r"essay|report|coherence|citation|source|procedures?|methods?|"
              r"process(es)?|text|proposal|memo|emails?|letters?|resumes?|"
              r"summary|summaries|abstract")
_CONCEPT_META = re.compile(
    rf"\b(the|a|an)\s+(?:[a-z0-9-]+\s+){{0,2}}({_CONCEPTS})s?\b.{{0,16}}\b(should|must|is|are|"
    rf"was|were|means|indicates|describes|explains|states|presents|defines|"
    rf"outlines|summarizes|combines|consists|comprises|advocates|argues|"
    rf"makes? (a )?(claims?|recommendations?))\b"
    rf"|^(?:[a-z0-9-]+\s+){{0,2}}(?:{_CONCEPTS})s?\b.{{0,16}}\b(should|must|is|"
    r"are|was|were|means|indicates|describes|explains|states|presents|"
    r"defines|outlines|summarizes|combines|consists|comprises|advocates|"
    r"argues|makes? (a )?(claims?|recommendations?))\b")

_STOPWORDS = {"the", "a", "an", "and", "or", "of", "to", "in", "on", "is",
              "are", "was", "it", "for", "with", "that", "this"}


def _show_score(sentence: str, coherence: bool = False,
                genre: bool = False) -> int:
    """2 shows the thing, 1 neutral, 0 never an example.

    Zero covers definitions, meta-talk, glossary frames, mundane-name
    filler, hedges, weak frames, author addresses and instructions.
    Linker starts are zero outside coherence (flow is that module's
    thing); inside coherence a bare "for example" without a linker
    shows illustration, not flow. Genre modules exempt weak frames
    (enumeration can show report form) but drop "for example" lines
    that never name the genre.
    """
    lowered = sentence.lower()
    if any(m in lowered for m in DEFINITION_MARKERS):
        return 0
    if _CONCEPT_META.search(lowered):
        return 0
    if _GLOSSARY.search(sentence):
        return 0
    if _MUNDANE_START.search(sentence):
        return 0
    if _HEDGE_START.search(sentence):
        return 0
    if _META_ADDRESS.search(sentence):
        return 0
    if _WEAK_START.search(sentence) and not genre:
        return 0
    if _IF_START.search(sentence):
        return 0
    if _THIS_START.search(sentence):
        return 0
    if _QUAL_START.search(sentence):
        return 0
    if _IT_START.search(sentence):
        return 0
    if _TEXTBOOK_YOU.search(sentence):
        return 0
    if _CAPS_START.search(sentence):
        return 0
    if _QW_START.search(sentence):
        return 0
    if _YOU_START.search(sentence):
        return 0
    if _ANAPHOR_PP.search(sentence):
        return 0
    if _I_START.search(sentence):
        return 0
    if _MID_WEAK.search(sentence):
        return 0
    if _is_caps_end(sentence):
        return 0
    if _HERE_START.search(sentence):
        return 0
    if _YOU_SHOULD.search(sentence):
        return 0
    if _THAT_NOUN.search(sentence):
        return 0
    if _YOU_MID.search(sentence):
        return 0
    if "provides necessary background" in lowered:
        return 0
    if "sets the stage" in lowered:
        return 0
    if re.search(r"(?:analysis|intro|introduction|thesis|abstract|summary|"
                 r"conclusion|methods|results|discussion|references)\s+"
                 r"comes\s+(?:at the end|first|last)\b", lowered):
        return 0
    if _COUNTED_DISEASE.search(sentence):
        return 0
    if _YEAR_START.search(sentence):
        return 0
    if _OTHER_START.search(sentence):
        return 0
    if _SOME_START.search(sentence):
        return 0
    if _THEM_MID.search(sentence):
        return 0
    if _YOUR_MID.search(sentence):
        return 0
    if "uses a version of" in lowered or "use a version of" in lowered:
        return 0
    if "is designed to" in lowered:
        return 0
    if _BELOW_PTR.search(sentence):
        return 0
    if _YEAR_PAREN.search(sentence):
        return 0
    if _KEYWORD_RUN.search(sentence):
        return 0
    if _CREDITS.search(sentence):
        return 0
    if _PUNCT_START.search(sentence):
        return 0
    if _PRON_START.search(sentence):
        return 0
    if _WE_START.search(sentence):
        return 0
    if "number of cases" in lowered:
        return 0
    if _NEWS_EVENT.search(sentence):
        return 0
    if _VAGUE_KIND.search(sentence):
        return 0
    if _PURPOSES.search(sentence):
        return 0
    if _IN_YOUR.search(sentence):
        return 0
    if _is_instruction(sentence):
        return 0
    if _LINKER_START.search(sentence):
        return 1 if coherence else 0
    if any(b in lowered for b in SHOW_BOOSTERS):
        if coherence and not _LINKER_MID.search(lowered):
            return 0
        if genre and not _GENRE_SIGNAL.search(lowered):
            return 0
        return 2
    return 1


def _overlaps_rule(sentence: str, rule_text: str) -> bool:
    """True when a candidate repeats the rule text (never show both)."""
    a = set(re.findall(r"[a-z]+", sentence.lower())) - _STOPWORDS
    b = set(re.findall(r"[a-z]+", (rule_text or "").lower())) - _STOPWORDS
    if not a or not b:
        return True
    return len(a & b) / min(len(a), len(b)) >= 0.6


# Chunks with this much raw letter-spacing damage have more hiding in
# them (damage clusters by page), so their sentences lose.
_CHUNK_DIRT_LIMIT = 3


def select_showing_example(query_base: str, genre: str, discipline: str,
                           rule_text: str, genre_boost: bool = False,
                           coherence_boost: bool = False) -> dict:
    """One cleaned example sentence that SHOWS the thing, with provenance.

    Prefers showing passages from discipline-matching books, never repeats
    the rule text, and falls back to NO_VERIFIED_EXAMPLE with nulls. With
    genre_boost (genre modules), sentences naming genre parts outrank
    generic ones; definitions, meta-talk, glossary frames, mundane-name
    filler, hedges, instructions and (outside coherence) linker starts
    stay at zero either way.
    """
    docs, metas = _query_guides(f"{query_base} example {genre}", n_results=8)
    cands = []
    for rank, (doc, meta) in enumerate(zip(docs, metas)):
        meta = meta or {}
        book = _book_score(meta.get("source"), discipline)
        chunk_ok = _artifact_count(doc or "") < _CHUNK_DIRT_LIMIT
        for sent in clean_sentences(doc):
            if (len(sent) < 35 or sent.endswith("?")
                    or _overlaps_rule(sent, rule_text)
                    or not re.search(r"[.!?][\"']?$", sent)):
                continue
            show = _show_score(sent, coherence=coherence_boost,
                               genre=genre_boost)
            if genre_boost and show >= 1 and _GENRE_SIGNAL.search(sent.lower()):
                show += 2
            cands.append({"sent": sent, "show": show, "book": book,
                          "rank": rank, "meta": meta, "chunk_ok": chunk_ok,
                          "dirty": _artifact_count(sent) > 0})
    pool = ([c for c in cands if c["show"] >= 1 and c["chunk_ok"]
             and not c["dirty"]]
            or [c for c in cands if c["show"] >= 1 and not c["dirty"]]
            or [c for c in cands if c["show"] >= 1])
    if not pool:
        return {"text": NO_VERIFIED_EXAMPLE, "source": None,
                "chapter": None, "license": None}
    best = max(pool, key=lambda c: (not c["dirty"], c["book"], c["show"], -c["rank"]))
    meta = best["meta"]
    return {"text": best["sent"], "source": meta.get("source"),
            "chapter": meta.get("chapter"), "license": meta.get("license")}


def learn_card(skill: str, level: int, discipline: str) -> dict:
    """Build a short Learn card from verified library excerpts only."""
    genre = DISCIPLINE_GENRES[discipline]
    rule = verified_excerpt(f"{skill} writing rule", 2, prefer_discipline=discipline)
    example = select_showing_example(f"{skill} writing", genre, discipline, rule["text"])
    books = []
    for part in (rule, example):
        if part["source"]:
            books.append(resolve_book(part["source"], part["license"]))
    seen, based_on = set(), []
    for book in books:
        if book["title"] not in seen:
            seen.add(book["title"])
            based_on.append(book)
    return {"skill": skill, "level": level, "discipline": discipline,
            "idea": {"text": rule["text"]}, "example": {"text": example["text"]},
            "based_on": based_on}


# --- Curriculum ---------------------------------------------------------------
# Six disciplines, nine ordered modules each. The first eight modules are
# shared; the ninth teaches the discipline's genre (Medicine: writing about
# case reports only - never health advice).
DISCIPLINE_GENRES = {
    "Sciences": "lab report",
    "Technology": "technical report",
    "Medicine": "case report",
    "Arts & Humanities": "essay",
    "Commerce & Management": "business report",
    "Social Sciences": "research report",
}

CURRICULUM_MODULES = [
    {"id": "topic-sentences", "title": "Topic sentences",
     "skill": "Paragraphing", "required_level": 1, "query": "topic sentences"},
    {"id": "thesis-statements", "title": "Thesis statements",
     "skill": "Argument", "required_level": 2, "query": "thesis statements"},
    {"id": "developing-paragraphs", "title": "Developing paragraphs",
     "skill": "Paragraphing", "required_level": 2, "query": "developing paragraphs"},
    {"id": "coherence-flow", "title": "Coherence and flow",
     "skill": "Sentence structure", "required_level": 3, "query": "coherence and flow"},
    {"id": "using-sources", "title": "Using sources",
     "skill": "Using sources", "required_level": 3, "query": "using sources citations"},
    {"id": "mechanics", "title": "Mechanics",
     "skill": "Grammar", "required_level": 1,
     "query": "mechanics punctuation capitals spelling"},
    {"id": "referencing-styles", "title": "Referencing styles",
     "skill": "Using sources", "required_level": 3,
     "query": "referencing styles APA MLA citations"},
    {"id": "academic-vocabulary", "title": "Academic vocabulary",
     "skill": "Vocabulary", "required_level": 2,
     "query": "academic vocabulary formal words linking"},
]


def genre_module(discipline: str) -> dict:
    """The ninth module: writing the discipline's genre."""
    genre = DISCIPLINE_GENRES[discipline]
    return {"id": "genre", "title": (genre + "s").capitalize(),
            "skill": "Academic tone", "required_level": 3,
            "query": f"{genre} introduction opening draft"}


def discipline_modules(discipline: str) -> list[dict]:
    """All nine modules for a discipline, in order."""
    return [*CURRICULUM_MODULES, genre_module(discipline)]


def module_states(discipline: str, scores: dict[str, float]) -> list[dict]:
    """All modules open; the first module of the weakest skill is recommended."""
    weak, _ = weakest_skill(scores)
    states = []
    for module in discipline_modules(discipline):
        level = level_for_score(scores.get(module["skill"], 0))
        states.append({"id": module["id"], "title": module["title"],
                       "skill": module["skill"],
                       "required_level": module["required_level"],
                       "learner_level": level, "unlocked": True,
                       "current": False, "recommended": False})
    for state in states:
        if state["skill"] == weak:
            state["recommended"] = True
            state["current"] = True
            break
    return states


def module_rule_query(module: dict) -> str:
    """ChromaDB query for a module's rule excerpt."""
    return f"{module['query']} rule"


def module_example_query(module: dict, genre: str) -> str:
    """ChromaDB query for a module's discipline example excerpt."""
    return f"{module['query']} example {genre}"


# --- Lessons: one idea per screen -------------------------------------------------
# (a) Hook: scenario, never invented facts. (b) Try first: predict or choose
# (abstract options only, never example sentences). (c) The idea: paraphrase
# of the retrieved excerpt, verified claim by claim. (d) Real example: a
# cleaned book quote. (e) Your turn: the scaffolded task. (f) Why it matters:
# one twin-voiced line. Placeholders: {topic} {genre} {art} {Art}.
LESSON_HOOKS = {
    "topic-sentences": "Imagine opening a {genre} and the first line tells you nothing. Would you keep reading?",
    "thesis-statements": "A friend asks what you think about {topic}. You get one line. What do you say?",
    "developing-paragraphs": "One strong line about {topic} stands alone on a page. Is it enough to convince you?",
    "coherence-flow": "Two true lines about {topic} sit side by side, yet the reader is lost. What is missing between them?",
    "using-sources": "You read a striking claim about {topic} with no source named. Do you trust it?",
    "mechanics": "Your {genre} is strong, but each line starts with a small letter. Will the reader trust it?",
    "referencing-styles": "Two writers make the same point about {topic}. One names a source. Whose line do you trust?",
    "academic-vocabulary": "Your line about {topic} says 'nice' three times. What does the reader actually learn?",
    "genre": "Your {genre} about {topic} lands on a busy reader's desk. What must they see first?",
}

LESSON_TRY = {
    "topic-sentences": {
        "prompt": "A paragraph about {topic} needs a first line. What should that line do?",
        "options": ["Tell the main idea", "List every detail", "Close the topic"],
        "answer": 0,
        "reveal": "The main idea comes first. The next card shows why."},
    "thesis-statements": {
        "prompt": "You hold a view on {topic}. What must your thesis line do?",
        "options": ["State your view", "Describe everything", "Ask a question"],
        "answer": 0,
        "reveal": "A thesis states your view. Details come later."},
    "developing-paragraphs": {
        "prompt": "Your first line states the main idea. What should the next lines do?",
        "options": ["Prove it", "Change the topic", "Repeat it word for word"],
        "answer": 0,
        "reveal": "Each line must prove the first one."},
    "coherence-flow": {
        "prompt": "Two lines about {topic} sit side by side. The reader is lost. What is missing?",
        "options": ["A link between them", "Longer words", "More lines"],
        "answer": 0,
        "reveal": "A linker shows how ideas connect."},
    "using-sources": {
        "prompt": "You borrow an idea about {topic}. What must you add?",
        "options": ["The source name", "Bigger words", "More ideas"],
        "answer": 0,
        "reveal": "Name the source, then use your own words."},
    "mechanics": {
        "prompt": "A line about {topic} has no capital letter and no full stop. What must you fix first?",
        "options": ["The capitals and stops", "The topic", "The length"],
        "answer": 0,
        "reveal": "Capitals and stops come first. Then the words."},
    "referencing-styles": {
        "prompt": "You use an idea about {topic} from a book. What must your line carry?",
        "options": ["The author and year", "A long quote", "A new topic"],
        "answer": 0,
        "reveal": "Author and year point to the source."},
    "academic-vocabulary": {
        "prompt": "Your line about {topic} repeats easy words. What should you do?",
        "options": ["Pick exact words", "Add more lines", "Shorten each word"],
        "answer": 0,
        "reveal": "Exact words carry exact meaning."},
    "genre": {
        "prompt": "You open {art} {genre} about {topic}. What should the first lines give?",
        "options": ["The key facts", "A long greeting", "A joke"],
        "answer": 0,
        "reveal": "Report readers want the key facts first."},
}

LESSON_IDEAS = {
    "topic-sentences": "A topic sentence tells the main idea. It comes first in the paragraph. The other lines follow it.",
    "thesis-statements": "A thesis states your view in one line. It must be debatable, not a plain fact. All your lines prove it.",
    "developing-paragraphs": "One paragraph makes one point. Each line adds proof or detail. Cut lines that wander off.",
    "coherence-flow": "Flow means the reader moves smoothly from line to line. Strong ideas in clear order make flow. Linkers show the links.",
    "using-sources": "Name the source each time you borrow. Citations point to the author. Your own words carry your voice.",
    "mechanics": "Capitals open each sentence. Stops close them. Articles point at the right noun.",
    "referencing-styles": "Name the author in your line. Add the year in brackets. List full details at the end.",
    "academic-vocabulary": "Formal words suit college writing. Exact verbs beat vague ones. Linkers join your ideas.",
    "genre": "{Art} {genre} reports facts in order. It opens with what matters most. Short parts keep it easy to scan.",
}

# One keyword set per claim; a claim passes when ANY keyword appears in the
# excerpt (case-insensitive substring). All claims must pass (AND).
LESSON_IDEA_CLAIMS = {
    "topic-sentences": [
        {"label": "topic sentence", "keywords": ["topic"]},
        {"label": "main idea", "keywords": ["main", "point", "controlling"]},
        {"label": "comes first", "keywords": ["first", "opening", "begin"]},
        {"label": "rest follows", "keywords": ["follow", "rest", "detail", "support"]}],
    "thesis-statements": [
        {"label": "states view", "keywords": ["thesis", "view", "position", "argu"]},
        {"label": "debatable", "keywords": ["debat", "argu", "claim", "opinion"]},
        {"label": "not fact", "keywords": ["fact"]},
        {"label": "lines prove it", "keywords": ["prov", "support", "evidence"]}],
    "developing-paragraphs": [
        {"label": "one point", "keywords": ["paragraph", "point"]},
        {"label": "proof or detail", "keywords": ["proof", "detail", "support", "content", "example"]},
        {"label": "cut wanderers", "keywords": ["cut", "remov", "delet", "unity", "coheren", "relevant", "focus", "topic"]}],
    "coherence-flow": [
        {"label": "flow", "keywords": ["flow"]},
        {"label": "clear order", "keywords": ["smooth", "clear", "order", "structure", "organiz"]},
        {"label": "linkers", "keywords": ["link", "connect", "transition", "cohesi"]}],
    "using-sources": [
        {"label": "name source", "keywords": ["source", "cite", "citation"]},
        {"label": "point to author", "keywords": ["author", "credit", "attribut", "writer"]},
        {"label": "own words", "keywords": ["own", "voice", "paraphras", "word", "paper"]}],
    "mechanics": [
        {"label": "capitals", "keywords": ["capital"]},
        {"label": "stops", "keywords": ["stop", "period", "punctuat"]},
        {"label": "articles", "keywords": ["article", "noun"]}],
    "referencing-styles": [
        {"label": "author", "keywords": ["author"]},
        {"label": "year", "keywords": ["year", "date"]},
        {"label": "reference list", "keywords": ["reference", "list", "bibliograph"]}],
    "academic-vocabulary": [
        {"label": "formal words", "keywords": ["formal", "academic", "word"]},
        {"label": "exact verbs", "keywords": ["exact", "verb", "precise", "vague"]},
        {"label": "linkers", "keywords": ["link", "transition", "connect", "cohesi"]}],
    "genre": [
        {"label": "reports facts", "keywords": ["report", "essay", "paper", "document", "account"]},
        {"label": "opens first", "keywords": ["first", "open", "begin", "introduction", "lead"]},
        {"label": "short parts", "keywords": ["short", "clear", "scan", "concise", "section"]}],
}

LESSON_WHY = {
    "topic-sentences": "You will open with one clear line. Start by naming your topic first.",
    "thesis-statements": "You will hold your piece on one line. Start by stating your view in one sentence.",
    "developing-paragraphs": "You will prove each line before you move on. Start by checking that one line proves the first.",
    "coherence-flow": "You will link every line to the next. Start by adding one linking word.",
    "using-sources": "You will name each source you use. Start by adding one name.",
    "mechanics": "You will write clean lines every time. Start by fixing one capital letter.",
    "referencing-styles": "You will credit every source you use. Start by adding one author and year.",
    "academic-vocabulary": "You will pick exact words with ease. Start by swapping one vague word.",
    "genre": "You will follow the {genre} shape each time. Start by writing one part in its order.",
}


def _select_grounded_idea(module: dict, discipline: str) -> tuple[str, dict | None, bool]:
    """(idea text, excerpt meta or None, authored?) for a lesson.

    Tries rule-query candidates until the grounding verifier passes,
    preferring discipline-matching books; falls back to quoting the top
    excerpt when nothing supports the authored idea.
    """
    docs, metas = _query_guides(module_rule_query(module), n_results=8)
    passing = []
    first_text, first_meta = "", None
    for rank, (doc, meta) in enumerate(zip(docs, metas)):
        cleaned = clean_excerpt_text(doc)
        if not cleaned.strip():
            continue
        meta = meta or {}
        if not first_text:
            first_text = " ".join(clean_sentences(doc)[:2])
            first_meta = meta
        verdict = verify("lesson_idea", {"module": module["id"], "excerpt": cleaned})
        if verdict["pass"]:
            passing.append((_book_score(meta.get("source"), discipline), -rank, meta))
    if passing:
        _, _, meta = max(passing, key=lambda c: (c[0], c[1]))
        return LESSON_IDEAS[module["id"]], meta, True
    if first_text:
        return first_text, first_meta, False
    return NO_VERIFIED_EXAMPLE, None, False


def build_lesson(discipline: str, module_id: str) -> dict:
    """Assemble the six lesson screens for a discipline module."""
    modules = {m["id"]: m for m in discipline_modules(discipline)}
    module = modules[module_id]
    genre = DISCIPLINE_GENRES[discipline]
    topic = DISCIPLINE_TOPICS[discipline]
    idea_text, idea_meta, authored = _select_grounded_idea(module, discipline)
    art = "an" if genre == "essay" else "a"
    if authored:
        idea_text = idea_text.format(genre=genre, topic=topic, art=art, Art=art.capitalize())
    example = select_showing_example(module["query"], genre, discipline,
                                       idea_text,
                                       genre_boost=(module["id"] == "genre"),
                                       coherence_boost=(module["id"] == "coherence-flow"))
    books = []
    if idea_meta and idea_meta.get("source"):
        books.append(resolve_book(idea_meta["source"], idea_meta.get("license")))
    if example["source"]:
        books.append(resolve_book(example["source"], example["license"]))
    seen, based_on = set(), []
    for book in books:
        if book["title"] not in seen:
            seen.add(book["title"])
            based_on.append(book)
    try_block = LESSON_TRY[module_id]
    fmt = {"topic": topic, "genre": genre, "art": art, "Art": art.capitalize()}
    return {"discipline": discipline, "module": module_id, "title": module["title"],
            "skill": module["skill"],
            "hook": LESSON_HOOKS[module_id].format(**fmt),
            "try_first": {"prompt": try_block["prompt"].format(**fmt),
                          "options": [o.format(**fmt) for o in try_block["options"]],
                          "answer": try_block["answer"],
                          "reveal": try_block["reveal"].format(**fmt)},
            "idea": {"text": idea_text},
            "example": {"text": example["text"]},
            "task": scaffold_task(discipline, module_id),
            "why": LESSON_WHY[module_id].format(**fmt),
            "based_on": based_on}


# --- Productive-struggle scaffolding --------------------------------------------
# Ladder per module task: (a) learner tries with no help, (b) twin asks one
# guiding question, (c) a targeted hint on the weak spot, (d) a real book
# excerpt with source, (e) learner rewrites using the pattern. The twin never
# writes the learner's answer: questions ask, hints instruct, excerpts quote.
DISCIPLINE_TOPICS = {
    "Sciences": "evaporation",
    "Technology": "password safety",
    "Medicine": "hand washing",
    "Arts & Humanities": "the freedom struggle",
    "Commerce & Management": "festival sales",
    "Social Sciences": "village life",
}

SCAFFOLD_TASKS = {
    "topic-sentences": "Write one topic sentence for a paragraph about {topic}.",
    "thesis-statements": "Write one thesis statement: your view on {topic}.",
    "developing-paragraphs": "Write three sentences that develop this idea: {topic}.",
    "coherence-flow": "Write two sentences about {topic}. Join them with because, but, or so.",
    "using-sources": "Write one sentence about {topic} that names its source with 'According to'.",
    "mechanics": "Write one sentence about {topic} with correct capitals, spelling, and a full stop.",
    "referencing-styles": "Write one sentence about {topic} with an in-text citation: author and year in brackets.",
    "academic-vocabulary": "Write one sentence about {topic} using one formal word and one linking word.",
    "genre": "Write one {genre} sentence about {topic}.",
}

SCAFFOLD_QUESTIONS = {
    "topic-sentences": ["What is your paragraph about, in three words?",
                        "Which words in your line tell the main idea?"],
    "thesis-statements": ["What is your view in one short line?",
                          "What reason proves your view?"],
    "developing-paragraphs": ["Which line is your main idea?",
                              "Which line does NOT prove it?"],
    "coherence-flow": ["How do your two ideas connect?",
                       "Which linker joins them best: because, but, or so?"],
    "using-sources": ["Whose idea are you using?",
                      "Where did you read it?"],
    "mechanics": ["Which word needs a capital letter?",
                  "Where does the full stop go?"],
    "referencing-styles": ["Whose idea are you borrowing?",
                           "Where do the author and year go?"],
    "academic-vocabulary": ["Which word is vague in your line?",
                            "Which linker joins your ideas?"],
    "genre": ["Who will read this {genre}?",
              "What fact must your first line give?"],
}

# Guiding questions before a hint, by level. Levels 1-2 move to hints sooner;
# Levels 4-5 get only questions (never hints or excerpts from the ladder).
QUESTIONS_BEFORE_HINT = {1: 0, 2: 1, 3: 2}

SELF_EXPLANATION = "In one line, why does this example work?"


def scaffold_task(discipline: str, module_id: str) -> str:
    """The writing task for a module (an instruction, never an answer)."""
    return SCAFFOLD_TASKS[module_id].format(
        topic=DISCIPLINE_TOPICS[discipline], genre=DISCIPLINE_GENRES[discipline])


def scaffold_question(module_id: str, index: int, genre: str) -> str:
    """One guiding question; cycles when a learner needs more than two."""
    questions = SCAFFOLD_QUESTIONS[module_id]
    return questions[index % len(questions)].format(genre=genre)


def _attempt_sentences(text: str) -> int:
    return len([s for s in re.split(r"[.!?]+", (text or "")) if s.strip()])


def targeted_hint(module_id: str, attempt_text: str, topic: str) -> str:
    """A hint aimed at the weak spot the attempt shows (or the module default)."""
    text = (attempt_text or "").strip()
    lowered = text.lower()
    if module_id == "topic-sentences":
        if not text or _attempt_sentences(text) != 1:
            return "Write just ONE sentence. Nothing more."
        return f"Start your sentence with the topic itself: {topic}."
    if module_id == "thesis-statements":
        if "because" not in lowered:
            return "Add because and your reason."
        return "Now cut every word that is not your view or your reason."
    if module_id == "developing-paragraphs":
        if _attempt_sentences(text) < 3:
            return "Add one more sentence that proves your first line."
        return "Cut any sentence that does not prove your first line."
    if module_id == "coherence-flow":
        if not any(w in lowered for w in ("because", "but", "so", "when", "while")):
            return "Join your two sentences with one of these: because, but, so."
        return "Read both parts aloud. Do they connect?"
    if module_id == "using-sources":
        if "according to" not in lowered:
            return "Start with 'According to ...' and name your source."
        return "Now put the rest in your own words."
    if module_id == "mechanics":
        if text and not text[0].isupper():
            return "Start with a capital letter."
        if not re.search(r"[.!?]$", text):
            return "Close your line with a full stop."
        return "Check each word's spelling, then each a, an, and the."
    if module_id == "referencing-styles":
        if "(" not in text or not re.search(r"\d{4}", text):
            return "Add the author and year in brackets."
        return "Now list the full source at the end."
    if module_id == "academic-vocabulary":
        if any(w in lowered for w in ("nice", "very", "good", "bad", "big",
                                      "small", "things", "stuff")):
            return "Swap one vague word for an exact one."
        if not any(w in lowered for w in ("however", "therefore", "because",
                                          "but", "also", "for example")):
            return "Add one linker: however, therefore, or for example."
        return "Read it aloud. Does it sound formal?"
    if _attempt_sentences(text) < 1 or len(text.split()) < 5:
        return "Write one full sentence of five or more words."
    return "Use calm, exact words. No 'very' or 'really'."


# Worked answers for impatient learners. Each module teaches its book rule as
# topic + controlling idea: (1) name the topic, (2) fix the exact point,
# (3) narrow it, (4) check every line supports it. Served only on the
# explicit "Just show me the steps" ask or a repeated "Show me now" - never
# in the normal ladder, where the twin still withholds the answer.
# Placeholders: {topic} {genre}.
WORKED_STEPS = {
    "topic-sentences": [
        "First, name the topic: {topic}.",
        "Next, ask: what exact point will you prove about it?",
        "Then narrow your point until one paragraph can prove it.",
        "Finally, check every line against your point, then study the model."],
    "thesis-statements": [
        "First, name the topic: {topic}.",
        "Next, take one side: what do you believe about it?",
        "Then add your best reason in the same line.",
        "Finally, check every line proves your view, then study the model."],
    "developing-paragraphs": [
        "First, write your main line about {topic}.",
        "Next, add two lines that prove your main line.",
        "Then cut any line that does not prove it.",
        "Finally, check each kept line, then study the model."],
    "coherence-flow": [
        "First, write two true lines about {topic}.",
        "Next, name the link: cause, contrast, or extra detail.",
        "Then join them with the linker that shows it.",
        "Finally, check the flow aloud, then study the model."],
    "using-sources": [
        "First, name whose idea about {topic} you borrow.",
        "Next, fix the exact point you borrow.",
        "Then write that point in your own words.",
        "Finally, check the source is named, then study the model."],
    "mechanics": [
        "First, write one line about {topic}.",
        "Next, fix the capital letter and the full stop.",
        "Then check each word's spelling and each article.",
        "Finally, check the line once more, then study the model."],
    "referencing-styles": [
        "First, name whose idea about {topic} you borrow.",
        "Next, add the author and year in brackets.",
        "Then write the point in your own words.",
        "Finally, check the citation is there, then study the model."],
    "academic-vocabulary": [
        "First, write one plain line about {topic}.",
        "Next, swap one vague word for an exact one.",
        "Then add one linker to join your ideas.",
        "Finally, check it sounds formal, then study the model."],
    "genre": [
        "First, name your reader and your {genre} topic: {topic}.",
        "Next, ask: which fact does your reader need first?",
        "Then open with that fact and push the rest down.",
        "Finally, check the first line gives it, then study the model."],
}


def worked_steps(module_id: str, discipline: str) -> list[str]:
    """The four ordered steps for a module, set on the learner's topic."""
    fmt = {"topic": DISCIPLINE_TOPICS[discipline],
           "genre": DISCIPLINE_GENRES[discipline]}
    return [step.format(**fmt) for step in WORKED_STEPS[module_id]]


# One running model topic per discipline, worked across all six modules so the
# learner sees every sentence type on the same point. Each model topic is
# clearly different from its task topic (friction, not evaporation; street
# plays, not the freedom struggle) so the model cannot be copied as the
# learner's answer. Points stay familiar to first-year Indian undergraduates:
# cycling, old phones, vaccine drives, street plays, tea stalls, city jobs.
# Keyed (module, discipline); the genre models take {genre}.
WORKED_MODELS = {
    ("topic-sentences", "Sciences"):
        "Friction explains why cycling uphill feels harder than cycling "
        "on flat ground.",
    ("topic-sentences", "Technology"):
        "Software updates explain why old phones fail after support ends.",
    ("topic-sentences", "Medicine"):
        "Vaccination explains why polio faded from our schools.",
    ("topic-sentences", "Arts & Humanities"):
        "Street plays explain why busy markets turn into open theatres.",
    ("topic-sentences", "Commerce & Management"):
        "Tea stalls explain why small savings grow into big shops.",
    ("topic-sentences", "Social Sciences"):
        "City jobs explain why young people leave their farms.",
    ("thesis-statements", "Sciences"):
        "Colleges should teach friction tests because rough roads slow "
        "every cyclist.",
    ("thesis-statements", "Technology"):
        "Shops should force updates because old phones leak data after "
        "support ends.",
    ("thesis-statements", "Medicine"):
        "Schools should host vaccine drives because missed shots spread "
        "illness fast.",
    ("thesis-statements", "Arts & Humanities"):
        "Colleges should fund street plays because live shows teach faster "
        "than posters.",
    ("thesis-statements", "Commerce & Management"):
        "Towns should license tea stalls because tidy stalls draw daily "
        "crowds.",
    ("thesis-statements", "Social Sciences"):
        "Towns should train youth because city jobs pull workers from farms.",
    ("developing-paragraphs", "Sciences"):
        "Friction explains why cycling uphill feels harder than cycling "
        "on flat ground. "
        "Rough roads grip the tyres hard. "
        "Smooth tracks let wheels glide on.",
    ("developing-paragraphs", "Technology"):
        "Software updates explain why old phones fail after support ends. "
        "Makers stop fixing flaws in old phones. "
        "Crooks learn each old flaw fast.",
    ("developing-paragraphs", "Medicine"):
        "Vaccination explains why polio faded from our schools. "
        "Nurses list each child at the gate. "
        "No child misses the second shot.",
    ("developing-paragraphs", "Arts & Humanities"):
        "Street plays explain why busy markets turn into open theatres. "
        "Actors rehearse each night in the park. "
        "Crowds learn the songs by heart.",
    ("developing-paragraphs", "Commerce & Management"):
        "Tea stalls explain why small savings grow into big shops. "
        "Owners save each coin in a tin box. "
        "One box buys a second stall.",
    ("developing-paragraphs", "Social Sciences"):
        "City jobs explain why young people leave their farms. "
        "Farms pay less than town shops. "
        "Buses leave full each Monday dawn.",
    ("coherence-flow", "Sciences"):
        "Uphill rides tire legs because friction grips hard, "
        "so riders change to low gears.",
    ("coherence-flow", "Technology"):
        "Old phones leak data because makers stop fixing them, "
        "so shops push updates fast.",
    ("coherence-flow", "Medicine"):
        "Polio faded from schools because nurses tracked each child, "
        "so drives visit yearly.",
    ("coherence-flow", "Arts & Humanities"):
        "Markets turn into theatres because actors play for free, "
        "so crowds stay back each night.",
    ("coherence-flow", "Commerce & Management"):
        "Small savings grow because owners bank each coin, "
        "so one stall becomes two.",
    ("coherence-flow", "Social Sciences"):
        "Young people leave farms because town shops pay more, "
        "so buses run full each dawn.",
    ("using-sources", "Sciences"):
        "According to our textbook, uphill rides tire legs because friction "
        "grips hard.",
    ("using-sources", "Technology"):
        "According to our guide, old phones leak data because makers stop "
        "fixing them.",
    ("using-sources", "Medicine"):
        "According to our manual, polio faded from schools because nurses "
        "tracked each child.",
    ("using-sources", "Arts & Humanities"):
        "According to our reader, markets turn into theatres because actors "
        "play for free.",
    ("using-sources", "Commerce & Management"):
        "According to our survey, small savings grow because owners bank "
        "each coin.",
    ("using-sources", "Social Sciences"):
        "According to our survey, young people leave farms because town "
        "shops pay more.",
    ("genre", "Sciences"):
        "This {genre} opens with slope tests, which show why rough roads "
        "tire riders.",
    ("genre", "Technology"):
        "This {genre} opens with leak counts, which show why updates matter "
        "most.",
    ("genre", "Medicine"):
        "This {genre} opens with shot lists, which show why full coverage "
        "works.",
    ("genre", "Arts & Humanities"):
        "This {genre} opens with play scripts, which show why crowds stay "
        "back each night.",
    ("genre", "Commerce & Management"):
        "This {genre} opens with cash-box counts, which show why small "
        "coins matter.",
    ("genre", "Social Sciences"):
        "This {genre} opens with bus counts, which show why youth leave "
        "farms.",
    ("mechanics", "Sciences"):
        "Neem trees explain why village homes stay cool in summer.",
    ("mechanics", "Technology"):
        "Bus tickets show why paper tokens still beat phone apps in towns.",
    ("mechanics", "Medicine"):
        "Boiled water proves why clean habits stop stomach pain.",
    ("mechanics", "Arts & Humanities"):
        "Street plays show why busy markets turn into open theatres.",
    ("mechanics", "Commerce & Management"):
        "Tea stalls explain why small shops earn trust before profit.",
    ("mechanics", "Social Sciences"):
        "City jobs explain why young workers leave their farms.",
    ("referencing-styles", "Sciences"):
        "According to our textbook, neem trees explain why homes stay cool.",
    ("referencing-styles", "Technology"):
        "According to the manual, bus tickets show why paper tokens work.",
    ("referencing-styles", "Medicine"):
        "According to the health worker, boiled water proves why clean "
        "habits matter.",
    ("referencing-styles", "Arts & Humanities"):
        "According to our teacher, street plays show why markets turn "
        "lively.",
    ("referencing-styles", "Commerce & Management"):
        "According to the shop owner, tea stalls explain why trust earns "
        "profit.",
    ("referencing-styles", "Social Sciences"):
        "According to the survey report, city jobs explain why workers "
        "migrate.",
    ("academic-vocabulary", "Sciences"):
        "Because neem trees reduce indoor heat, villagers plant them near "
        "homes.",
    ("academic-vocabulary", "Technology"):
        "Paper tickets remain reliable because phone networks often fail "
        "in small towns.",
    ("academic-vocabulary", "Medicine"):
        "Boiled water prevents illness because heat kills most germs.",
    ("academic-vocabulary", "Arts & Humanities"):
        "Street plays should get more public grounds because crowds learn "
        "fast from them.",
    ("academic-vocabulary", "Commerce & Management"):
        "Small shops should keep daily accounts because clear records "
        "build trust.",
    ("academic-vocabulary", "Social Sciences"):
        "Young workers migrate because city jobs pay regular wages.",
}


def worked_model(module_id: str, discipline: str) -> str:
    """The model demonstration for a module: same discipline, own point."""
    return WORKED_MODELS[(module_id, discipline)].format(
        genre=DISCIPLINE_GENRES[discipline])


# --- Attempt assessor (Muse Spark, JSON output) ---------------------------------
# Every free-text scaffold try is judged against the task and the module
# rubric: Spark returns a verdict, feedback fields, a 0-2 score and the next
# ladder step. Short nonsense and copies of the served pattern are caught
# deterministically without calling Spark. Feedback is assembled server-side
# (strength?, problem quoting the learner, next action), verified, and only
# then served; anything failing falls back to the fixed ladder silently.
SCAFFOLD_RUBRICS = {
    "topic-sentences": ["Names the paragraph topic.",
                        "States one specific point the paragraph will prove.",
                        "Is one complete sentence."],
    "thesis-statements": ["Takes a debatable side, not a plain fact.",
                          "Gives a reason in the same line.",
                          "Is one complete sentence."],
    "developing-paragraphs": ["Keeps one main idea across three lines.",
                              "Each line proves the main line.",
                              "Cuts lines that wander off."],
    "coherence-flow": ["Has two true lines about the topic.",
                       "Joins them with a fitting linker.",
                       "Reads smoothly from line to line."],
    "using-sources": ["Names the source with According to.",
                      "Puts the borrowed point in own words.",
                      "Is one complete sentence."],
    "mechanics": ["Starts with a capital letter.",
                  "Ends with a full stop.",
                  "Spelling and articles are correct."],
    "referencing-styles": ["Names the author in the line.",
                           "Adds the year in brackets.",
                           "Puts the point in own words."],
    "academic-vocabulary": ["Uses one formal, exact word.",
                            "Joins ideas with a linker.",
                            "Is one complete sentence."],
    "genre": ["Opens with the fact readers need first.",
              "Uses calm, exact words.",
              "Fits the {genre} shape."],
}

# Attempt score -> skill points. Levels move through level_for_score.
ASSESS_BUMPS = {0: 0, 1: 5, 2: 10}

ASSESS_KIND_LINES = {
    "off_task": "That does not match the task yet.",
    "nonsense": "I cannot follow that yet.",
    "copied": "That matches the book pattern too closely.",
}
ASSESS_RETRY_LINES = {
    "off_task": "Try the task itself in your own words.",
    "nonsense": "Write one clear line for the task.",
    "copied": "Write it again in your own words.",
}

SPARK_ASSESSOR_SYSTEM = (
    "You judge a learner's writing try for a first-year Indian undergraduate. "
    "Reply with a JSON object only, no other text, with keys: status (ok, "
    "off_task, nonsense or copied), strength (one sentence naming a real "
    "strength, or empty when there is none), problem (one sentence naming "
    "the one main problem, quoting the learner's own words), quote (the "
    "exact quoted words), next_action (one sentence telling the learner "
    "what to do next), score (0, 1 or 2 against the rubric) and next_step "
    "(retry, question, hint, excerpt or rewrite). For language errors, "
    "point to them without rewriting the sentence. For claims that look "
    "wrong, ask a question instead of correcting, and never invent facts.")


def _assessor_messages(module_id: str, discipline: str, attempt: dict,
                       text: str) -> list[dict]:
    """Prompt: task, rubric, the try, and the must-not-copy references."""
    rubric = [c.format(genre=DISCIPLINE_GENRES[discipline])
              for c in SCAFFOLD_RUBRICS[module_id]]
    refs = f"Model pattern: {worked_model(module_id, discipline)}"
    if attempt.get("excerpt_text"):
        refs += f" Shown excerpt: {attempt['excerpt_text']}"
    user = (f"Task: {scaffold_task(discipline, module_id)} "
            f"Rubric: {' '.join(f'{i + 1}. {c}' for i, c in enumerate(rubric))} "
            f"Learner try: {text} {refs}")
    return [{"role": "system", "content": SPARK_ASSESSOR_SYSTEM},
            {"role": "user", "content": user}]


def _as_sentence(text: str | None) -> str:
    text = (text or "").strip()
    if text and text[-1] not in ".!?":
        text += "."
    return text


def _validate_assessment(data: dict) -> dict | None:
    """Validated assessor fields, or None when Spark output is unusable."""
    if not isinstance(data, dict):
        return None
    status, score = data.get("status"), data.get("score")
    if status not in ("ok", "off_task", "nonsense", "copied"):
        return None
    if not isinstance(score, int) or isinstance(score, bool) \
            or score not in (0, 1, 2):
        return None
    if status != "ok":
        score = 0
    next_step = data.get("next_step")
    if next_step not in ("retry", "question", "hint", "excerpt", "rewrite",
                         "next", "study"):
        next_step = "question"
    fields = {"status": status, "score": score, "next_step": next_step,
              "strength": _as_sentence(data.get("strength")),
              "problem": _as_sentence(data.get("problem")),
              "quote": str(data.get("quote") or "").strip(),
              "next_action": _as_sentence(data.get("next_action"))}
    if status == "ok" and (not fields["next_action"] or not fields["quote"]):
        return None
    if status == "ok" and fields["score"] < 2 and not fields["problem"]:
        return None
    return fields


def _parse_assessment(raw: str) -> dict | None:
    """Validated assessor fields from one JSON object, else None."""
    try:
        data = json.loads(raw)
    except ValueError:
        return None
    return _validate_assessment(data)


def _assessment_feedback(fields: dict) -> str:
    """Strength?, problem, next action - or the kind retry pair."""
    if fields["status"] == "ok":
        parts = (([fields["strength"]] if fields["strength"] else [])
                 + ([fields["problem"]] if fields["problem"] else [])
                 + [fields["next_action"]])
    else:
        parts = [ASSESS_KIND_LINES[fields["status"]],
                 fields["next_action"]
                 or ASSESS_RETRY_LINES[fields["status"]]]
    return " ".join(parts)


def _copied_pattern(module_id: str, discipline: str, attempt: dict,
                    text: str) -> bool:
    """True when the try overlaps the served model or excerpt."""
    refs = [worked_model(module_id, discipline)]
    if attempt.get("excerpt_text"):
        refs.append(attempt["excerpt_text"])
    return any(_overlaps_rule(text, ref) for ref in refs)


def _assess_with_spark(learner_id: int, module_id: str, discipline: str,
                       attempt: dict, text: str) -> dict | None:
    """Spark verdict passing the assessor checklist, or None after regens."""
    if _demo_mode() or _model_api_key() is None:
        return None
    failed = ["no-output"]
    for _ in range(1 + SPARK_MAX_REGENS):
        try:
            raw = _spark_chat(_assessor_messages(
                module_id, discipline, attempt, text),
                timeout=SPARK_TIMEOUT_SLOW)
        except SparkError:
            continue
        fields = _parse_assessment(raw)
        if fields is None:
            continue
        verdict = verify("assessor", {
            "status": fields["status"],
            "feedback": _assessment_feedback(fields), "attempt": text,
            "quote": fields["quote"], "score": fields["score"],
            "fields": [fields["strength"], fields["problem"],
                       fields["next_action"]]})
        if verdict["pass"]:
            return fields
        failed = verdict["failed"]
    store.log_event(learner_id, "Scaffold", "twin", "verify-assess",
                    f"attempt rejected: {failed}")
    return None


# Deterministic assessor fallback: every try is judged, even with no key.
ASSESS_FALLBACK_PROBLEM = {
    "topic-sentences": "It has no clear controlling idea yet, so a reader "
                       "cannot tell what the paragraph will prove.",
    "thesis-statements": "It states no clear side with a reason, so a reader "
                         "cannot tell what you will argue.",
    "developing-paragraphs": "The lines do not all prove one idea yet, so "
                             "the point feels loose.",
    "coherence-flow": "The two parts are not joined yet, so the reader "
                      "trips between them.",
    "using-sources": "No source is named yet, so a reader cannot trust "
                     "the point.",
    "genre": "The opening does not lead with the key fact yet, so a "
             "reader must hunt for it.",
    "mechanics": "Small slips in capitals or stops remain, so the line "
                 "looks careless.",
    "referencing-styles": "The author or year is missing, so the source "
                          "stays hidden.",
    "academic-vocabulary": "Easy words repeat, so the point sounds weak.",
}
ASSESS_FALLBACK_ACTION = {
    "topic-sentences": "Say what exactly about the topic in the same line.",
    "thesis-statements": "Add your side and one reason in one line.",
    "developing-paragraphs": "Make every line prove your first line.",
    "coherence-flow": "Join the two parts with because, but, or so.",
    "using-sources": "Start with According to and name the source.",
    "genre": "Open with the one fact readers need first.",
    "mechanics": "Fix one capital letter and one full stop.",
    "referencing-styles": "Add the author and year in brackets.",
    "academic-vocabulary": "Swap one vague word for an exact one.",
}
ASSESS_STARTERS = {
    "topic-sentences": "{topic} explains why ____.",
    "thesis-statements": "____ should ____ because ____.",
    "developing-paragraphs": "For example, ____.",
    "coherence-flow": "____, but ____.",
    "using-sources": "According to ____, ____.",
    "genre": "The key fact is ____.",
    "mechanics": "{topic} ____.",
    "referencing-styles": "According to ____ (__), ____.",
    "academic-vocabulary": "____. However, ____.",
}
ASSESS_TRY_QUESTIONS = {
    "topic-sentences": "what exactly will you say about it?",
    "thesis-statements": "what reason proves your view?",
    "developing-paragraphs": "which line proves your main idea?",
    "coherence-flow": "which linker joins your two parts best?",
    "using-sources": "whose idea is it, and where did you read it?",
    "genre": "what is the key fact a reader needs first?",
    "mechanics": "which letter needs a capital in your line?",
    "referencing-styles": "where do the author and year go in your line?",
    "academic-vocabulary": "which word is vague in your line?",
}
_CLAIM_VERBS = ("explain", "explains", "show", "shows", "should", "because",
                "why", "prove", "proves", "mean", "means", "make", "makes",
                "lead", "leads", "ensure", "ensures", "cause", "causes")


def _assess_fallback(module_id: str, discipline: str, text: str) -> dict:
    """Deterministic verdict: real-try strength, module problem, 1 or 2."""
    lowered = text.lower()
    if module_id == "developing-paragraphs":
        strong = _attempt_sentences(text) >= 3 and len(text.split()) >= 20
    elif module_id == "coherence-flow":
        strong = _attempt_sentences(text) >= 2 and any(
            w in lowered for w in ("because", "but", "so", "when", "while"))
    else:
        strong = (_attempt_sentences(text) == 1
                  and len(text.split()) >= 8
                  and any(v in lowered for v in _CLAIM_VERBS))
    words = text.split()
    quote = text.strip() if len(words) <= 10 else " ".join(words[:6])
    return {"status": "ok", "score": 2 if strong else 1,
            "next_step": "question",
            "strength": f"Your line starts well: '{quote}'.",
            "problem": "" if strong else ASSESS_FALLBACK_PROBLEM[module_id],
            "quote": quote,
            "next_action": ASSESS_FALLBACK_ACTION[module_id]}


def _demo_assessment(learner_id: int, attempt: dict) -> dict:
    """Fixed score-1 card for the scripted demo try (bump + log included)."""
    quote = "the peace and calm that we enjoy today"
    attempt["weak"] = attempt.get("weak", 0) + 1
    skill = attempt["skill"]
    current = latest_scores(learner_id).get(skill, 0)
    new_score = min(100, current + ASSESS_BUMPS[1])
    store.save_skill_scores(learner_id, {skill: new_score})
    store.log_event(learner_id, "Scaffold", "twin", "assess",
                    "score=1/2 status=ok (demo script)")
    learner = store.get_learner(learner_id) or {}
    first = ((learner.get("name") or "friend").split() or ["friend"])[0]
    action = ASSESS_FALLBACK_ACTION["topic-sentences"]
    return {"status": "ok",
            "feedback": f"{DEMO_ASSESSMENT_STRENGTH} {DEMO_ASSESSMENT_PROBLEM}",
            "strength": DEMO_ASSESSMENT_STRENGTH,
            "problem": DEMO_ASSESSMENT_PROBLEM, "quote": quote, "score": 1,
            "next_step": "question",
            "next_action": "Say what exactly about the topic in the same line.",
            "skill": skill,
            "skill_score": new_score,
            "skill_level": level_for_score(new_score),
            "model": DEMO_ASSESSMENT_MODEL,
            "your_turn": DEMO_ASSESSMENT_YOUR_TURN,
            "motivation": _motivation_card(
                first, "fair",
                {"quote": quote, "line": DEMO_ASSESSMENT_STRENGTH},
                DEMO_ASSESS_ATTEMPT, [action],
                DISCIPLINE_TOPICS[attempt["discipline"]],
                f"Next goal: {action}")}


def _judge_attempt(learner_id: int, attempt: dict, text: str) -> dict | None:
    """Assess one try: gates, Spark, fallback, verify, score. None: demo only."""
    module_id, discipline = attempt["module"], attempt["discipline"]
    if len(text.split()) < 3:
        fields = {"status": "nonsense", "score": 0, "next_step": "retry",
                  "strength": "", "problem": "", "quote": "", "next_action": ""}
    elif _copied_pattern(module_id, discipline, attempt, text):
        fields = {"status": "copied", "score": 0, "next_step": "retry",
                  "strength": "", "problem": "", "quote": "", "next_action": ""}
    elif _demo_mode():
        if attempt["module"] == "topic-sentences" and _demo_text_match(
                text, DEMO_ASSESS_ATTEMPT):
            return _demo_assessment(learner_id, attempt)
        return None  # demo keeps the fixed ladder
    else:
        fields = _assess_with_spark(
            learner_id, module_id, discipline, attempt, text)
        if fields is None:
            fields = _assess_fallback(module_id, discipline, text)
    feedback = _assessment_feedback(fields)
    verdict = verify("assessor", {"status": fields["status"], "feedback": feedback,
                                  "attempt": text, "quote": fields["quote"],
                                  "score": fields["score"]})
    if not verdict["pass"]:
        store.log_event(learner_id, "Scaffold", "twin", "verify-assess",
                        f"attempt rejected: {verdict['failed']}")
        return None
    weak = fields["status"] != "ok" or fields["score"] < 2
    attempt["weak"] = 0 if not weak else attempt.get("weak", 0) + 1
    skill = attempt["skill"]
    bump = ASSESS_BUMPS[fields["score"]]
    current = latest_scores(learner_id).get(skill, 0)
    new_score = min(100, current + bump)
    if bump:
        store.save_skill_scores(learner_id, {skill: new_score})
    store.log_event(learner_id, "Scaffold", "twin", "assess",
                    f"score={fields['score']}/2 status={fields['status']}")
    starter = ASSESS_STARTERS[module_id].format(
        topic=DISCIPLINE_TOPICS[discipline],
        genre=DISCIPLINE_GENRES[discipline])
    learner = store.get_learner(learner_id) or {}
    first = ((learner.get("name") or "friend").split() or ["friend"])[0]
    band = ("strong" if fields["score"] == 2
            else "fair" if fields["score"] == 1 else "weak")
    strength = ({"quote": fields["quote"], "line": fields["strength"]}
                if fields["strength"] else None)
    action = ASSESS_FALLBACK_ACTION[module_id]
    return {"status": fields["status"], "feedback": feedback,
            "strength": fields["strength"], "problem": fields["problem"],
            "quote": fields["quote"], "score": fields["score"],
            "next_step": fields["next_step"], "next_action": fields["next_action"],
            "skill": skill,
            "skill_score": new_score,
            "skill_level": level_for_score(new_score),
            "model": worked_model(module_id, discipline),
            "your_turn": f"Your turn: finish this starter: '{starter}'",
            "motivation": _motivation_card(
                first, band, strength, text, [action],
                DISCIPLINE_TOPICS[discipline], f"Next goal: {action}")}


# --- Practice Assessor ----------------------------------------------------------
# Closed answers (a picked option, an ordering) are judged against the module
# rubric in one Spark batch per set: ordered feedback quoting the choice, a
# 0-2 score each, and study routing after repeated wrongs. Deterministic
# templates cover no-key, failure, invalid output, and skills without a
# module, so every answer is always assessed and scored.
SKILL_MODULE = {"Paragraphing": "topic-sentences",
                "Argument": "thesis-statements",
                "Sentence structure": "coherence-flow",
                "Using sources": "using-sources",
                "Academic tone": "genre"}

SPARK_PRACTICE_SYSTEM = (
    "You judge practice answers for a first-year Indian undergraduate. "
    "Reply with a JSON array only, no other text: one object per answer, in "
    "order, each with id, strength (one sentence naming a real strength, or "
    "empty when there is none), problem (one sentence naming the main "
    "problem and quoting the learner's answer; empty when the answer is "
    "fully correct), quote (exact words from the learner's answer), "
    "next_action (one sentence telling the learner what to do next) and "
    "score (2 when a marked answer is correct, else 0 or 1; 0-2 for "
    "written answers against the rubric). Never invent facts.")


def _order_prompt_sentences(prompt: str) -> dict:
    """{number: sentence} from '1) ...' runs (apostrophes inside are fine).

    Letter runs ('[A] ...') map too, for the demo repair item.
    """
    marks = [(m.start(), m.group(1))
             for m in re.finditer(r"(\d+)\)\s*'", prompt or "")]
    sents = {}
    for k, (pos, num) in enumerate(marks):
        end = marks[k + 1][0] if k + 1 < len(marks) else len(prompt or "")
        seg = (prompt or "")[pos + len(num) + 3:end]
        cut = seg.rfind("'")
        sents[num] = seg[:cut].strip() if cut >= 0 else seg.strip()
    letters = [(m.start(), m.group(1).upper())
               for m in re.finditer(r"\[([A-Za-z])\]", prompt or "")]
    for k, (pos, letter) in enumerate(letters):
        end = letters[k + 1][0] if k + 1 < len(letters) else len(prompt or "")
        seg = (prompt or "")[pos + 3:end].strip().rstrip(".")
        sents[letter] = seg.strip()
    return sents


def _practice_answer_text(item: dict, given: str) -> str:
    """The learner's answer in words: chosen option, ordered sentences."""
    given = (given or "").strip()
    if item["type"] == "mcq":
        for option in item["options"]:
            mark = re.match(r"\s*\(?([A-Za-z])\)", str(option))
            if mark and given.upper() == mark.group(1).upper():
                return str(option).split(")", 1)[1].strip()
        return ""
    parts = [p.strip().upper() for p in given.split(",") if p.strip()]
    if not parts or any(not (p.isdigit() or len(p) == 1 and p.isalpha())
                        for p in parts):
        return ""
    sents = _order_prompt_sentences(item["prompt"])
    try:
        return " ".join(sents[p] for p in parts)
    except KeyError:
        return f"order {given}"


def _practice_assess_messages(skill: str, module_id: str, discipline: str,
                              answers: list[dict]) -> list[dict]:
    """One batch prompt: rubric plus every judged answer with its verdict."""
    rubric = [c.format(genre=DISCIPLINE_GENRES[discipline])
              for c in SCAFFOLD_RUBRICS[module_id]]
    lines = []
    for i, ans in enumerate(answers):
        if ans["closed"]:
            lines.append(
                f"A{i + 1} (id {ans['id']}): {ans['prompt']} "
                f"Options: {' / '.join(ans['options'])} "
                f"Learner answer: {ans['choice']} "
                f"Correct: {'yes' if ans['correct'] else 'no'}.")
        else:
            lines.append(
                f"A{i + 1} (id {ans['id']}, {ans['kind']}): {ans['task']} "
                f"Learner text: {ans['choice']} Score 0-2 on the rubric.")
    user = (f"Skill: {skill}. "
            f"Rubric: {' '.join(f'{i + 1}. {c}' for i, c in enumerate(rubric))} "
            f"Judge each answer:\n" + "\n".join(lines))
    return [{"role": "system", "content": SPARK_PRACTICE_SYSTEM},
            {"role": "user", "content": user}]


def _practice_write_template(text: str, topic_words: set[str]) -> dict:
    """Deterministic free-text scoring: length plus topic mention."""
    words = text.split()
    if len(words) < 3:
        return _practice_template_fields("", False, "")
    quote = " ".join(words[:6])
    topical = bool(set(re.findall(r"[a-z]+", text.lower())) & topic_words)
    if len(words) >= 8 and topical:
        return {"status": "ok",
                "strength": f"Good try on the topic: \"{quote}\".",
                "problem": "", "quote": quote,
                "next_action": "Keep going.", "score": 2}
    return {"status": "ok", "strength": "",
            "problem": f"Needs more: \"{quote}\".", "quote": quote,
            "next_action": "Write at least two full lines on the topic.",
            "score": 1}


def _practice_template_fields(choice: str, correct: bool, given: str) -> dict:
    """Deterministic assessment (needs no rubric beyond the verdict)."""
    if not choice:
        return {"status": "ok", "strength": "",
                "problem": "You gave no answer here.", "quote": "no answer",
                "next_action": "Pick an option before moving on.", "score": 0}
    attempt = choice if len(choice.strip()) >= 4 else f"option {given}: {choice}"
    if correct:
        return {"status": "ok", "strength": f"Correct: \"{attempt}\".",
                "problem": "", "quote": attempt,
                "next_action": "Keep going.", "score": 2}
    return {"status": "ok", "strength": "",
            "problem": f"Not this time: you chose \"{attempt}\".",
            "quote": attempt,
            "next_action": "Read the explanation below, then continue.",
            "score": 0}


def _judge_practice_set(learner_id: int, skill: str, items: list[dict],
                        answers: dict, demo: bool = False) -> dict:
    """{item_id: assessment}: one Spark batch per module, templates for rest.

    Closed answers are checked exactly; write answers are free text scored
    0-2. ok means correct (closed) or score 2 (write). Demo sets use the
    fixed produce rule; no Spark runs in demo mode at all.
    """
    learner = store.get_learner(learner_id) or {}
    discipline = learner.get("discipline") or "Sciences"
    topic_words = (set(re.findall(
        r"[a-z]+", DISCIPLINE_TOPICS[discipline].lower())) - _STOPWORDS)
    judged: dict[str, tuple] = {}
    sparkable: list[dict] = []
    for item in items:
        given = answers.get(item["id"], "")
        iskill = item.get("skill", skill)
        module_id = item.get("module") or SKILL_MODULE.get(iskill)
        if item.get("type") == "write":
            text = (given or "").strip()
            if demo and item.get("kind") == "produce":
                fields = _demo_produce_fields(text)
                judged[item["id"]] = (fields["score"] == 2, fields,
                                      module_id, iskill)
            elif len(text.split()) < 3 or module_id is None:
                fields = _practice_write_template(text, topic_words)
                judged[item["id"]] = (fields["score"] == 2, fields,
                                      module_id, iskill)
            else:
                sparkable.append({"id": item["id"], "closed": False,
                                  "kind": item.get("kind", "write"),
                                  "task": item["prompt"], "choice": text,
                                  "skill": iskill, "module": module_id})
        else:
            ok = check_answer(item, given)
            choice = _practice_answer_text(item, given)
            if not choice or module_id is None:
                judged[item["id"]] = (ok, _practice_template_fields(
                    choice, ok, (given or "").strip()), module_id, iskill)
            else:
                sparkable.append({"id": item["id"], "closed": True,
                                  "prompt": item["prompt"],
                                  "options": item["options"], "choice": choice,
                                  "correct": ok, "skill": iskill,
                                  "module": module_id})
    by_module: dict[str, list[dict]] = {}
    for ans in sparkable:
        by_module.setdefault(ans["module"], []).append(ans)
    for module_id, group in by_module.items():
        resolved: dict[str, dict] = {}
        if _model_api_key() is not None and not _demo_mode():
            for _ in range(1 + SPARK_MAX_REGENS):
                pending = [a for a in group if a["id"] not in resolved]
                if not pending:
                    break
                try:
                    raw = _spark_chat(_practice_assess_messages(
                        pending[0]["skill"], module_id, discipline, pending))
                    data = json.loads(raw)
                    drafts = {d["id"]: d for d in data
                              if isinstance(d, dict) and "id" in d} \
                        if isinstance(data, list) else {}
                except (SparkError, ValueError):
                    continue
                for ans in pending:
                    fields = _validate_assessment(drafts.get(ans["id"], {}))
                    if fields is not None and (
                            fields["status"] != "ok"
                            or (ans["closed"]
                                and (fields["score"] == 2) != ans["correct"])):
                        fields = None
                    if fields is not None:
                        feedback = _assessment_feedback(fields)
                        verdict = verify("assessor", {
                            "status": "ok", "feedback": feedback,
                            "attempt": ans["choice"],
                            "quote": fields["quote"],
                            "score": fields["score"]})
                        if not verdict["pass"]:
                            fields = None
                    if fields is not None:
                        resolved[ans["id"]] = fields
        rejected = [a["id"] for a in group if a["id"] not in resolved]
        for ans in group:
            fields = resolved.get(ans["id"])
            if fields is None:
                given = answers.get(ans["id"], "")
                if ans["closed"]:
                    fields = _practice_template_fields(
                        ans["choice"], ans["correct"], (given or "").strip())
                else:
                    fields = _practice_write_template(ans["choice"], topic_words)
            ok = ans["correct"] if ans["closed"] else fields["score"] == 2
            judged[ans["id"]] = (ok, fields, module_id, ans["skill"])
        if rejected and _model_api_key() is not None \
                and not _demo_mode():
            store.log_event(learner_id, "Practise", "twin", "verify-assess",
                            f"items rejected: {rejected}")
    out = {}
    wrongs = 0
    for item in items:
        ok, fields, module_id, iskill = judged[item["id"]]
        if not ok and wrongs >= 2 and module_id is not None:
            next_step: str = "study"
        else:
            next_step = "next"
        if not ok:
            wrongs += 1
        out[item["id"]] = {"ok": ok, "feedback": _assessment_feedback(fields),
                           "score": fields["score"], "next_step": next_step,
                           "module": module_id, "skill": iskill}
    return out


def _mastery_move_up(learner_id: int, skill: str) -> bool:
    """Two sets at 80%+ move the skill to the next level floor."""
    rows = store.get_practice_results(learner_id, skill)[-MASTERY_SETS:]
    if len(rows) < MASTERY_SETS or any(
            r["accuracy"] < MASTERY_ACCURACY for r in rows):
        return False
    current = latest_scores(learner_id).get(skill, 0)
    if level_for_score(current) >= 5:
        return False
    if _demo_mode():
        # Earned and shown, but not saved: the improved paragraph must
        # still compare Level 1 → 2.
        return True
    store.save_skill_scores(
        learner_id, {skill: 20 * level_for_score(current)})
    return True


# --- Heuristic skill scorers (demo logic; Muse Spark plugs in here) -----------------
def _sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"[.!?]+", text) if s.strip()]


def _words(text: str) -> list[str]:
    return re.findall(r"[A-Za-z']+", text.lower())


def _clamp(score: float) -> int:
    return max(5, min(98, round(score)))


def score_grammar(text: str) -> int:
    """Capitalisation, terminal punctuation, runaway sentences."""
    sents = _sentences(text)
    score = 75.0
    bad_starts = sum(1 for s in sents if s and s[0].islower())
    score -= min(15, 5 * bad_starts)
    if not re.search(r"[.!?]\s*$", text.strip()):
        score -= 10
    score -= min(6, 2 * len(re.findall(r"  +", text)))
    score -= min(9, 3 * sum(1 for s in sents if len(s.split()) > 35))
    return _clamp(score)


def score_vocabulary(text: str) -> int:
    """Word variety (type-token ratio) plus longer-word use."""
    words = _words(text)
    if not words:
        return 5
    type_token = len(set(words)) / len(words)
    long_ratio = sum(1 for w in words if len(w) > 6) / len(words)
    return _clamp(100 * (0.5 * type_token + 0.5 * min(1.0, long_ratio * 4)))


def score_sentence_structure(text: str) -> int:
    """Sentence count, linker use, and length variety."""
    sents = _sentences(text)
    linkers = ["and", "but", "because", "so", "however", "although", "when", "while"]
    lowered = text.lower()
    score = 50 + 6 * min(3, len(sents)) + 4 * min(4, sum(lowered.count(l) for l in linkers))
    lengths = [len(s.split()) for s in sents]
    if lengths and max(lengths) - min(lengths) > 5:
        score += 8
    return _clamp(score)


def score_paragraphing(text: str) -> int:
    """Length in a healthy band, decent opening line, coherence words."""
    words = _words(text)
    sents = _sentences(text)
    score = 55.0
    if len(words) < 30:
        score -= 15
    elif len(words) > 200:
        score -= 10
    if sents and 8 <= len(sents[0].split()) <= 25:
        score += 10  # first line looks like a topic sentence
    coherence = ["first", "then", "also", "for example", "in conclusion", "finally"]
    lowered = text.lower()
    score += min(12, 4 * sum(lowered.count(c) for c in coherence))
    return _clamp(score)


def score_argument(text: str) -> int:
    """Claim/evidence markers: because, therefore, for example, ..."""
    markers = ["because", "therefore", "however", "for example", "in my opinion",
               "should", "evidence", "reason"]
    lowered = text.lower()
    return _clamp(30 + 12 * min(5, sum(lowered.count(m) for m in markers)))


def score_using_sources(text: str) -> int:
    """Quotes, reporting verbs, years, numbers - rare in plain drafts."""
    markers = ["according to", "said", "says", "study", "research", "%",
               "for instance", "shows that"]
    lowered = text.lower()
    hits = sum(lowered.count(m) for m in markers)
    hits += len(re.findall(r'"[^"]+"', text))          # quoted strings
    hits += len(re.findall(r"\b(19|20)\d{2}\b", text))  # years
    return _clamp(20 + 15 * min(5, hits))


# Chatty words the tone scorer penalises; the demo produce rule forbids them.
INFORMAL_WORDS = ["very", "really", "a lot", "thing", "things", "get", "got",
                  "gonna", "wanna", "can't", "don't", "doesn't", "isn't"]


def score_academic_tone(text: str) -> int:
    """Penalise chatty words, reward formal/hedging words."""
    formal = ["however", "moreover", "furthermore", "significant", "demonstrate",
              "indicate", "suggest", "therefore"]
    lowered = text.lower()
    score = 70 - 6 * min(5, sum(lowered.count(w) for w in INFORMAL_WORDS))
    score += 4 * min(4, sum(lowered.count(w) for w in formal))
    return _clamp(score)


SCORERS = {
    "Grammar": score_grammar,
    "Vocabulary": score_vocabulary,
    "Sentence structure": score_sentence_structure,
    "Paragraphing": score_paragraphing,
    "Argument": score_argument,
    "Using sources": score_using_sources,
    "Academic tone": score_academic_tone,
}


def diagnose_text(text: str) -> dict[str, int]:
    """Score text on all 7 skills with the heuristic scorers.

    The heuristic Diagnoser: fallback when Spark is unavailable and sanity
    check on Spark's levels.
    """
    return {skill: SCORERS[skill](text) for skill in SKILLS}


# --- Spark Diagnoser (fixed rubric in code; heuristic is the fallback) ---------
# Level descriptors per skill, weak to strong. Fixed here, mirrored in the
# "Rubric" section of docs/plan.md, sent to Spark with every diagnosis.
DIAGNOSE_RUBRIC = {
    "Grammar": [
        "Frequent errors block meaning.",
        "Many errors; meaning mostly clear.",
        "Some errors; meaning clear.",
        "Few, minor errors.",
        "Rare, minor errors.",
    ],
    "Vocabulary": [
        "Everyday words only, often repeated.",
        "Mostly everyday words; a few academic words.",
        "Some academic words, sometimes misused.",
        "Academic and subject terms, mostly used correctly.",
        "Precise academic and subject terms.",
    ],
    "Sentence structure": [
        "Short or run-on sentences.",
        "Mostly simple sentences; some joined correctly.",
        "Mix of simple and compound sentences.",
        "Varied sentences with few errors.",
        "Varied, controlled sentences.",
    ],
    "Paragraphing": [
        "No clear topic sentence; ideas listed.",
        "Topic sentence present but vague.",
        "Clear topic sentence with some support.",
        "Clear topic sentence, relevant support, some links.",
        "Clear topic sentence, support, and a link to the next idea.",
    ],
    "Argument": [
        "Opinions without reasons.",
        "A claim with one weak reason.",
        "A claim with reasons but little evidence.",
        "A claim with reasons and evidence.",
        "Claim, evidence, and a counterpoint answered.",
    ],
    "Using sources": [
        "No sources.",
        "A source mentioned vaguely, no citation.",
        "A source cited, format inconsistent.",
        "Correct citation, some copied wording.",
        "Correct paraphrase and citation.",
    ],
    "Academic tone": [
        "Conversational.",
        "Mostly conversational, a few formal phrases.",
        "Mix of formal and informal.",
        "Mostly formal and objective.",
        "Formal, objective, and appropriately hedged.",
    ],
}

SPARK_DIAGNOSE_SYSTEM = (
    "You score a learner's paragraph for a first-year Indian undergraduate. "
    "Reply with a JSON object only, no other text: one key per skill, each "
    "with level (1-5 against the rubric below), reason (one short sentence "
    "in simple English: basic words), "
    "and evidence (exact words copied from the paragraph). Judge only what "
    "is written; never invent facts. Never praise in general words.")

# Formal words that fail the simple-English check on model-written reasons.
COMPLEX_WORDS = ("moreover", "furthermore", "consequently", "subsequently",
                 "notwithstanding", "henceforth", "hereby", "herein",
                 "thereof", "albeit", "utilize", "utilise", "facilitate",
                 "paradigm", "plethora", "delineate", "elucidate",
                 "cognizant", "methodology", "dichotomy")


def _uses_simple_english(text: str) -> bool:
    """Rough check: no formal words, no sentence over 25 words."""
    lowered = (text or "").lower()
    if any(re.search(r"\b" + re.escape(w) + r"\b", lowered)
           for w in COMPLEX_WORDS):
        return False
    return all(len(s.split()) <= 25
               for s in re.split(r"[.!?]+", text or "") if s.strip())

# Spark levels map to band midpoints so level_for_score round-trips exactly.
DIAGNOSE_LEVEL_SCORES = {1: 10, 2: 30, 3: 50, 4: 70, 5: 90}


def _diagnose_messages(text: str, discipline: str) -> list[dict]:
    """Prompt: discipline, the fixed rubric, and the paragraph."""
    blocks = []
    for skill in SKILLS:
        levels = " ".join(
            f"L{i + 1}: {d}" for i, d in enumerate(DIAGNOSE_RUBRIC[skill]))
        blocks.append(f"{skill}: {levels}")
    user = (f"Discipline: {discipline}. "
            f"Rubric: {' '.join(blocks)} Paragraph: {text}")
    return [{"role": "system", "content": SPARK_DIAGNOSE_SYSTEM},
            {"role": "user", "content": user}]


def _validate_diagnosis(data, text: str) -> dict | None:
    """Levels 1-5 for all 7 skills with reasons and in-text evidence."""
    if not isinstance(data, dict):
        return None
    flat = " ".join(text.split())
    fields = {}
    for skill in SKILLS:
        entry = data.get(skill)
        if not isinstance(entry, dict):
            return None
        level = entry.get("level")
        if (isinstance(level, bool) or not isinstance(level, int)
                or not 1 <= level <= 5):
            return None
        reason = (entry.get("reason") or "").strip()
        evidence = (entry.get("evidence") or "").strip()
        if not reason or not evidence:
            return None
        if " ".join(evidence.split()) not in flat:
            return None
        if _has_generic_praise(reason) or not _uses_simple_english(reason):
            return None
        fields[skill] = {"level": level, "reason": reason,
                         "evidence": evidence}
    return fields


def _diagnose_with_spark(learner_id: int, text: str,
                         discipline: str) -> dict | None:
    """Levels + reasons from Spark (None when unusable after retries).

    Live in demo mode too: the scripted paragraphs never reach this helper
    (post_diagnose branches first), so any other text gets live Spark.
    """
    if _model_api_key() is None:
        return None
    messages = _diagnose_messages(text, discipline)
    for _ in range(1 + SPARK_MAX_REGENS):
        try:
            data = json.loads(_spark_chat(messages, temperature=0,
                                           timeout=SPARK_TIMEOUT_SLOW))
        except (SparkError, ValueError):
            continue
        fields = _validate_diagnosis(data, text)
        if fields is not None:
            return fields
    return None


# --- Demo mode (fixed script from the Demo kit in docs/plan.md) ----------------
# On when DEMO_MODE=true in the environment or backend .env (off by default).
# Only the exact scripted weak/improved paragraphs use fixed output; every
# other text (diagnose, feedback, scan, voice) calls Muse live, like Teacher
# Studio, with the usual template fallback.
def _demo_mode() -> bool:
    return (_env_key("DEMO_MODE") or "").strip().lower() in ("true", "1", "yes")


DEMO_LEARNER_ID = 1

DEMO_WEAK_PARAGRAPH = (
    "Plastic is very big problem. In my village the river is full of plastic. "
    "People throw the waste in river and fish is dying. "
    "Government should do something. Also the students also should know. "
    "So plastic is dangerous for nature and we must stop it.")

DEMO_IMPROVED_PARAGRAPH = (
    "Plastic waste is seriously harming the river in my village. "
    "People throw bottles and bags into the water, and the fish are dying. "
    "The panchayat should set up waste bins near the river, and students "
    "can help by spreading awareness.")

DEMO_DIAGNOSIS = {
    "Paragraphing": {"level": 1,
                     "reason": "No clear topic sentence; ideas are listed.",
                     "evidence": "Plastic is very big problem."},
    "Academic tone": {"level": 1, "reason": "Conversational.",
                      "evidence": "Government should do something."},
    "Using sources": {"level": 1, "reason": "No sources.",
                      "evidence": "In my village the river is full of plastic."},
    "Grammar": {"level": 2, "reason": "Missing articles; repeated \"also\".",
                "evidence": "People throw the waste in river"},
    "Argument": {"level": 2, "reason": "A claim with one weak reason.",
                 "evidence": "So plastic is dangerous for nature"},
    "Sentence structure": {"level": 2,
                           "reason": "Mostly short simple sentences.",
                           "evidence": "Also the students also should know."},
    "Vocabulary": {"level": 2, "reason": "Mostly everyday words.",
                   "evidence": "very big problem"},
}

DEMO_TWIN_RESPONSE = (
    "You are saying plastic in your village river is killing fish, and "
    "people must act. Your main problem: the first sentence, 'Plastic is "
    "very big problem', does not say what this paragraph will prove. Try "
    "starting like this: 'Plastic waste is harming ______ in ______.'")

DEMO_COMPARISON = (
    "In your last paragraph you had no clear topic sentence; this time "
    "your first sentence names the problem and the place.")

# Scripted Learn-assessor verdict for one exact demo try (fixed script:
# no Spark, no verifier). Any other demo try keeps the fixed ladder.
DEMO_ASSESS_ATTEMPT = ("Freedom struggle ensured the peace and calm that "
                       "we enjoy today")
DEMO_ASSESSMENT_STRENGTH = ("You named a topic and said what it achieved - "
                            "that is the right shape.")
DEMO_ASSESSMENT_PROBLEM = ("'the peace and calm that we enjoy today' is too "
                           "broad for one paragraph to prove. Which struggle, "
                           "and which result? Also start with 'The'.")
DEMO_ASSESSMENT_MODEL = ("Public libraries helped many village students "
                         "prepare for college.")
DEMO_ASSESSMENT_YOUR_TURN = ("Your turn: 'The Indian freedom struggle gave "
                             "ordinary people ______.'")

DEMO_PRACTICE_ITEMS = [
    {"id": "d1", "type": "mcq", "kind": "recognise",
     "prompt": "Which is the best topic sentence for a paragraph about "
               "phones in college?",
     "options": ["(a) I like phones.",
                 "(b) Mobile phones can support learning in college when "
                 "clear rules are followed.",
                 "(c) Phones are there.", "(d) Many students have phones."],
     "answer": "b",
     "explanation": "b names the topic and one clear point; the others "
                    "are vague or off-point.",
     "source": "", "skill": "Paragraphing", "module": "topic-sentences"},
    {"id": "d2", "type": "order", "kind": "repair",
     "prompt": "Put these in order to make a paragraph: [A] For example, "
               "students can look up difficult terms during a lecture. "
               "[B] Mobile phones can support learning in college when "
               "clear rules are followed. [C] Therefore, colleges should "
               "allow phones with clear limits. [D] They give instant "
               "access to reference material.",
     "options": ["B, D, A, C", "A, B, C, D", "D, C, B, A"],
     "answer": "B, D, A, C",
     "explanation": "B states the main idea first; D and A support it; "
                    "C concludes.",
     "source": "", "skill": "Paragraphing", "module": "topic-sentences"},
    {"id": "d3", "type": "write", "kind": "produce",
     "prompt": "Complete the topic sentence for your own paragraph: "
               "\"Plastic waste in rivers ______.\"",
     "options": [], "answer": "",
     "explanation": "Write one formal sentence stating a single main idea "
                    "about plastic waste in rivers.",
     "source": "", "skill": "Paragraphing", "module": "topic-sentences"},
]


def _demo_text_match(text: str, fixed: str) -> bool:
    """True when the text is the fixed script paragraph (spacing ignored)."""
    return " ".join(text.split()) == " ".join(fixed.split())


def _demo_practice_set() -> list[dict]:
    """Fresh copies of the fixed Paragraphing L1 set."""
    return [{**it, "options": list(it["options"])}
            for it in DEMO_PRACTICE_ITEMS]


def _demo_produce_fields(text: str) -> dict:
    """Demo judge for the produce item: one formal sentence, one main idea."""
    clean = (text or "").strip()
    sents = [s for s in re.split(r"[.!?]+", clean) if s.strip()]
    words = clean.split()
    lowered = clean.lower()
    chatty = any(re.search(rf"\b{re.escape(w)}\b", lowered)
                 for w in INFORMAL_WORDS)
    ok = (len(sents) == 1 and len(words) >= 6 and clean[:1].isupper()
          and re.search(r"[.!?]$", clean) is not None and not chatty)
    quote = clean if len(clean) <= 140 else clean[:137] + "..."
    if ok:
        return {"status": "ok",
                "strength": f"Good topic sentence: \"{quote}\".",
                "problem": "", "quote": quote,
                "next_action": "Keep going.", "score": 2}
    return {"status": "ok", "strength": "",
            "problem": f"Not yet: \"{quote}\"." if clean
                       else "You gave no answer here.",
            "quote": quote if clean else "no answer",
            "next_action": ("Write one formal sentence stating a single main "
                            "idea about plastic waste in rivers."),
            "score": 0}


# --- Feedback on your paragraph --------------------------------------------------
_LINKERS = ("and", "but", "because", "so", "therefore", "however", "then")
_CLAIM_MARKERS = ("because", "so", "therefore", "should", "for example",
                  "since")
_SOURCE_MARKERS = ("according to", "studies", "study shows", "research",
                    "says", "said")
_COMMON_WORDS = {"the", "a", "an", "and", "or", "but", "to", "of", "in",
                 "on", "is", "are", "was", "were", "it", "its", "i", "you",
                 "we", "they", "he", "she", "s", "t"}


def _text_sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", text.strip())
            if s.strip()]


def _skill_evidence(skill: str, text: str) -> str:
    """In-text quote showing the skill at work (fallback path)."""
    sents = _text_sentences(text)
    first = sents[0] if sents else text.strip()
    if skill == "Paragraphing":
        return first  # the (non-)topic sentence itself
    if skill == "Grammar":
        for sent in sents:
            if not sent[:1].isupper() or not re.search(r"[.!?]$", sent):
                return sent
        return first
    if skill == "Vocabulary":
        words = [w for w in re.findall(r"[A-Za-z']+", text.lower())
                 if w not in _COMMON_WORDS]
        if words:
            common = max(sorted(set(words)), key=words.count)
            for sent in sents:
                if re.search(r"\b" + re.escape(common) + r"\b", sent.lower()):
                    return sent
        return first
    if skill == "Sentence structure":
        for sent in sents:
            if any(re.search(r"\b" + link + r"\b", sent.lower())
                   for link in _LINKERS):
                return sent
        for sent in sents:
            if len(sent.split()) < 6 or len(sent.split()) > 25:
                return sent
        return first
    if skill == "Argument":
        for sent in sents:
            if any(m in sent.lower() for m in _CLAIM_MARKERS):
                return sent
        return first
    if skill == "Using sources":
        for sent in sents:
            if any(m in sent.lower() for m in _SOURCE_MARKERS) or '"' in sent:
                return sent
        return first
    if skill == "Academic tone":
        for sent in sents:
            if any(re.search(r"\b" + re.escape(w) + r"\b", sent.lower())
                   for w in INFORMAL_WORDS):
                return sent
        return first
    return first


def _heuristic_details(text: str, scores: dict) -> dict:
    """Per-skill level + rubric reason + in-text evidence (fallback path)."""
    details = {}
    for skill in SKILLS:
        level = level_for_score(scores[skill])
        details[skill] = {"level": level,
                          "reason": DIAGNOSE_RUBRIC[skill][level - 1],
                          "evidence": _skill_evidence(skill, text)}
    return details


SPARK_FEEDBACK_SYSTEM = (
    "You give feedback on a learner's paragraph for a first-year Indian "
    "undergraduate. Reply with a JSON object only, no other text. Use "
    "simple English: basic words, short lines. Use no emojis. Never praise "
    "in general words like 'great job', 'excellent' or 'amazing'. Quote "
    "the learner's exact words.")


def _feedback_messages(text: str, weakest_two: list) -> list[dict]:
    """Prompt: the paragraph plus its two weakest skills."""
    user = (f"Paragraph: {text} The two weakest skills are "
            f"{weakest_two[0]} and {weakest_two[1]}. Write strength (one "
            f"real strength quoting their words, or null when nothing is "
            f"good), problems (the two most important problems, each with "
            f"quote = exact words from the paragraph, wrong = what is "
            f"wrong, why = why it matters to a reader, fix = how to fix "
            f"it), model (rewrite exactly ONE of their sentences: before = "
            f"their sentence word-for-word, after = your improved version "
            f"as one sentence, changed = one line on what changed), "
            f"your_turn (one line asking them to fix the other lines the "
            f"same way).")
    return [{"role": "system", "content": SPARK_FEEDBACK_SYSTEM},
            {"role": "user", "content": user}]


def _validate_feedback_shape(data) -> dict | None:
    """Feedback keys present with the right types; model edits one sentence."""
    if not isinstance(data, dict):
        return None
    strength = data.get("strength")
    if strength is not None:
        if not isinstance(strength, dict):
            return None
        if not (strength.get("quote") or "").strip():
            return None
        if not (strength.get("line") or "").strip():
            return None
    problems = data.get("problems")
    if not isinstance(problems, list) or len(problems) != 2:
        return None
    for problem in problems:
        if not isinstance(problem, dict):
            return None
        for key in ("quote", "wrong", "why", "fix"):
            if not (problem.get(key) or "").strip():
                return None
    model = data.get("model")
    if model is not None:
        if not isinstance(model, dict):
            return None
        before = (model.get("before") or "").strip()
        after = (model.get("after") or "").strip()
        changed = (model.get("changed") or "").strip()
        if not before or not after or not changed:
            return None
        if len([s for s in re.split(r"[.!?]+", after) if s.strip()]) != 1:
            return None
    your_turn = (data.get("your_turn") or "").strip()
    if not your_turn:
        return None
    clean = lambda part, keys: {k: (part[k] or "").strip() for k in keys} \
        if part is not None else None
    return {"strength": clean(strength, ("quote", "line")),
            "problems": [clean(p, ("quote", "wrong", "why", "fix"))
                         for p in problems],
            "model": clean(model, ("before", "after", "changed")),
            "your_turn": your_turn}


def _feedback_verify_payload(feedback: dict, text: str) -> dict:
    """Model-written lines plus quotes, for the feedback checklist."""
    quotes = [p["quote"] for p in feedback["problems"]]
    fields = []
    if feedback.get("strength"):
        quotes.append(feedback["strength"]["quote"])
        fields.append(feedback["strength"]["line"])
    for problem in feedback["problems"]:
        fields.extend([problem["wrong"], problem["why"], problem["fix"]])
    model = feedback.get("model") or {}
    if model:
        quotes.append(model["before"])
        fields.extend([model["after"], model["changed"]])
    fields.append(feedback["your_turn"])
    motivation = feedback.get("motivation") or {}
    for fix in motivation.get("grammar_fixes", []):
        quotes.append(fix["wrong"])
        fields.extend([fix["right"], fix["rule"]])
    for tip in motivation.get("vocab_tips", []):
        fields.append(tip["tip"])
    fields.extend(motivation.get("improve", []))
    for key in ("critical_tip", "next_goal", "twin_message"):
        if motivation.get(key):
            fields.append(motivation[key])
    return {"text": text, "quotes": quotes, "fields": fields,
            "before": model.get("before", "") if model else "",
            "after": model.get("after", "") if model else ""}


def _feedback_with_spark(learner_id: int, text: str,
                         weakest_two: list) -> dict | None:
    """Feedback card passing the checklist, or None after retries."""
    if _model_api_key() is None:
        return None
    messages = _feedback_messages(text, weakest_two)
    for _ in range(1 + SPARK_MAX_REGENS):
        try:
            data = json.loads(_spark_chat(messages, temperature=0,
                                           timeout=SPARK_TIMEOUT_SLOW))
        except (SparkError, ValueError):
            continue
        fields = _validate_feedback_shape(data)
        if fields is None:
            continue
        verdict = verify("feedback", _feedback_verify_payload(fields, text))
        if verdict["pass"]:
            return fields
        store.log_event(learner_id, "Diagnose", "twin", "verify-feedback",
                        f"rejected: {verdict['failed']}")
    return None


# Deterministic why/fix lines per skill for the template fallback card.
SKILL_WHY_FIX = {
    "Grammar": ("Readers get lost when verbs go wrong.",
                "Check every he, she, and it."),
    "Vocabulary": ("Vague words hide your point.",
                   "Swap one weak word for a strong one."),
    "Sentence structure": ("Choppy lines tire the reader.",
                           "Join two short sentences with because."),
    "Paragraphing": ("Readers need the main point first.",
                     "Start with one line that tells the main idea."),
    "Argument": ("A claim alone will not convince anyone.",
                 "Add because and one reason."),
    "Using sources": ("Readers trust named sources.",
                      "Add 'According to' before one fact."),
    "Academic tone": ("Chatty words weaken your point.",
                      "Swap one chatty word for a calm one."),
}


FALLBACK_NOTICE = "Quick estimate - full feedback unavailable right now."


def _cap_fallback_scores(text: str, scores: dict) -> dict:
    """Cautious heuristic: at most L3, or L2 under three sentences."""
    cap = 39 if len(_text_sentences(text)) < 3 else 59
    return {skill: min(score, cap) for skill, score in scores.items()}


# --- Motivation layer (twin message, fixes, tips, goal) ----------------------
# Deterministic and quotable: every fix copies the learner's exact words.
TWIN_MOODS = {
    "strong": ("Outstanding work!", "\U0001F31F"),
    "good": ("You're thinking well!", "\U0001F44D"),
    "fair": ("Good effort - you're getting there!", "\U0001F4AA"),
    "weak": ("Every expert started here. Let's learn from this one!", "\U0001F331"),
}


def _twin_message(name: str, band: str, quote: str | None) -> str:
    """2-3 warm sentences: mood line, name, strength quote, one emoji."""
    mood, emoji = TWIN_MOODS[band]
    if band == "weak":
        if quote:
            mid = f"Your line '{quote}' needs one clear point."
        else:
            mid = "Your try needs one clear point."
        return (f"Every expert started here. Let's learn from this one! "
                f"{emoji} {name}, {mid[0].lower() + mid[1:]}")
    if quote:
        core = f"your line '{quote}' does the job"
    else:
        core = "you put real thoughts on paper"
    closer = {"strong": "Keep writing like this.",
              "good": "One small fix will lift it higher.",
              "fair": "Let's fix its weak spot together."}[band]
    return f"{mood} {emoji} {name}, {core}. {closer}"


_COMMON_MISSPELLINGS = {
    "recieve": "receive", "seperate": "separate", "occured": "occurred",
    "writting": "writing", "grammer": "grammar", "enviroment": "environment",
    "tommorow": "tomorrow", "freind": "friend", "beleive": "believe",
    "definately": "definitely", "goverment": "government",
    "knowlege": "knowledge",
}


def _grammar_fixes(text: str) -> list[dict]:
    """Up to 3 real errors: exact sentence, corrected, simple rule."""
    fixes = []
    for sent in _text_sentences(text):
        if len(fixes) >= 3:
            break
        if sent and sent[0].isalpha() and not sent[0].isupper():
            fixes.append({"wrong": sent, "right": sent[0].upper() + sent[1:],
                          "rule": "Start each sentence with a capital "
                                  "letter."})
            continue
        lowered = f" {sent} "
        if " i " in lowered:
            fixed = sent.replace(" i ", " I ", 1)
            fixes.append({"wrong": sent, "right": fixed,
                          "rule": "Write 'I' with a capital letter."})
            continue
        doubled = re.search(r"\b(\w+) \1\b", sent, re.IGNORECASE)
        if doubled:
            fixed = sent[:doubled.start()] + doubled.group(1) \
                + sent[doubled.end():]
            fixes.append({"wrong": sent, "right": fixed,
                          "rule": "Say each word once."})
            continue
        nospace = re.search(r"[.!?][A-Za-z]", sent)
        if nospace:
            at = nospace.start() + 1
            fixes.append({"wrong": sent, "right": sent[:at] + " " + sent[at:],
                          "rule": "Leave a space after each full stop."})
            continue
        article = re.search(r"\ba ([aeiouAEIOU])", sent)
        if article:
            fixed = sent[:article.start()] + "an " \
                + sent[article.start() + 2:]
            fixes.append({"wrong": sent, "right": fixed,
                          "rule": "Use 'an' before a, e, i, o and u."})
            continue
        for bad, good in _COMMON_MISSPELLINGS.items():
            hit = re.search(r"\b" + re.escape(bad) + r"\b", sent)
            if hit:
                fixed = sent[:hit.start()] + good + sent[hit.end():]
                fixes.append({"wrong": sent, "right": fixed,
                              "rule": f"The spelling is '{good}'."})
                break
    return fixes


VAGUE_TIPS = (
    ("nice", "Try 'important' in place of 'nice'."),
    ("very", "Drop 'very' and pick a stronger word."),
    ("good", "Try 'useful' in place of 'good'."),
    ("bad", "Try 'weak' in place of 'bad'."),
    ("big", "Try 'large' in place of 'big'."),
    ("small", "Try 'tiny' in place of 'small'."),
    ("things", "Name the things in place of 'things'."),
    ("stuff", "Name it exactly in place of 'stuff'."),
    ("a lot", "Say 'many' or 'much' in place of 'a lot'."),
    ("get", "Try 'receive' in place of 'get'."),
)


def _vocab_tips(text: str) -> list[dict]:
    """1-2 better word choices, only for words the learner used."""
    tips = []
    lowered = f" {(text or '').lower()} "
    for word, tip in VAGUE_TIPS:
        if len(tips) >= 2:
            break
        if re.search(r"(?<![a-z])" + re.escape(word) + r"(?![a-z])", lowered):
            tips.append({"word": word, "tip": tip})
    return tips


def _topic_word(text: str) -> str | None:
    """Most repeated content word: an honest link to their topic."""
    words = [w for w in re.findall(r"[A-Za-z']+", (text or "").lower())
             if w not in _COMMON_WORDS and len(w) > 3]
    if not words:
        return None
    return max(sorted(set(words)), key=words.count)


def _motivation_card(name: str, band: str, strength: dict | None, text: str,
                     actions: list[str], topic: str,
                     next_goal: str) -> dict:
    """Twin message, fixes, tips, improve points, critical tip, next goal."""
    quote = (strength or {}).get("quote")
    topic_word = _topic_word(text) or topic
    return {
        "twin_message": _twin_message(name, band, quote),
        "grammar_fixes": _grammar_fixes(text)[:3],
        "vocab_tips": _vocab_tips(text)[:2],
        "improve": actions[:3],
        "critical_tip": ("Ask yourself: why does "
                         f"{topic_word} matter to your reader?"),
        "next_goal": next_goal,
    }


def _template_feedback(skills_info: dict, weakest_two: list,
                       text: str) -> dict:
    """Deterministic card from skill reasons: two problems, no rewrite."""
    problems = []
    for skill in weakest_two:
        info = skills_info[skill]
        why, fix = SKILL_WHY_FIX[skill]
        problems.append({"quote": info["evidence"], "wrong": info["reason"],
                         "why": why, "fix": fix})
    sents = _text_sentences(text)
    if len(sents) > 1 and problems[0]["quote"] == problems[1]["quote"]:
        other = next((s for s in sents if s != problems[0]["quote"]), None)
        if other is not None:
            problems[1]["quote"] = other
    return {"strength": None, "problems": problems, "model": None,
            "your_turn": "Fix these two lines the same way, then rewrite "
                         "your paragraph below."}


# Fixed cards for the scripted demo paragraphs (no Spark on the demo path).
DEMO_FEEDBACK_WEAK = {
    "strength": {"quote": "fish is dying",
                 "line": "You name a clear result: fish are dying."},
    "problems": [
        {"quote": "Plastic is very big problem.",
         "wrong": "No clear topic sentence: the line does not say what the "
                  "paragraph will prove.",
         "why": "Readers need the main point first.",
         "fix": "Start with one line that names the problem and the place."},
        {"quote": "People throw the waste in river",
         "wrong": "Missing words: 'the waste in river' needs 'the' before "
                  "river.",
         "why": "Small grammar slips confuse readers.",
         "fix": "Write 'throw waste into the river'."},
    ],
    "model": {"before": "Plastic is very big problem.",
              "after": "Plastic waste is harming the river in my village.",
              "changed": "It names the problem and the place."},
    "your_turn": "Fix your other lines the same way, then rewrite your "
                 "paragraph below.",
}

DEMO_FEEDBACK_IMPROVED = {
    "strength": {"quote": "Plastic waste is seriously harming the river in "
                          "my village.",
                 "line": "Your first sentence names the problem and the "
                         "place."},
    "problems": [
        {"quote": "students can help by spreading awareness",
         "wrong": "No source is named for this idea.",
         "why": "Readers trust named sources.",
         "fix": "Add whose idea it is, or where you read it."},
        {"quote": "The panchayat should set up waste bins near the river, "
                  "and students can help by spreading awareness.",
         "wrong": "Two ideas share one long line.",
         "why": "Long lines tire the reader.",
         "fix": "Split it into two short lines."},
    ],
    "model": {"before": "People throw bottles and bags into the water, and "
                        "the fish are dying.",
              "after": "Bottles and bags in the water are killing the fish.",
              "changed": "Fewer words carry the same point."},
    "your_turn": "Fix your other lines the same way, then rewrite your "
                 "paragraph below.",
}

# Fixed motivation parts for the scripted demo cards (the twin message is
# built at serve time so it carries the learner's own first name).
DEMO_MOTIVATION_WEAK = {
    "grammar_fixes": [
        {"wrong": "Plastic is very big problem.",
         "right": "Plastic is a very big problem.",
         "rule": "Add 'a' before one thing."},
        {"wrong": "People throw the waste in river and fish is dying.",
         "right": "People throw the waste into the river and fish is dying.",
         "rule": "Use 'the' for a known place."},
        {"wrong": "Also the students also should know.",
         "right": "The students should also know.",
         "rule": "Say 'also' once."},
    ],
    "vocab_tips": [
        {"word": "very", "tip": "Drop 'very' and pick a stronger word."},
        {"word": "big", "tip": "Try 'large' in place of 'big'."},
    ],
    "improve": ["Make your first sentence say your main idea.",
                "Name one source."],
    "critical_tip": "Ask yourself: why does plastic matter to your reader?",
    "next_goal": "Next goal: Make your first sentence say your main idea.",
}

DEMO_MOTIVATION_IMPROVED = {
    "grammar_fixes": [],
    "vocab_tips": [
        {"word": "set up", "tip": "Try 'install' in place of 'set up'."},
    ],
    "improve": ["Name one source.",
                "Swap one chatty word for a calm one."],
    "critical_tip": "Ask yourself: why does plastic matter to your reader?",
    "next_goal": "Next goal: Name one source.",
}


# Concrete signs per skill for comparing two drafts: what weak vs strong
# looks like, the first fix, and the next step after an improvement.
COMPARE_NOTES = {
    "Grammar": {"weak": "verbs that do not agree", "strong": "verbs that agree",
                "first": "Check every he, she, and it.",
                "next": "Check every line for one more verb."},
    "Vocabulary": {"weak": "vague words like 'nice'", "strong": "precise words",
                   "first": "Swap one weak word for a strong one.",
                   "next": "Swap one more weak word."},
    "Sentence structure": {"weak": "short, choppy sentences", "strong": "joined sentences",
                           "first": "Join two short sentences with because.",
                           "next": "Join one more pair of sentences."},
    "Paragraphing": {"weak": "no topic sentence", "strong": "a topic sentence",
                     "first": "Start with one line that tells the main idea.",
                     "next": "Make your topic sentence narrower."},
    "Argument": {"weak": "claims with no reasons", "strong": "a claim with a reason",
                 "first": "Add because and one reason.",
                 "next": "Add one more reason."},
    "Using sources": {"weak": "no named sources", "strong": "a named source",
                      "first": "Add 'According to' before one fact.",
                      "next": "Name one more source."},
    "Academic tone": {"weak": "chatty words", "strong": "calm words",
                      "first": "Swap one chatty word for a calm one.",
                      "next": "Hunt one more chatty word."},
}


def compare_note(skill: str, prev_level: int, new_level: int) -> str:
    """One concrete sentence comparing this draft with the previous one."""
    notes = COMPARE_NOTES[skill]
    if new_level > prev_level:
        return (f"In your last paragraph you had {notes['weak']}; "
                f"this time you have {notes['strong']}. {notes['next']}")
    if new_level < prev_level:
        return (f"In your last paragraph you had {notes['strong']}; "
                f"this time you have {notes['weak']}. {notes['first']}")
    if new_level >= 2:
        return (f"Like your last paragraph, this one has {notes['strong']}. "
                f"{notes['next']}")
    return (f"Like your last paragraph, this one has {notes['weak']}. "
            f"{notes['first']}")


# --- Practice bank (demo content; Paragraphing L1-L2 are the planned items) ----------
# Item types: "mcq" (answer = option letter) or "order" (answer = "2,1,3").
PRACTICE_BANK: dict[tuple[str, int], list[dict]] = {
    ("Paragraphing", 1): [
        {"id": "p1-1", "type": "mcq",
         "prompt": "Which is the best topic sentence for a paragraph about Onam?",
         "options": ["A) Onam is nice.", "B) Onam is Kerala's biggest festival, "
                     "celebrated with feasts, flowers and boat races.",
                     "C) I like holidays."],
         "answer": "B",
         "explanation": "A topic sentence names the topic AND the main idea.",
         "variants": {
             "Science": {
                 "prompt": "Which is the best topic sentence for a lab report about evaporation?",
                 "options": ["A) Evaporation is nice.",
                             "B) Evaporation speeds up when temperature and airflow increase.",
                             "C) I like experiments."]},
             "Humanities": {
                 "prompt": "Which is the best topic sentence for an essay about the freedom struggle?",
                 "options": ["A) History is nice.",
                             "B) The freedom struggle united peasants, workers and students against colonial rule.",
                             "C) I like holidays."]},
             "Commerce": {
                 "prompt": "Which is the best topic sentence for a business report about sales?",
                 "options": ["A) Sales are nice.",
                             "B) Online sales grew 20% last quarter, driven by festival offers.",
                             "C) I like shopping."]},
         }},
        {"id": "p1-2", "type": "order",
         "prompt": "Put the paragraph in order. Sentences: 1) 'First, people "
                   "lay flower carpets called pookkalam.' 2) 'Onam is Kerala's "
                   "harvest festival.' 3) 'Finally, families share the Onasadya feast.'",
         "options": ["1,2,3", "2,1,3", "3,1,2"],
         "answer": "2,1,3",
         "explanation": "Topic sentence first, details next, closing line last.",
         "variants": {
             "Science": {
                 "prompt": "Put the paragraph in order. Sentences: 1) 'First, we "
                           "heated 100 ml of water to 80°C.' 2) 'This experiment tests "
                           "how temperature affects evaporation.' 3) 'Finally, we recorded "
                           "the water level every ten minutes.'",
                 "options": ["1,2,3", "2,1,3", "3,1,2"]},
             "Humanities": {
                 "prompt": "Put the paragraph in order. Sentences: 1) 'First, peasants "
                           "refused to pay the new tax.' 2) 'The revolt began as a protest "
                           "against unfair taxes.' 3) 'Finally, the rulers withdrew the tax.'",
                 "options": ["1,2,3", "2,1,3", "3,1,2"]},
             "Commerce": {
                 "prompt": "Put the paragraph in order. Sentences: 1) 'First, we surveyed "
                           "200 customers about prices.' 2) 'This report studies why store "
                           "sales fell last quarter.' 3) 'Finally, we suggest three ways to "
                           "win customers back.'",
                 "options": ["1,2,3", "2,1,3", "3,1,2"]},
         }},
        {"id": "p1-3", "type": "mcq",
         "prompt": "Which sentence does NOT belong in a paragraph about Onam?",
         "options": ["A) Children enjoy the holidays.",
                     "B) My bicycle has two wheels.",
                     "C) Boat races draw big crowds."],
         "answer": "B",
         "explanation": "Every sentence must connect to the paragraph's one idea.",
         "variants": {
             "Science": {
                 "prompt": "Which sentence does NOT belong in a paragraph about evaporation?",
                 "options": ["A) Warm air holds more vapour.",
                             "B) My bicycle has two wheels.",
                             "C) Wind speeds up drying."]},
             "Humanities": {
                 "prompt": "Which sentence does NOT belong in a paragraph about the freedom struggle?",
                 "options": ["A) Students joined the marches.",
                             "B) My bicycle has two wheels.",
                             "C) Workers went on strike."]},
             "Commerce": {
                 "prompt": "Which sentence does NOT belong in a paragraph about store sales?",
                 "options": ["A) Festival offers drew crowds.",
                             "B) My bicycle has two wheels.",
                             "C) Online orders doubled."]},
         }},
    ],
    ("Paragraphing", 2): [
        {"id": "p2-1", "type": "mcq",
         "prompt": "Pick the best supporting detail for: 'Onasadya is a grand meal.'",
         "options": ["A) It is served on a banana leaf with rice, curries and payasam.",
                     "B) Food is good.",
                     "C) I eat lunch daily."],
         "answer": "A",
         "explanation": "Details prove the topic sentence with specifics.",
         "variants": {
             "Science": {
                 "prompt": "Pick the best supporting detail for: 'The solution changed colour.'",
                 "options": ["A) It turned from blue to green as the temperature passed 60°C.",
                             "B) Colour is nice.",
                             "C) I mix liquids daily."]},
             "Humanities": {
                 "prompt": "Pick the best supporting detail for: 'The march was enormous.'",
                 "options": ["A) Over ten thousand people walked from the village to the fort.",
                             "B) Marches are good.",
                             "C) I walk daily."]},
             "Commerce": {
                 "prompt": "Pick the best supporting detail for: 'The quarter was profitable.'",
                 "options": ["A) Revenue rose 15% while costs stayed flat.",
                             "B) Money is good.",
                             "C) I earn daily."]},
         }},
        {"id": "p2-2", "type": "order",
         "prompt": "Order the paragraph. 1) 'They practise for weeks before the race.' "
                   "2) 'Vallamkali is Kerala's famous boat race.' "
                   "3) 'Long snake boats carry over a hundred rowers.' "
                   "4) 'So the whole village gathers at the riverside.'",
         "options": ["2,3,1,4", "1,2,3,4", "4,3,2,1"],
         "answer": "2,3,1,4",
         "explanation": "Topic -> description -> detail -> closing 'so' sentence.",
         "variants": {
             "Science": {
                 "prompt": "Order the paragraph. 1) 'We repeated each reading three times.' "
                           "2) 'This experiment measures how light affects plant growth.' "
                           "3) 'Two pots sat in sunlight and two in shade.' "
                           "4) 'So the shaded plants grew half as tall.'",
                 "options": ["2,3,1,4", "1,2,3,4", "4,3,2,1"]},
             "Humanities": {
                 "prompt": "Order the paragraph. 1) 'They marched for twelve days to reach the sea.' "
                           "2) 'The Salt March was a famous protest for freedom.' "
                           "3) 'Thousands of villagers joined the marchers.' "
                           "4) 'So the whole country watched the march.'",
                 "options": ["2,3,1,4", "1,2,3,4", "4,3,2,1"]},
             "Commerce": {
                 "prompt": "Order the paragraph. 1) 'Staff called fifty unhappy customers for feedback.' "
                           "2) 'This report studies our fall in repeat buyers.' "
                           "3) 'Most buyers complained about slow delivery.' "
                           "4) 'So faster delivery should win them back.'",
                 "options": ["2,3,1,4", "1,2,3,4", "4,3,2,1"]},
         }},
        {"id": "p2-3", "type": "mcq",
         "prompt": "Which closing sentence fits a paragraph about pookkalam?",
         "options": ["A) Thus the flower carpet shows the beauty of teamwork.",
                     "B) Flowers are colourful.",
                     "C) I must buy flowers."],
         "answer": "A",
         "explanation": "A closing line restates the main idea, not a new fact.",
         "variants": {
             "Science": {
                 "prompt": "Which closing sentence fits a lab report about evaporation?",
                 "options": ["A) Thus faster airflow clearly speeds up evaporation.",
                             "B) Water is useful.",
                             "C) I must buy a flask."]},
             "Humanities": {
                 "prompt": "Which closing sentence fits an essay about the march?",
                 "options": ["A) Thus the march showed the power of peaceful protest.",
                             "B) Walking is healthy.",
                             "C) I must buy shoes."]},
             "Commerce": {
                 "prompt": "Which closing sentence fits a report about falling sales?",
                 "options": ["A) Thus better delivery should restore our sales.",
                             "B) Shops are busy.",
                             "C) I must buy stock."]},
         }},
    ],
    ("Grammar", 1): [
        {"id": "g1-1", "type": "mcq",
         "prompt": "Choose the correct sentence.",
         "options": ["A) She go to school daily.", "B) She goes to school daily.",
                     "C) She going to school daily."],
         "answer": "B", "explanation": "He/she/it takes verb+s: goes.",
         "variants": {
             "Science": {
                 "prompt": "Choose the correct sentence for a lab report.",
                 "options": ["A) The solution boil at 100°C.",
                             "B) The solution boils at 100°C.",
                             "C) The solution boiling at 100°C."]},
             "Humanities": {
                 "prompt": "Choose the correct sentence for an essay.",
                 "options": ["A) The article discuss the revolt.",
                             "B) The article discusses the revolt.",
                             "C) The article discussing the revolt."]},
             "Commerce": {
                 "prompt": "Choose the correct sentence for a business report.",
                 "options": ["A) The report show a profit.",
                             "B) The report shows a profit.",
                             "C) The report showing a profit."]},
         }},
        {"id": "g1-2", "type": "mcq",
         "prompt": "Choose the correct article: '___ Onam is in Chingam.'",
         "options": ["A) A", "B) An", "C) No article needed"],
         "answer": "C", "explanation": "Festival names take no article.",
         "variants": {
             "Science": {
                 "prompt": "Choose the correct article: '___ Evaporation speeds up in summer.'",
                 "options": ["A) A", "B) An", "C) No article needed"],
                 "explanation": "Process names take no article."},
             "Humanities": {
                 "prompt": "Choose the correct article: '___ Freedom struggles need brave leaders.'",
                 "options": ["A) A", "B) An", "C) No article needed"],
                 "explanation": "General plural nouns take no article."},
             "Commerce": {
                 "prompt": "Choose the correct article: '___ Sales rose last quarter.'",
                 "options": ["A) A", "B) An", "C) No article needed"],
                 "explanation": "General plural nouns take no article."},
         }},
    ],
    ("Vocabulary", 1): [
        {"id": "v1-1", "type": "mcq",
         "prompt": "Pick the more academic word: 'The result was ___ .'",
         "options": ["A) very big", "B) significant", "C) really nice"],
         "answer": "B", "explanation": "'Significant' is precise academic vocabulary.",
         "variants": {
             "Science": {
                 "prompt": "Pick the more academic word: 'The temperature rise was ___ .'",
                 "options": ["A) very big", "B) significant", "C) really nice"]},
             "Humanities": {
                 "prompt": "Pick the more academic word: 'The effect of the law was ___ .'",
                 "options": ["A) very big", "B) significant", "C) really nice"]},
             "Commerce": {
                 "prompt": "Pick the more academic word: 'The profit growth was ___ .'",
                 "options": ["A) very big", "B) significant", "C) really nice"]},
         }},
        {"id": "v1-2", "type": "mcq",
         "prompt": "'Linkers' are words that ___ .",
         "options": ["A) join ideas (because, however)",
                     "B) name festivals", "C) end sentences"],
         "answer": "A", "explanation": "Linkers connect sentences and ideas.",
         "variants": {
             "Science": {
                 "prompt": "'Linkers' are words that ___ .",
                 "options": ["A) join ideas (since, therefore)",
                             "B) name chemicals", "C) end experiments"]},
             "Humanities": {
                 "prompt": "'Linkers' are words that ___ .",
                 "options": ["A) join ideas (however, because)",
                             "B) name kings", "C) end essays"]},
             "Commerce": {
                 "prompt": "'Linkers' are words that ___ .",
                 "options": ["A) join ideas (therefore, while)",
                             "B) name products", "C) end meetings"]},
         }},
    ],
    ("Sentence structure", 1): [
        {"id": "s1-1", "type": "mcq",
         "prompt": "Join with 'because': 'She stayed home. She was ill.'",
         "options": ["A) She stayed home because she was ill.",
                     "B) Because she stayed home she was ill.",
                     "C) She because stayed home she was ill."],
         "answer": "A", "explanation": "'Because' joins reason to result in order.",
         "variants": {
             "Science": {
                 "prompt": "Join with 'because': 'The flask cracked. It was heated too fast.'",
                 "options": ["A) The flask cracked because it was heated too fast.",
                             "B) Because the flask cracked it was heated too fast.",
                             "C) The flask because cracked it was heated too fast."]},
             "Humanities": {
                 "prompt": "Join with 'because': 'The villagers marched. They opposed the tax.'",
                 "options": ["A) The villagers marched because they opposed the tax.",
                             "B) Because the villagers marched they opposed the tax.",
                             "C) The villagers because marched they opposed the tax."]},
             "Commerce": {
                 "prompt": "Join with 'because': 'The shop closed early. Sales were slow.'",
                 "options": ["A) The shop closed early because sales were slow.",
                             "B) Because the shop closed early sales were slow.",
                             "C) The shop because closed early sales were slow."]},
         }},
        {"id": "s1-2", "type": "mcq",
         "prompt": "Which sentence is complete?",
         "options": ["A) Running fast down the road.",
                     "B) The children ran fast down the road.",
                     "C) When the race began."],
         "answer": "B", "explanation": "A sentence needs a subject + finite verb.",
         "variants": {
             "Science": {
                 "prompt": "Which sentence is complete?",
                 "options": ["A) Heating the flask gently.",
                             "B) The students heated the flask gently.",
                             "C) When the reading settled."]},
             "Humanities": {
                 "prompt": "Which sentence is complete?",
                 "options": ["A) Marching to the fort.",
                             "B) The villagers marched to the fort.",
                             "C) When the speech ended."]},
             "Commerce": {
                 "prompt": "Which sentence is complete?",
                 "options": ["A) Counting the day's cash.",
                             "B) The manager counted the day's cash.",
                             "C) When the shop closed."]},
         }},
    ],
    ("Argument", 1): [
        {"id": "a1-1", "type": "mcq",
         "prompt": "Which is a claim (not a fact)?",
         "options": ["A) Onam falls in Chingam.",
                     "B) Every school should teach art.",
                     "C) Rice is served on a leaf."],
         "answer": "B", "explanation": "A claim argues something that needs proof.",
         "variants": {
             "Science": {
                 "prompt": "Which is a claim (not a fact)?",
                 "options": ["A) Water boils at 100°C.",
                             "B) Every lab should recycle its chemicals.",
                             "C) Salt dissolves in water."]},
             "Humanities": {
                 "prompt": "Which is a claim (not a fact)?",
                 "options": ["A) The march reached the sea in April.",
                             "B) Every school should teach art.",
                             "C) The fort has four gates."]},
             "Commerce": {
                 "prompt": "Which is a claim (not a fact)?",
                 "options": ["A) Sales rose 10% in March.",
                             "B) Every shop should open on Sundays.",
                             "C) Cash is kept in the safe."]},
         }},
        {"id": "a1-2", "type": "mcq",
         "prompt": "Which best supports: 'Reading builds vocabulary'?",
         "options": ["A) My friend reads comics.",
                     "B) Studies show readers meet thousands of new words yearly.",
                     "C) Books have pages."],
         "answer": "B", "explanation": "Evidence must directly prove the claim.",
         "variants": {
             "Science": {
                 "prompt": "Which best supports: 'Boiling kills germs'?",
                 "options": ["A) My friend boils milk.",
                             "B) Lab tests show boiled water has almost no live germs.",
                             "C) Pots have lids."]},
             "Humanities": {
                 "prompt": "Which best supports: 'The march united the village'?",
                 "options": ["A) My friend likes marches.",
                             "B) Records show farmers, traders and teachers marched together.",
                             "C) Roads are long."]},
             "Commerce": {
                 "prompt": "Which best supports: 'Lower prices raise sales'?",
                 "options": ["A) My friend likes discounts.",
                             "B) Store data shows sales doubled during the discount week.",
                             "C) Shops have doors."]},
         }},
    ],
    ("Using sources", 1): [
        {"id": "u1-1", "type": "mcq",
         "prompt": "Which sentence cites a source correctly?",
         "options": ["A) According to the textbook, plants need sunlight.",
                     "B) Plants need sunlight, I think.",
                     "C) Sunlight sunlight plants."],
         "answer": "A", "explanation": "'According to X' names the source.",
         "variants": {
             "Science": {
                 "prompt": "Which sentence cites a source correctly?",
                 "options": ["A) According to the textbook, plants need sunlight.",
                             "B) Plants need sunlight, I think.",
                             "C) Sunlight sunlight plants."]},
             "Humanities": {
                 "prompt": "Which sentence cites a source correctly?",
                 "options": ["A) According to the history book, the revolt began in Meerut.",
                             "B) The revolt began in Meerut, I think.",
                             "C) Revolt revolt Meerut."]},
             "Commerce": {
                 "prompt": "Which sentence cites a source correctly?",
                 "options": ["A) According to the sales report, revenue peaks in December.",
                             "B) Revenue peaks in December, I think.",
                             "C) Revenue revenue December."]},
         }},
        {"id": "u1-2", "type": "mcq",
         "prompt": "Copying a sentence without naming the writer is ___ .",
         "options": ["A) plagiarism", "B) planning", "C) proofreading"],
         "answer": "A", "explanation": "Always credit the source.",
         "variants": {
             "Science": {
                 "prompt": "Copying a lab result without naming the writer is ___ .",
                 "options": ["A) plagiarism", "B) planning", "C) proofreading"]},
             "Humanities": {
                 "prompt": "Copying a paragraph without naming the writer is ___ .",
                 "options": ["A) plagiarism", "B) planning", "C) proofreading"]},
             "Commerce": {
                 "prompt": "Copying a report figure without naming the writer is ___ .",
                 "options": ["A) plagiarism", "B) planning", "C) proofreading"]},
         }},
    ],
    ("Academic tone", 1): [
        {"id": "t1-1", "type": "mcq",
         "prompt": "Pick the more academic sentence.",
         "options": ["A) The result was really good.",
                     "B) The result was significant.",
                     "C) Wow, great result!"],
         "answer": "B", "explanation": "Academic tone avoids chatty words.",
         "variants": {
             "Science": {
                 "prompt": "Pick the more academic sentence for a lab report.",
                 "options": ["A) The result was really good.",
                             "B) The result was significant.",
                             "C) Wow, great result!"]},
             "Humanities": {
                 "prompt": "Pick the more academic sentence for an essay.",
                 "options": ["A) The essay was really good.",
                             "B) The essay was persuasive.",
                             "C) Wow, great essay!"]},
             "Commerce": {
                 "prompt": "Pick the more academic sentence for a business report.",
                 "options": ["A) The quarter was really good.",
                             "B) The quarter was profitable.",
                             "C) Wow, great quarter!"]},
         }},
        {"id": "t1-2", "type": "mcq",
         "prompt": "Which sentence hedges politely?",
         "options": ["A) This proves everyone is wrong.",
                     "B) This suggests the plan may need changes.",
                     "C) This is the best ever."],
         "answer": "B", "explanation": "'Suggests/may' soften claims politely.",
         "variants": {
             "Science": {
                 "prompt": "Which sentence hedges politely?",
                 "options": ["A) This proves every chemist is wrong.",
                             "B) This suggests the mixture may need heating.",
                             "C) This is the best ever."]},
             "Humanities": {
                 "prompt": "Which sentence hedges politely?",
                 "options": ["A) This proves every king was wrong.",
                             "B) This suggests the policy may have failed.",
                             "C) This is the best ever."]},
             "Commerce": {
                 "prompt": "Which sentence hedges politely?",
                 "options": ["A) This proves every rival is wrong.",
                             "B) This suggests the plan may need changes.",
                             "C) This is the best ever."]},
         }},
    ],
}


# Practice bank variants are written in three genre families; each curriculum
# discipline maps to the closest one (lab-flavoured, essay-flavoured, report).
PRACTICE_VARIANT_FOR = {
    "Sciences": "Science", "Technology": "Science", "Medicine": "Science",
    "Arts & Humanities": "Humanities", "Social Sciences": "Humanities",
    "Commerce & Management": "Commerce",
}


def practice_items_for(skill: str, level: int,
                       discipline: str | None = None) -> list[dict]:
    """Demo bank lookup with fallback: exact level -> L1 -> Paragraphing L1.

    With a discipline, each item's prompt/options come from its genre-family
    variant (ids, answers, and explanations stay aligned); without one, the
    generic base items are returned (used by teacher sets).
    """
    base = (PRACTICE_BANK.get((skill, level))
            or PRACTICE_BANK.get((skill, 1))
            or PRACTICE_BANK[("Paragraphing", 1)])
    if discipline is None:
        return base
    family = PRACTICE_VARIANT_FOR.get(discipline, discipline)
    rendered = []
    for item in base:
        variant = (item.get("variants") or {}).get(family)
        if not variant:
            rendered.append(item)
            continue
        new = dict(item)
        new["prompt"] = variant.get("prompt", item["prompt"])
        new["options"] = list(variant.get("options", item["options"]))
        if "explanation" in variant:
            new["explanation"] = variant["explanation"]
        rendered.append(new)
    return rendered


def check_answer(item: dict, given: str) -> bool:
    """Case-insensitive comparison after stripping whitespace."""
    return (given or "").strip().lower() == item["answer"].strip().lower()


# --- Unified Verifier (checklist: docs/plan.md) ---------------------------------------
# Single gate before the learner sees anything. Replies only in JSON:
# {"pass": bool, "failed": [rule ids], "fix": one-line fix or ""}.
VERIFY_FIXES = {
    "not-empty": "Fill in the missing text.",
    "non-empty": "Add at least one item.",
    "unique-id": "Give every item a non-empty, unique id.",
    "no-generic-praise": "Remove generic praise; name the exact improvement instead.",
    "no-invented-examples": "Use an excerpt from the knowledge base and cite its source.",
    "valid-type": "Set type to 'mcq' or 'order'.",
    "min-options": "Add at least 2 options.",
    "has-answer": "Add the answer.",
    "answer-matches-option": "Make the answer match one option.",
    "has-explanation": "Add an explanation (learners need feedback).",
    "grounded-in-excerpt": "Use an excerpt that supports every claim.",
    "has-controlling-idea": "Give the model a clear controlling idea: a verb like "
                            "explains, shows, should, because, or why.",
    "not-task-topic": "Put the model on a different topic: it must not share "
                      "the task's topic word.",
    "grounded-in-excerpts": "Quote example sentences word-for-word from the "
                            "shown excerpts.",
    "valid-score": "Score the attempt 0, 1 or 2.",
    "feedback-shape": "Give 2-4 short feedback sentences.",
    "quotes-learner": "Quote the learner's own words in the feedback.",
    "quotes-in-text": "Quote only words that exist in the learner's text.",
    "one-rewrite": "Rewrite at most one sentence, as one sentence.",
    "simple-english": "Use basic words and short lines.",
    "grammar-quotes": "Copy each grammar error exactly from the learner's text.",
}

# Structural subset for the curated bank (exempt from no-invented-examples).
PRACTICE_STRUCTURAL_RULES = ["unique-id", "not-empty", "valid-type",
                             "min-options", "has-answer",
                             "answer-matches-option", "has-explanation"]

_PRACTICE_RULE_MESSAGES = {
    "unique-id": "missing or duplicate id.",
    "not-empty": "empty prompt.",
    "valid-type": "type must be 'mcq' or 'order'.",
    "min-options": "need at least 2 options.",
    "has-answer": "missing answer.",
    "has-explanation": "missing explanation (learners need feedback).",
    "no-invented-examples": "missing book source (every example must come from the knowledge base).",
}


def _quoted_spans(text: str) -> list[str]:
    """Double- and single-quoted spans, without the quote marks."""
    spans = re.findall(r'"([^"]+)"', text or "")
    spans += re.findall(r"'([^']+)'", text or "")
    return spans


def _reply_has_invented_example(reply: str, message: str | None) -> bool:
    """True when the reply quotes a complete sentence it should not have.

    Allowed quotes: the learner's own words, sentence starters with ___,
    passages marked with ... . Anything else quoted with sentence-ending
    punctuation is an invented example: book examples must arrive as
    excerpts with their source instead.
    """
    learner = message or ""
    for span in _quoted_spans(reply or ""):
        if not re.search(r"[.!?]", span):
            continue  # bare words like 'very' are not examples
        if "___" in span or "..." in span:
            continue
        core = span.strip().rstrip(".!?").strip()
        if core and (span.strip() in learner or core in learner):
            continue  # quoting the learner's own words
        return True
    return False


def _verify_twin_reply_rules(reply: str, message: str | None) -> list[str]:
    if not (reply or "").strip():
        return ["not-empty"]
    failed = []
    if _has_generic_praise(reply):
        failed.append("no-generic-praise")
    if _reply_has_invented_example(reply, message):
        failed.append("no-invented-examples")
    return failed


def _verify_practice_item_rules(item: dict) -> list[str]:
    if not isinstance(item, dict):
        return ["not-empty"]
    failed = []
    if not (item.get("prompt") or "").strip():
        failed.append("not-empty")
    if item.get("type") not in ("mcq", "order"):
        failed.append("valid-type")
    options = item.get("options") or []
    if len(options) < 2:
        failed.append("min-options")
    answer = (item.get("answer") or "").strip()
    if not answer:
        failed.append("has-answer")
    elif item.get("type") == "mcq" and not any(
            str(o).strip().lower().lstrip("(").startswith(answer.lower())
            for o in options):
        failed.append("answer-matches-option")
    if not (item.get("explanation") or "").strip():
        failed.append("has-explanation")
    if not (item.get("source") or "").strip():
        failed.append("no-invented-examples")
    return failed


def _verify_lesson_idea_rules(payload: dict) -> list[str]:
    """One failure per idea claim the excerpt does not support."""
    claims = LESSON_IDEA_CLAIMS.get((payload or {}).get("module"), [])
    excerpt = ((payload or {}).get("excerpt") or "").lower()
    failed = []
    for i, claim in enumerate(claims):
        if not any(k in excerpt for k in claim["keywords"]):
            failed.append(f"claim {i + 1} ({claim['label']}): grounded-in-excerpt")
    return failed


# Claim verbs that mark a controlling idea (a point being made, not a topic
# being named). "must"/"need" are excluded: on their own they urge without
# saying anything specific ("must get more care" states no point).
WORKED_CONTROL_MARKERS = ("explain", "explains", "show", "shows", "prove",
                          "proves", "should", "because", "why")


def _verify_assessor_rules(payload: dict) -> list[str]:
    """An assessment must score 0-2, run 2-4 sentences, quote the learner."""
    payload = payload or {}
    failed = []
    score = payload.get("score")
    if not isinstance(score, int) or isinstance(score, bool) \
            or score not in (0, 1, 2):
        failed.append("valid-score")
    sents = [s for s in re.split(r"[.!?]+", (payload.get("feedback") or "").strip())
             if s.strip()]
    if not 2 <= len(sents) <= 4:
        failed.append("feedback-shape")
    if (payload.get("status") or "ok") == "ok":
        quote = _normalized(payload.get("quote") or "")
        if len(quote) < 4 \
                or quote not in _normalized(payload.get("attempt") or "") \
                or quote not in _normalized(payload.get("feedback") or ""):
            failed.append("quotes-learner")
    attempt = _normalized(payload.get("attempt") or "")
    if any(len(_normalized(q)) < 4 or _normalized(q) not in attempt
           for q in payload.get("grammar_quotes") or []):
        failed.append("grammar-quotes")
    fields = [f for f in payload.get("fields") or [] if (f or "").strip()]
    if any(not _uses_simple_english(f) for f in fields):
        failed.append("simple-english")
    if any(_has_generic_praise(f) for f in fields):
        failed.append("no-generic-praise")
    return failed


def _verify_feedback_rules(payload: dict) -> list[str]:
    """Feedback quotes the learner, rewrites one sentence, stays simple."""
    payload = payload or {}
    failed = []
    flat = _normalized(payload.get("text") or "")
    quotes = payload.get("quotes") or []
    if not quotes or any(len(_normalized(q)) < 4 or _normalized(q) not in flat
                         for q in quotes):
        failed.append("quotes-in-text")
    after = (payload.get("after") or "").strip()
    if after:
        sents = [s for s in re.split(r"[.!?]+", after) if s.strip()]
        before = _normalized(payload.get("before") or "")
        if len(sents) != 1 or not before or _normalized(after) == before:
            failed.append("one-rewrite")
    fields = payload.get("fields") or []
    if any(not _uses_simple_english(f) for f in fields):
        failed.append("simple-english")
    if any(_has_generic_praise(f) for f in fields):
        failed.append("no-generic-praise")
    return failed


def _verify_excerpt_grounding_rules(payload: dict) -> list[str]:
    """One failure per item quoting no excerpt sentence verbatim."""
    payload = payload or {}
    sentences = []
    for excerpt in payload.get("excerpts") or []:
        sentences.extend(clean_sentences(excerpt))
    failed = []
    for i, item in enumerate(payload.get("items") or []):
        if not _item_grounded(item if isinstance(item, dict) else {},
                              sentences):
            failed.append(f"item {i + 1}: grounded-in-excerpts")
    return failed


def _verify_worked_model_rules(payload: dict) -> list[str]:
    """A worked model must argue its own topic, off the task topic."""
    payload = payload or {}
    model = payload.get("model") or ""
    task_words = (set(re.findall(r"[a-z]+", (payload.get("task_topic") or "").lower()))
                  - _STOPWORDS)
    failed = []
    if not re.search(r"\b(" + "|".join(WORKED_CONTROL_MARKERS) + r")\b",
                     model, re.IGNORECASE):
        failed.append("has-controlling-idea")
    if task_words & set(re.findall(r"[a-z]+", model.lower())):
        failed.append("not-task-topic")
    return failed


def verify(kind: str, payload, context: dict | None = None,
           rules: list[str] | None = None) -> dict:
    """Run the docs/plan.md checklist. Replies only in JSON.

    kind: "twin_reply" | "practice_item" | "practice_set" | "lesson_idea"
      | "worked_model" | "excerpt_grounding" | "assessor" | "feedback".
    context: {"message": learner text} for twin replies.
    rules: optional subset of rule ids (used for the curated bank).
    """
    context = context or {}
    if kind == "twin_reply":
        failed = [r for r in _verify_twin_reply_rules(
            payload, context.get("message")) if rules is None or r in rules]
    elif kind == "practice_item":
        failed = [r for r in _verify_practice_item_rules(payload)
                  if rules is None or r in rules]
    elif kind == "lesson_idea":
        failed = _verify_lesson_idea_rules(payload)
    elif kind == "worked_model":
        failed = _verify_worked_model_rules(payload)
    elif kind == "excerpt_grounding":
        failed = _verify_excerpt_grounding_rules(payload)
    elif kind == "assessor":
        failed = _verify_assessor_rules(payload)
    elif kind == "feedback":
        failed = _verify_feedback_rules(payload)
    elif kind == "practice_set":
        failed = []
        if not payload:
            failed = ["non-empty"]
        else:
            seen_ids: set[str] = set()
            for i, item in enumerate(payload):
                item_id = item.get("id", "") if isinstance(item, dict) else ""
                if (rules is None or "unique-id" in rules) and (
                        not item_id or item_id in seen_ids):
                    failed.append(f"item {i + 1}: unique-id")
                seen_ids.add(item_id)
                for r in _verify_practice_item_rules(item):
                    if rules is None or r in rules:
                        failed.append(f"item {i + 1}: {r}")
    else:
        raise ValueError(f"Unknown verify kind: {kind}")
    passed = not failed
    first = failed[0].split(": ")[-1] if failed else ""
    return {"pass": passed, "failed": failed,
            "fix": "" if passed else VERIFY_FIXES[first]}


def _practice_failure_message(items: list, entry: str) -> str:
    """Map a "item N: rule" failure back to the legacy human message."""
    where, _, rule = entry.partition(": ")
    if rule == "answer-matches-option":
        try:
            answer = items[int(where.split()[1]) - 1].get("answer", "")
        except (IndexError, ValueError, AttributeError):
            answer = ""
        return f"{where}: answer '{answer}' matches no option."
    return f"{where}: {_PRACTICE_RULE_MESSAGES[rule]}"


def verify_practice_set(items: list[dict]) -> list[str]:
    """Return a list of problems (empty = passed). Rules are deliberately strict.

    Structural checklist only (legacy interface); generated sets go through
    verify("practice_set") with the full checklist instead.
    """
    result = verify("practice_set", items, rules=PRACTICE_STRUCTURAL_RULES)
    messages = []
    for entry in result["failed"]:
        if entry == "non-empty":
            messages.append("Practice set is empty.")
        else:
            messages.append(_practice_failure_message(items, entry))
    return messages


# First keyword match wins, so specific phrases come before bare words
# ("topic sentence" must beat "sentence").
TEACHER_SKILL_KEYWORDS = [
    ("Paragraphing", ["topic sentence", "paragraph", "coherence", "unity", "developing"]),
    ("Argument", ["thesis", "argument", "claim", "evidence"]),
    ("Using sources", ["citation", "cite", "reference", "sources", "plagiarism", "bibliography"]),
    ("Academic tone", ["tone", "formal", "hedging"]),
    ("Sentence structure", ["sentence structure", "flow", "clause", "fragment", "run-on", "sentence"]),
    ("Grammar", ["grammar", "tense", "subject-verb", "article", "punctuation", "verb"]),
    ("Vocabulary", ["vocabulary", "word choice", "synonym", "linker"]),
]

TEACHER_SKILL_LABELS = {
    "Paragraphing": "paragraphs", "Argument": "arguments",
    "Using sources": "using sources", "Academic tone": "academic tone",
    "Sentence structure": "sentence structure", "Grammar": "grammar",
    "Vocabulary": "vocabulary",
}

TEACHER_EXPLANATIONS = {
    "Paragraphing": "Main idea first, details next, closing last.",
    "Argument": "Claim first, then the reason that proves it.",
    "Using sources": "The source is named before the borrowed idea.",
    "Academic tone": "Calm, exact words carry the point.",
    "Sentence structure": "Ideas join in reason order.",
    "Grammar": "Every sentence keeps subject and verb in agreement.",
    "Vocabulary": "One exact word does the work.",
}

# "Social sciences" must be checked before "science" (substring).
TEACHER_DISCIPLINE_WORDS = [
    ("Social Sciences", ["social sciences"]),
    ("Sciences", ["sciences", "science"]),
    ("Technology", ["technology", "technical", "engineering"]),
    ("Medicine", ["medicine", "medical", "health", "nursing"]),
    ("Arts & Humanities", ["arts & humanities", "humanities", "arts", "history", "literature"]),
    ("Commerce & Management", ["commerce & management", "commerce", "management", "business"]),
]


def parse_teacher_request(request_text: str) -> dict:
    """Pull skill, count (1-10), level (1-5) and discipline from a request."""
    lowered = (request_text or "").lower()
    skill = next((s for s, kws in TEACHER_SKILL_KEYWORDS
                  if any(k in lowered for k in kws)), "Paragraphing")
    count_match = re.search(r"(\d+)\s*(practice\s+)?(items?|questions?)", lowered)
    count = max(1, min(10, int(count_match.group(1)))) if count_match else 3
    level_match = re.search(r"level\s*([1-5])", lowered)
    level = int(level_match.group(1)) if level_match else 1
    discipline = next((d for d, words in TEACHER_DISCIPLINE_WORDS
                       if any(w in lowered for w in words)), None)
    return {"skill": skill, "count": count, "level": level, "discipline": discipline}


def _excerpt_sentences(doc: str, max_n: int = 12) -> list[str]:
    """Cleaned sentences of one excerpt, preferring substantial ones."""
    parts = clean_sentences(doc)
    long = [p for p in parts if len(p) >= 25]
    return (long if len(long) >= 2 else parts)[:max_n]


def _teacher_source(meta: dict) -> tuple:
    """(source, chapter, license) provenance for a generated item."""
    return meta.get("source"), meta.get("chapter"), meta.get("license")


def _teacher_explanation(skill: str, meta: dict) -> str:
    cite = meta.get("source") or "unknown source"
    if meta.get("chapter"):
        cite += f", {meta['chapter']}"
    return f"{TEACHER_EXPLANATIONS[skill]} From {cite}."


def _teacher_order_item(num: int, sentences: list[str], meta: dict, skill: str) -> dict:
    """Order-the-paragraph item from excerpt sentences in guide order."""
    window = sentences[:4]
    n = len(window)
    numbered = " ".join(f"{i + 1}) '{s}'" for i, s in enumerate(window))
    correct = ",".join(str(i + 1) for i in range(n))
    rev = ",".join(str(n - i) for i in range(n))
    rot = ",".join(str((i + 1) % n + 1) for i in range(n))
    options = []
    for order in (correct, rev, rot):
        if order not in options:
            options.append(order)
    options = options[num % len(options):] + options[:num % len(options)]
    source, chapter, license = _teacher_source(meta)
    return {"id": f"t{num + 1}", "type": "order",
            "prompt": f"Put the paragraph in order. Sentences: {numbered}",
            "options": options, "answer": correct,
            "explanation": _teacher_explanation(skill, meta),
            "source": source, "chapter": chapter, "license": license}


def _teacher_mcq_item(num: int, correct: str, distractors: list[str],
                      meta: dict, skill: str) -> dict:
    """Recognition item: the guide sentence among other excerpts' sentences."""
    options = [correct, *distractors[:3]]
    options = options[(num + 1) % len(options):] + options[:(num + 1) % len(options)]
    letters = "ABCD"[:len(options)]
    lettered = [f"{letter}) {s}" for letter, s in zip(letters, options)]
    source, chapter, license = _teacher_source(meta)
    return {"id": f"t{num + 1}", "type": "mcq",
            "prompt": f"Which sentence gives advice on {TEACHER_SKILL_LABELS[skill]}?",
            "options": lettered, "answer": letters[options.index(correct)],
            "explanation": _teacher_explanation(skill, meta),
            "source": source, "chapter": chapter, "license": license}


# --- Muse Spark item drafting (excerpt-grounded) ----------------------------------
# Teacher sets are drafted by Muse Spark over retrieved ChromaDB excerpts, then
# gated: every kept item must pass the practice_item checklist AND quote an
# excerpt sentence word-for-word. Provenance (source/chapter/license) is always
# resolved server-side from the excerpt's metadata, never from model output.
# Anything ungrounded is dropped and template-built items fill the count, so
# the set stays excerpt-only even when Spark invents or the API is down.
SPARK_CHAT_URL = "https://api.meta.ai/v1/chat/completions"
SPARK_MODEL = "muse-spark-1.3"
SPARK_TIMEOUT = 20
# Slower lane for the interactive writing loop only (Diagnoser, Write
# feedback card, Learn Assessor): long JSON answers need more room.
SPARK_TIMEOUT_SLOW = 40
# Verifier retry budget, shared by every Spark path: 1 initial attempt plus
# at most 2 regenerations, then the safe template or deterministic response.
SPARK_MAX_REGENS = 2


class SparkError(Exception):
    """Muse Spark call failed; the caller falls back to templates."""


def _spark_post(url: str, body: dict, key: str, timeout: int) -> dict:
    """POST JSON to the Model API; return the decoded response (mock point).

    HTTP errors keep the API's status and message so backend logs show the
    real failure instead of a bare status line.
    """
    req = urllib.request.Request(
        url, data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json",
                 "Authorization": f"Bearer {key}"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as res:
            return json.loads(res.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        try:
            detail = exc.read().decode("utf-8", "replace")[:300]
        except Exception:
            detail = ""
        raise SparkError(f"HTTP {exc.code}: {detail or exc.reason}") from exc
    except TimeoutError as exc:
        raise SparkError(f"request timed out after {timeout}s") from exc


def _spark_chat(messages: list[dict],
                temperature: float | None = None,
                timeout: int = SPARK_TIMEOUT) -> str:
    """One JSON-mode chat completion; assistant text, or raise SparkError."""
    key = _model_api_key()
    if not key:
        raise SparkError("no API key")
    body = {"model": SPARK_MODEL, "messages": messages,
            "response_format": {"type": "json_object"}}
    if temperature is not None:
        body["temperature"] = temperature
    try:
        data = _spark_post(SPARK_CHAT_URL, body, key, timeout)
        return data["choices"][0]["message"]["content"]
    except SparkError:
        raise
    except Exception as exc:
        raise SparkError(str(exc)) from exc


SPARK_TEACHER_SYSTEM = (
    "You write English-writing practice items for first-year Indian "
    "undergraduates. Use ONLY the numbered excerpts below: every example "
    "sentence in every item must be copied word-for-word from the excerpts. "
    "Never invent examples. Reply with a JSON array only, no other text. "
    "Each item is an object with type (mcq or order), prompt, options, "
    "answer, and answerExcerpt (the excerpt number holding the answer, like "
    "E2). For mcq: options are sentences labelled A) B) C), answer is the "
    "correct letter. For order: the prompt embeds the sentences as "
    "1) '...' 2) '...', options are orderings like 1,2 and answer is the "
    "correct ordering.")


def _shown_excerpts(pool: list, max_docs: int = 8, max_chars: int = 600) -> list:
    """(text, meta) pairs Spark may quote, trimmed at sentence ends."""
    shown = []
    for doc, meta in pool[:max_docs]:
        text = ""
        for sent in clean_sentences(doc):
            if text and len(text) + 1 + len(sent) > max_chars:
                break
            text = f"{text} {sent}".strip()
        if text:
            shown.append((text, meta or {}))
    return shown


def _spark_teacher_messages(shown: list, request_text: str,
                            parsed: dict, note: str) -> list[dict]:
    """Prompt: the teacher ask plus the quotable excerpts."""
    lines = [f"E{i + 1}: {text}" for i, (text, _) in enumerate(shown)]
    user = (f"Teacher request: {request_text} Skill: {parsed['skill']}. "
            f"Level: {parsed['level']}. Write exactly {parsed['count']} items, "
            f"alternating order, mcq, order, mcq and so on.")
    if (note or "").strip():
        user += f" Teacher note: {(note or '').strip()}."
    user += " Excerpts (quote these word-for-word):\n" + "\n".join(lines)
    return [{"role": "system", "content": SPARK_TEACHER_SYSTEM},
            {"role": "user", "content": user}]


def _resolve_spark_item(draft: dict, shown: list, skill: str) -> dict | None:
    """A draft with server-side provenance, or None when malformed."""
    if not isinstance(draft, dict) or draft.get("type") not in ("mcq", "order"):
        return None
    prompt, options, answer = (draft.get("prompt"), draft.get("options"),
                               draft.get("answer"))
    if not prompt or not isinstance(options, list) or len(options) < 2:
        return None
    if not answer or not all(isinstance(o, str) and o.strip() for o in options):
        return None
    ref = re.fullmatch(r"E(\d+)", str(draft.get("answerExcerpt") or "").strip())
    meta = (shown[int(ref.group(1)) - 1][1]
            if ref and 0 < int(ref.group(1)) <= len(shown)
            else shown[0][1])
    source, chapter, license = _teacher_source(meta)
    return {"id": "sx", "type": draft["type"], "prompt": str(prompt).strip(),
            "options": [o.strip() for o in options],
            "answer": str(answer).strip(),
            "explanation": _teacher_explanation(skill, meta),
            "source": source, "chapter": chapter, "license": license}


def _normalized(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").lower()).strip()


def _item_grounded(item: dict, sentences: list[str]) -> bool:
    """An excerpt sentence quoted verbatim in the prompt or options."""
    blob = _normalized(item.get("prompt", "") + " " +
                       " ".join(item.get("options") or []))
    return any(s and s in blob for s in (_normalized(s) for s in sentences))


def _spark_draft_items(shown: list, request_text: str, parsed: dict,
                       note: str) -> list[dict]:
    """Spark's items that pass structure + grounding (raises SparkError).

    Regenerates up to SPARK_MAX_REGENS times while short, merging new
    passing drafts; the caller backfills whatever is still missing. No key
    check here: _spark_chat raises SparkError when keyless, which the loop
    treats as a failed attempt.
    """
    messages = _spark_teacher_messages(shown, request_text, parsed, note)
    sentences = [s for text, _ in shown for s in clean_sentences(text)]
    kept: list[dict] = []
    seen = set()
    for _ in range(1 + SPARK_MAX_REGENS):
        if len(kept) >= parsed["count"]:
            break
        try:
            raw = _spark_chat(messages)
            drafts = json.loads(raw)
        except (SparkError, ValueError):
            continue
        if not isinstance(drafts, list):
            continue
        for draft in drafts:
            if len(kept) >= parsed["count"]:
                break
            item = _resolve_spark_item(draft, shown, parsed["skill"])
            if item is None:
                continue
            key = (item["type"], item["prompt"])
            if key in seen:
                continue
            if (verify("practice_item", item)["pass"]
                    and _item_grounded(item, sentences)):
                seen.add(key)
                kept.append(item)
    return kept


def _template_items(pool: list, dpool: list[str], skill: str, count: int,
                    start: int = 0, seen: set[str] | None = None) -> list[dict]:
    """Deterministic excerpt assembly; start offsets ids and type alternation."""
    items: list[dict] = []
    seen_prompts = set(seen or ())
    use_count = [0] * len(pool)
    idx = guard = 0
    while len(items) < count and guard < count * 4:
        guard += 1
        j = idx % len(pool)
        idx += 1
        sentences = _excerpt_sentences(pool[j][0])
        if len(sentences) < 2:
            continue
        off = (use_count[j] * 2) % len(sentences)
        use_count[j] += 1
        window = (sentences[off:] + sentences[:off])[:4]
        meta = pool[j][1]
        num = start + len(items)
        item = None
        if num % 2 == 0:
            item = _teacher_order_item(num, window, meta, skill)
        else:
            distractors = []
            for s in dpool:
                if s != window[0] and s not in distractors:
                    distractors.append(s)
                if len(distractors) == 3:
                    break
            if len(distractors) >= 2:
                item = _teacher_mcq_item(num, window[0], distractors, meta, skill)
            else:
                item = _teacher_order_item(num, window, meta, skill)
        if item is None:
            continue
        # Mcq prompts repeat by design; tell them apart by the correct sentence.
        key = item["prompt"] if item["type"] == "order" else item["prompt"] + "|" + window[0]
        if key not in seen_prompts:
            seen_prompts.add(key)
            items.append(item)
    return items


def _spark_item_key(item: dict) -> str:
    """Dedupe key matching the template rule (correct sentence for mcq)."""
    if item["type"] == "order":
        return item["prompt"]
    for option in item["options"]:
        if option.startswith(item["answer"] + ")"):
            return item["prompt"] + "|" + option
    return item["prompt"] + "|" + item["answer"]


def _generate_practice_set(request_text: str, note: str = "") -> tuple[list[dict], str]:
    """(items, engine): Spark drafts when keyed, templates fill any gap.

    Engine is spark | mixed | template. Either way every served item is
    excerpt-only: Spark drafts pass the grounding gate, templates assemble
    excerpts directly.
    """
    parsed = parse_teacher_request(request_text)
    skill, count = parsed["skill"], parsed["count"]
    extra = f" {(note or '').strip()}" if (note or "").strip() else ""
    docs, metas = _query_guides(f"{skill} writing{extra}", n_results=count + 3)
    pool = [(d, m or {}) for d, m in zip(docs, metas) if (d or "").strip()]
    if not pool:
        return [], "template"
    if parsed["discipline"]:
        pool = sorted(pool, key=lambda dm: _book_score(
            (dm[1] or {}).get("source"), parsed["discipline"]), reverse=True)
    others = [s for s in SKILLS if s != skill][:2]
    dpool: list[str] = []
    for other in others:
        other_docs, _ = _query_guides(f"{other} writing{extra}", n_results=2)
        for doc in other_docs:
            dpool.extend(_excerpt_sentences(doc))
    try:
        kept = _spark_draft_items(_shown_excerpts(pool), request_text,
                                  parsed, note)
    except SparkError:
        kept = []
    need = count - len(kept)
    backfill = _template_items(pool, dpool, skill, need, start=len(kept),
                               seen={_spark_item_key(it) for it in kept}) if need > 0 else []
    final = kept + backfill
    for i, item in enumerate(final):
        item["id"] = f"t{i + 1}"
    engine = "spark" if kept and not backfill else ("mixed" if kept else "template")
    return final, engine


def generate_practice_set(request_text: str, note: str = "") -> list[dict]:
    """Build items ONLY from ChromaDB excerpts; [] when nothing usable exists.

    Spark drafts the items when an API key is set; every draft must quote an
    excerpt sentence word-for-word or it is dropped. Template-built items fill
    any gap, so the set stays excerpt-only with or without Spark. The optional
    note steers retrieval (and Spark). Option order rotates deterministically
    by position.
    """
    return _generate_practice_set(request_text, note)[0]


# --- Endpoints --------------------------------------------------------------------------
@app.post("/learners")
def post_learner(data: LearnerIn):
    """Signup step: register a learner with their chosen discipline."""
    try:
        learner_id = store.create_learner(
            data.name, data.year, data.subject, data.language, data.discipline
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"ok": True, "learner_id": learner_id,
            "discipline": data.discipline, "message": "Learner signed up."}


@app.post("/drafts")
def post_draft(data: DraftIn):
    """Write step: save the paragraph and remember it for the twin."""
    if store.get_learner(data.learner_id) is None:
        raise HTTPException(status_code=404, detail="Unknown learner_id")
    if data.source not in ("typed", "scan"):
        raise HTTPException(status_code=400, detail="Unknown draft source")
    draft_id = store.save_draft(data.learner_id, data.content, feedback="",
                                source=data.source)
    store.save_writing_sample(data.learner_id, data.content)
    store.log_event(data.learner_id, "Write", "twin", "post_draft",
                    f"draft_id={draft_id} words={len(data.content.split())}")
    return {"ok": True, "draft_id": draft_id, "learner_id": data.learner_id,
            "message": "Draft saved."}


# --- Scan my paper (Spark vision transcription) --------------------------------
# Image input shape per dev.meta.ai/docs/image-understanding (Chat
# Completions): the user message carries content blocks, the photo as an
# image_url object whose url is a base64 data URL. The photo is forwarded,
# never stored: only the confirmed text reaches the drafts table.
SCAN_INSTRUCTION = (
    "Transcribe this handwritten paragraph exactly as written, keeping the "
    "learner's own spelling and grammar. Do not correct anything. Mark any "
    "word you cannot read as [unclear].")

SPARK_SCAN_SYSTEM = (
    "You transcribe a handwritten paragraph photo for a first-year Indian "
    "undergraduate. Reply with a JSON object only, no other text, with keys: "
    "text (the paragraph transcribed exactly as written, keeping the "
    "learner's own spelling and grammar, with [unclear] for words you "
    "cannot read) and unclear (an array with one short context snippet — "
    "the 2-3 words before each [unclear] mark, or empty when the mark "
    "starts the text — one entry per mark, in order). Do not correct "
    "anything.")

SCAN_FALLBACK = "Please type your paragraph."
SCAN_MAX_CHARS = 2000000  # ~1.5 MB of base64; browser compresses under 1 MB


def _scan_messages(image_url: str) -> list[dict]:
    """Prompt: the fixed instruction plus the photo as an image_url block."""
    return [{"role": "system", "content": SPARK_SCAN_SYSTEM},
            {"role": "user", "content": [
                {"type": "text", "text": SCAN_INSTRUCTION},
                {"type": "image_url",
                 "image_url": {"url": image_url}}]}]


def _validate_scan(data) -> dict | None:
    """Non-empty text plus the unclear list (missing means none found).

    The unclear list is informational: highlighting works off the [unclear]
    marks in the text, so a confident transcription without the key is
    still a pass.
    """
    if not isinstance(data, dict):
        return None
    text = (data.get("text") or "").strip()
    unclear = data.get("unclear") or []
    if not text or not isinstance(unclear, list):
        return None
    if any(not isinstance(u, str) for u in unclear):
        return None
    return {"text": text, "unclear": unclear}


def _scan_with_spark(image_url: str) -> tuple[dict | None, str | None]:
    """Transcription passing validation, or (None, last error) after retries."""
    messages = _scan_messages(image_url)
    last_error = "no response"
    for _ in range(1 + SPARK_MAX_REGENS):
        try:
            data = json.loads(_spark_chat(messages,
                                           timeout=SPARK_TIMEOUT_SLOW))
        except (SparkError, ValueError) as exc:
            last_error = str(exc)[:200]
            continue
        fields = _validate_scan(data)
        if fields is not None:
            return fields, None
        last_error = "invalid transcription shape"
    return None, last_error


def _scan_fallback_message(error: str) -> str:
    """Friendly real reason for a failed scan (raw error stays in the log)."""
    if "timed out" in (error or ""):
        return ("The photo took too long to read - try a smaller, "
                "clearer photo")
    if error == "invalid transcription shape":
        return "The writing was hard to read - try a clearer photo."
    return SCAN_FALLBACK


@app.post("/drafts/scan")
def post_draft_scan(data: DraftScanIn):
    """Scan step: transcribe a paper photo; the photo is never stored."""
    if store.get_learner(data.learner_id) is None:
        raise HTTPException(status_code=404, detail="Unknown learner_id")
    raw = (data.image or "").strip()
    if not raw or len(raw) > SCAN_MAX_CHARS:
        return {"ok": False, "message": SCAN_FALLBACK}
    url = raw if raw.startswith("data:image/") else \
        f"data:image/jpeg;base64,{raw}"
    found, error = _scan_with_spark(url)
    if found is None:
        store.log_event(data.learner_id, "Write", "twin", "scan",
                        f"scan failed: {error}")
        return {"ok": False, "message": _scan_fallback_message(error)}
    store.log_event(
        data.learner_id, "Write", "twin", "scan",
        f"Read by Muse Spark (vision): {len(found['unclear'])} unclear words")
    return {"ok": True, "text": found["text"], "unclear": found["unclear"]}


@app.post("/diagnose")
def post_diagnose(data: DiagnoseIn):
    """Diagnose step: score the draft on 7 skills, return scores + weakest."""
    learner = store.get_learner(data.learner_id)
    if learner is None:
        raise HTTPException(status_code=404, detail="Unknown learner_id")
    text = data.content
    if data.draft_id is not None:  # prefer the stored draft when given
        drafts = [d for d in store.get_drafts(data.learner_id) if d["id"] == data.draft_id]
        if not drafts:
            raise HTTPException(status_code=404, detail="Unknown draft_id")
        text = drafts[0]["content"]
    if not (text or "").strip():
        raise HTTPException(status_code=400, detail="Provide draft_id or content")
    # Snapshot before saving: in the normal draft -> diagnose flow this is
    # the previous draft's diagnosis, used for the twin's comparison.
    prev_scores = latest_scores(data.learner_id)
    discipline = learner.get("discipline") or "Sciences"
    heuristic = diagnose_text(text)
    demo_fixed = None
    if _demo_mode() and _demo_text_match(text, DEMO_WEAK_PARAGRAPH):
        demo_fixed = DEMO_DIAGNOSIS
    demo_improved = _demo_mode() and _demo_text_match(
        text, DEMO_IMPROVED_PARAGRAPH)
    sparked = _diagnose_with_spark(data.learner_id, text, discipline) \
        if demo_fixed is None and not demo_improved else None
    if demo_fixed is not None:
        scores = {s: DIAGNOSE_LEVEL_SCORES[demo_fixed[s]["level"]]
                  for s in SKILLS}
        weakest = min(SKILLS, key=lambda s: demo_fixed[s]["level"])
        wlevel = demo_fixed[weakest]["level"]
        store.log_event(
            data.learner_id, "Diagnose", "twin", "diagnose-demo",
            f"Demo diagnosis (fixed): weakest={weakest} L{wlevel} "
            f"({demo_fixed[weakest]['reason']} "
            f"\"{demo_fixed[weakest]['evidence']}\")")
    elif sparked is not None:
        scores = {s: DIAGNOSE_LEVEL_SCORES[sparked[s]["level"]] for s in SKILLS}
        weakest = min(SKILLS, key=lambda s: sparked[s]["level"])
        wlevel = sparked[weakest]["level"]
        store.log_event(
            data.learner_id, "Diagnose", "twin", "diagnose-spark",
            f"Diagnosed by Muse Spark: weakest={weakest} L{wlevel} "
            f"({sparked[weakest]['reason']} "
            f"\"{sparked[weakest]['evidence']}\")")
        gaps = [f"{s} L{sparked[s]['level']} vs "
                f"heuristic L{level_for_score(heuristic[s])}"
                for s in SKILLS
                if abs(sparked[s]["level"]
                       - level_for_score(heuristic[s])) > 2]
        if gaps:
            store.log_event(data.learner_id, "Diagnose", "twin",
                            "diagnose-sanity",
                            "Spark-heuristic gap over 2 levels: "
                            + "; ".join(gaps))
    else:
        scores = heuristic
        if demo_improved:
            scores = dict(scores)
            scores["Paragraphing"] = DIAGNOSE_LEVEL_SCORES[2]
        else:
            scores = _cap_fallback_scores(text, scores)
        weakest = min(SKILLS, key=lambda s: scores[s])
        if demo_improved:
            store.log_event(
                data.learner_id, "Diagnose", "twin", "diagnose-demo",
                "Demo diagnosis (improved paragraph; Paragraphing pinned L2)")
        else:
            store.log_event(data.learner_id, "Diagnose", "diagnose",
                            "heuristic-scorer",
                            f"weakest={weakest} scores={scores}")
    if demo_fixed is not None:
        detail = {s: {"reason": demo_fixed[s]["reason"],
                      "evidence": demo_fixed[s]["evidence"]} for s in SKILLS}
        feedback = dict(DEMO_FEEDBACK_WEAK)
    else:
        if sparked is not None:
            detail = {s: {"reason": sparked[s]["reason"],
                          "evidence": sparked[s]["evidence"]} for s in SKILLS}
        else:
            detail = _heuristic_details(text, scores)
        if demo_improved:
            feedback = dict(DEMO_FEEDBACK_IMPROVED)
        else:
            weakest_two = sorted(
                SKILLS, key=lambda s: (scores[s], SKILLS.index(s)))[:2]
            feedback = None
            if sparked is not None:
                feedback = _feedback_with_spark(
                    data.learner_id, text, weakest_two)
            if feedback is not None:
                store.log_event(
                    data.learner_id, "Diagnose", "twin",
                    "diagnose-feedback-spark",
                    "Feedback on your paragraph by Muse Spark")
            else:
                # Spark already failed for this diagnosis, or no key: use
                # the safe template now instead of another round of calls.
                feedback = _template_feedback(detail, weakest_two, text)
    store.save_skill_scores(data.learner_id, scores, detail)
    store.log_activity(data.learner_id, weakest, "write")
    level = level_for_score(scores[weakest])
    first = ((learner.get("name") or "friend").split() or ["friend"])[0]
    band = ("strong" if level >= 4 else "good" if level == 3
            else "fair" if level == 2 else "weak")
    ordered = sorted(SKILLS, key=lambda s: (scores[s], SKILLS.index(s)))
    motivation = _motivation_card(
        first, band, (feedback or {}).get("strength"), text,
        [NEXT_WIN_ACTIONS[s] for s in ordered[:2]],
        DISCIPLINE_TOPICS.get(discipline, "your topic"),
        f"Next goal: {NEXT_WIN_ACTIONS[weakest]}.")
    if demo_fixed is not None:
        motivation.update(DEMO_MOTIVATION_WEAK)
    elif demo_improved:
        motivation.update(DEMO_MOTIVATION_IMPROVED)
    if isinstance(feedback, dict):
        feedback["motivation"] = motivation
    if demo_improved:
        comparison = DEMO_COMPARISON
    elif prev_scores:
        comparison = compare_note(
            weakest, level_for_score(prev_scores.get(weakest, 0)), level)
    else:
        comparison = "This is your starting point."
    level_changes = {
        skill: {"previous": (level_for_score(prev_scores[skill])
                             if skill in prev_scores else None),
                "current": level_for_score(scores[skill])}
        for skill in SKILLS
    }
    note = twin_note(weakest)
    if data.draft_id is not None:
        store.update_draft_feedback(data.draft_id, f"{note} {comparison}")
    learn = learn_card(weakest, level, discipline)
    if isinstance(learn, dict) and isinstance(detail, dict) \
            and (detail.get(weakest) or {}).get("evidence"):
        quote = (detail[weakest]["evidence"] or "").strip()
        handle = {"Using sources": "has no source",
                  "Paragraphing": "has no clear main point",
                  "Argument": "gives no proof",
                  "Grammar": "has small errors",
                  "Vocabulary": "repeats easy words",
                  "Sentence structure": "runs in short lines",
                  "Academic tone": "sounds too casual"}.get(
                      weakest, "needs work")
        learn["connect"] = (f"Your sentence '{quote}' {handle}. "
                            "Here is why this skill matters.")
    notice = None
    if demo_fixed is None and sparked is None and not demo_improved:
        notice = FALLBACK_NOTICE
    return {"scores": scores, "weakest": weakest,
            "level": level,
            "notice": notice,
            "levels": {s: level_for_score(scores[s]) for s in SKILLS},
            "skills_details": [{"skill": s,
                                "level": level_for_score(scores[s]),
                                "reason": (detail or {}).get(s, {}).get("reason"),
                                "evidence": (detail or {}).get(s, {}).get("evidence")}
                               for s in SKILLS],
            "feedback": feedback,
            "twin_note": note,
            "comparison": comparison,
            "level_changes": level_changes,
            "study_material": study_material(weakest),
            "learn": learn}


SPARK_POLISH_SYSTEM = (
    "You rewrite a learner's paragraph in correct English for a first-year "
    "Indian undergraduate. Keep every idea and fact they wrote; fix the "
    "language only and never add new facts. Reply with a JSON object only, "
    "no other text, with one key: polished (their whole paragraph, "
    "rewritten correctly).")


def _polish_with_spark(text: str) -> str | None:
    """Whole-paragraph rewrite, or None after retries (never invent facts)."""
    if _model_api_key() is None:
        return None
    messages = [{"role": "system", "content": SPARK_POLISH_SYSTEM},
                {"role": "user", "content": f"Paragraph: {text}"}]
    words = len(text.split())
    for _ in range(1 + SPARK_MAX_REGENS):
        try:
            data = json.loads(_spark_chat(messages, temperature=0,
                                           timeout=SPARK_TIMEOUT_SLOW))
        except (SparkError, ValueError):
            continue
        polished = (data.get("polished") or "").strip() \
            if isinstance(data, dict) else ""
        if not polished:
            continue
        ratio = len(polished.split()) / max(1, words)
        if 0.5 <= ratio <= 2.0:
            return polished
    return None


@app.post("/polish")
def post_polish(data: PolishIn):
    """Compare step: a polished rewrite, unlocked after their own rewrite."""
    if store.get_learner(data.learner_id) is None:
        raise HTTPException(status_code=404, detail="Unknown learner_id")
    original = (data.content or "").strip()
    if not original:
        drafts = [d for d in store.get_drafts(data.learner_id)
                  if d["id"] == data.draft_id]
        if not drafts:
            raise HTTPException(status_code=404, detail="Unknown draft_id")
        if len(store.get_drafts(data.learner_id)) < 2:
            return {"ok": False,
                    "message": "Rewrite your paragraph first, then compare."}
        original = drafts[0]["content"]
    polished = _polish_with_spark(original)
    if polished is None:
        store.log_event(data.learner_id, "Write", "twin", "polish",
                        "polished version unavailable")
        return {"ok": False,
                "message": "Polished version unavailable right now - "
                           "try again later."}
    store.log_event(data.learner_id, "Write", "twin", "polish",
                    f"draft_id={data.draft_id} words={len(polished.split())}")
    return {"ok": True, "original": original, "polished": polished}


@app.get("/rubric")
def get_rubric():
    """The fixed 7-skill rubric (same data the Diagnoser sends to Spark)."""
    return {"skills": [{"skill": skill, "levels": list(DIAGNOSE_RUBRIC[skill])}
                       for skill in SKILLS]}


@app.get("/config")
def get_config():
    """Client flags: demo mode badge."""
    return {"demo_mode": _demo_mode()}


@app.get("/curriculum")
def get_curriculum(learner_id: int):
    """Learn step: all disciplines with module unlock states for a learner."""
    learner = store.get_learner(learner_id)
    if learner is None:
        raise HTTPException(status_code=404, detail="Unknown learner_id")
    scores = latest_scores(learner_id)
    return {"learner_id": learner_id,
            "discipline": learner.get("discipline") or "Sciences",
            "disciplines": [
                {"name": name, "genre": genre,
                 "modules": module_states(name, scores)}
                for name, genre in DISCIPLINE_GENRES.items()
            ]}


def _module_state_or_raise(learner_id: int, discipline: str,
                           module_id: str) -> tuple[dict, dict]:
    """(module state, module content) for a learner, or raise 404/400."""
    if store.get_learner(learner_id) is None:
        raise HTTPException(status_code=404, detail="Unknown learner_id")
    if discipline not in DISCIPLINE_GENRES:
        raise HTTPException(status_code=400, detail="Unknown discipline")
    modules = {m["id"]: m for m in discipline_modules(discipline)}
    if module_id not in modules:
        raise HTTPException(status_code=404, detail="Unknown module")
    states = {s["id"]: s for s in module_states(discipline, latest_scores(learner_id))}
    state = states[module_id]
    return state, modules[module_id]  # no locks: every module is open


@app.get("/curriculum/modules")
def get_curriculum_module(learner_id: int, discipline: str, module: str):
    """Learn step: the six-screen lesson for a module."""
    _module_state_or_raise(learner_id, discipline, module)
    store.log_event(learner_id, "Learn", "twin", "get_module",
                    f"discipline={discipline} module={module}")
    return build_lesson(discipline, module)


def _scaffold_view(attempt_id: str, attempt: dict, extra: dict | None = None) -> dict:
    """Full attempt view: task plus whatever the current step serves."""
    view = {"attempt_id": attempt_id, "step": attempt["step"],
            "task": scaffold_task(attempt["discipline"], attempt["module"]),
            "module": attempt["module"], "discipline": attempt["discipline"]}
    if extra:
        view.update(extra)
    return view


def _scaffold_attempt_or_raise(learner_id: int, attempt_id: str) -> tuple[str, dict]:
    attempt = SCAFFOLD_ATTEMPTS.get(attempt_id)
    if attempt is None or attempt["learner_id"] != learner_id:
        raise HTTPException(status_code=404, detail="Unknown or foreign attempt_id")
    return attempt_id, attempt


_WEAK_EXAMPLE_SIGNS = ("very ", "many things", "interesting", "nice",
                         "i will tell you", "there are", "a lot of")


def _serve_excerpt(learner_id: int, attempt_id: str, attempt: dict,
                   tool: str) -> dict:
    """Serve step (d): one clean book sentence, labelled Good/Weak example."""
    genre = DISCIPLINE_GENRES[attempt["discipline"]]
    modules = {m["id"]: m for m in discipline_modules(attempt["discipline"])}
    found = verified_excerpt(
        module_example_query(modules[attempt["module"]], genre))
    if found.get("source"):
        sents = clean_sentences(found["text"])
        one = sents[0] if sents else found["text"].strip()
        weak = any(sign in one.lower() for sign in _WEAK_EXAMPLE_SIGNS)
        excerpt = {"text": one, "source": found["source"],
                   "chapter": found.get("chapter"),
                   "license": found.get("license"),
                   "book": resolve_book(found["source"],
                                        found.get("license")),
                   "label": "Weak example" if weak else "Good example"}
        attempt["excerpt_text"] = one
    else:
        excerpt = {"text": NO_VERIFIED_EXAMPLE, "source": None,
                   "chapter": None, "license": None, "book": None,
                   "label": None}
        attempt["excerpt_text"] = ""
    attempt["step"] = "excerpt"
    store.log_event(learner_id, "Scaffold", "twin", tool,
                    f"attempt_id={attempt_id} module={attempt['module']}")
    return _scaffold_view(attempt_id, attempt, {
        "excerpt": excerpt, "try": attempt.get("last_try")})


def _select_module_rule(module: dict, discipline: str) -> dict:
    """The rule-query excerpt best matching the module's rule claims.

    Candidates score by claim-keyword hits first, then discipline book fit,
    then rank. With no keyword match anywhere the honest empty message wins
    over an irrelevant excerpt.
    """
    docs, metas = _query_guides(module_rule_query(module), n_results=8)
    claims = LESSON_IDEA_CLAIMS.get(module["id"], [])
    best = None
    for rank, (doc, meta) in enumerate(zip(docs, metas)):
        sents = clean_sentences(doc)
        if not sents:
            continue
        text = " ".join(sents[:2])
        low = text.lower()
        hits = sum(1 for claim in claims
                   if any(k.lower() in low for k in claim["keywords"]))
        if hits == 0:
            continue
        meta = meta or {}
        key = (hits, _book_score(meta.get("source"), discipline), -rank)
        if best is None or key > best[0]:
            best = (key, text, meta)
    if best is None:
        return {"text": NO_VERIFIED_EXAMPLE, "source": None, "chapter": None,
                "license": None, "book": None}
    _, text, meta = best
    return {"text": text, "source": meta.get("source"),
            "chapter": meta.get("chapter"), "license": meta.get("license"),
            "book": resolve_book(meta.get("source"), meta.get("license"))
            if meta.get("source") else None}


def _serve_scaffold_question(learner_id: int, attempt_id: str,
                             attempt: dict) -> dict:
    """Serve ladder step (b): one guiding question."""
    genre = DISCIPLINE_GENRES[attempt["discipline"]]
    question = scaffold_question(
        attempt["module"], attempt["q_index"], genre)
    if attempt.get("last_try"):
        question = f"About your line '{attempt['last_try']}': {question}"
    attempt["q_index"] += 1
    attempt["step"] = "question"
    store.log_event(learner_id, "Scaffold", "twin", "question",
                    f"attempt_id={attempt_id} module={attempt['module']}")
    return _scaffold_view(attempt_id, attempt, {"question": question})


def _serve_scaffold_hint(learner_id: int, attempt_id: str, attempt: dict,
                         attempt_text: str) -> dict:
    """Serve ladder step (c): a hint aimed at the try's weak spot."""
    topic = DISCIPLINE_TOPICS[attempt["discipline"]]
    hint = targeted_hint(attempt["module"], attempt_text, topic)
    if attempt.get("last_try"):
        hint = f"About your line '{attempt['last_try']}': {hint}"
    attempt["step"] = "hint"
    store.log_event(learner_id, "Scaffold", "twin", "hint",
                    f"attempt_id={attempt_id} module={attempt['module']}")
    return _scaffold_view(attempt_id, attempt, {"hint": hint})


def _serve_assessed(learner_id: int, attempt_id: str, attempt: dict,
                    judged: dict, text: str) -> dict:
    """Serve the assessed next step: 2 = praise + done, 1 = try-specific
    question, 0 = retry, repeated weak = excerpt. Then the ladder runs."""
    attempt["last_try"] = text
    if "first_try" not in attempt:
        attempt["first_try"] = text
        attempt["first_score"] = judged["score"]
    if judged["status"] != "ok" or judged["score"] == 0:
        judged["next_step"] = "retry"
        return _scaffold_view(attempt_id, attempt, {"assessment": judged})
    if judged["score"] == 2:
        judged["next_step"] = "done"
        attempt["step"] = "done"
        store.log_activity(learner_id, attempt["skill"], "learn")
        return _scaffold_view(attempt_id, attempt, {
            "assessment": judged,
            "message": f"Well done. Your line '{judged['quote']}' does the "
                       "job. Marked done."})
    if attempt.get("weak", 0) >= 2 and attempt["level"] < 4:
        judged["next_step"] = "excerpt"
        view = _serve_excerpt(learner_id, attempt_id, attempt, "excerpt")
        view["assessment"] = judged
        return view
    judged["next_step"] = "question"
    stem = ASSESS_TRY_QUESTIONS[attempt["module"]]
    question = f"About your line '{judged['quote']}': {stem}"
    attempt["q_index"] += 1
    attempt["step"] = "question"
    store.log_event(learner_id, "Scaffold", "twin", "question",
                    f"attempt_id={attempt_id} module={attempt['module']}")
    return _scaffold_view(attempt_id, attempt, {"assessment": judged,
                                                "question": question})


def _serve_steps(learner_id: int, attempt_id: str, attempt: dict,
                 tool: str) -> dict:
    """Serve the worked answer: book rule, ordered steps, verified model.

    The steps teach the retrieved rule; the model is served only when the
    worked_model Verifier check passes, else it is omitted and logged.
    """
    modules = {m["id"]: m for m in discipline_modules(attempt["discipline"])}
    model = worked_model(attempt["module"], attempt["discipline"])
    verdict = verify("worked_model", {
        "module": attempt["module"], "model": model,
        "task_topic": DISCIPLINE_TOPICS[attempt["discipline"]]})
    attempt["step"] = "steps"
    store.log_event(learner_id, "Scaffold", "twin", tool,
                    f"attempt_id={attempt_id} module={attempt['module']}")
    payload = {
        "steps": worked_steps(attempt["module"], attempt["discipline"]),
        "rule": _select_module_rule(modules[attempt["module"]],
                                    attempt["discipline"]),
    }
    if verdict["pass"]:
        payload["model"] = model
    else:
        store.log_event(learner_id, "Scaffold", "twin", "verify-steps",
                        f"attempt_id={attempt_id} failed={verdict['failed']}")
    return _scaffold_view(attempt_id, attempt, payload)


def skill_mode(learner_id: int, skill: str) -> str:
    """Guided until 6 activities in the skill; challenge from Level 3."""
    level = level_for_score(latest_scores(learner_id).get(skill, 0.0))
    if level >= 3:
        return "challenge"
    if store.count_activities(learner_id, skill) >= GUIDED_ACTIVITIES:
        return "challenge"
    return "guided"


@app.post("/scaffold/start")
def post_scaffold_start(data: ScaffoldStartIn):
    """Scaffold step (a): guided serves idea + worked example, else the task."""
    state, content = _module_state_or_raise(
        data.learner_id, data.discipline, data.module)
    mode = skill_mode(data.learner_id, content["skill"])
    attempt_id = uuid.uuid4().hex[:8]
    SCAFFOLD_ATTEMPTS[attempt_id] = {
        "learner_id": data.learner_id, "discipline": data.discipline,
        "module": data.module, "skill": content["skill"],
        "level": state["learner_level"], "step": "try", "q_index": 0,
        "shows": 0, "weak": 0, "mode": mode,
    }
    store.log_event(data.learner_id, "Scaffold", "twin", "start",
                    f"attempt_id={attempt_id} module={data.module} mode={mode}")
    extra = {"level": state["learner_level"], "mode": mode}
    if mode == "guided":
        extra["idea"] = build_lesson(
            data.discipline, data.module)["idea"]["text"]
        model = worked_model(data.module, data.discipline)
        verdict = verify("worked_model", {
            "module": data.module, "model": model,
            "task_topic": DISCIPLINE_TOPICS[data.discipline]})
        if verdict["pass"]:
            extra["worked_example"] = {
                "text": model, "self_check": SELF_EXPLANATION}
        else:
            store.log_event(data.learner_id, "Scaffold", "twin",
                            "verify-guided",
                            f"attempt_id={attempt_id} failed={verdict['failed']}")
    return _scaffold_view(attempt_id, SCAFFOLD_ATTEMPTS[attempt_id], extra)


@app.post("/scaffold/help")
def post_scaffold_help(data: ScaffoldHelpIn):
    """Move one rung up the ladder: question -> hint -> excerpt -> rewrite.

    A real try is assessed first and the next step follows the assessment;
    without a try (or Assessor) the fixed ladder runs: Levels 1-2 reach
    hints sooner; Levels 4-5 get only questions.
    """
    attempt_id, attempt = _scaffold_attempt_or_raise(
        data.learner_id, data.attempt_id)
    if attempt["step"] in ("rewrite", "done"):
        return _scaffold_view(attempt_id, attempt)
    text = (data.attempt_text or "").strip()
    if text and attempt["step"] in ("try", "question", "hint"):
        judged = _judge_attempt(data.learner_id, attempt, text)
        if judged is not None:
            return _serve_assessed(
                data.learner_id, attempt_id, attempt, judged, text)
    level = attempt["level"]
    if attempt["step"] == "excerpt":
        attempt["step"] = "rewrite"
        prompt = "Now rewrite using the pattern."
        if attempt.get("last_try"):
            prompt = (f"Now rewrite your line '{attempt['last_try']}' "
                      "using the pattern.")
        return _scaffold_view(attempt_id, attempt, {"prompt": prompt})
    if attempt["step"] == "steps":
        attempt["step"] = "rewrite"
        prompt = "Now write your version using the steps above."
        if attempt.get("last_try"):
            prompt = (f"Now rewrite your line '{attempt['last_try']}' "
                      "using the steps above.")
        return _scaffold_view(attempt_id, attempt, {"prompt": prompt})
    if attempt["step"] == "hint":
        return _serve_excerpt(data.learner_id, attempt_id, attempt, "excerpt")
    allowed = QUESTIONS_BEFORE_HINT.get(level)
    if level >= 4 or attempt["q_index"] < (allowed or 0):
        return _serve_scaffold_question(
            data.learner_id, attempt_id, attempt)
    return _serve_scaffold_hint(
        data.learner_id, attempt_id, attempt, data.attempt_text)


@app.post("/scaffold/show")
def post_scaffold_show(data: ScaffoldShowIn):
    """'Show me now': jump to the book excerpt, then one self-explanation ask.

    A repeated press means impatience: serve the worked steps instead.
    """
    attempt_id, attempt = _scaffold_attempt_or_raise(
        data.learner_id, data.attempt_id)
    if attempt["step"] in ("rewrite", "done"):
        return _scaffold_view(attempt_id, attempt)
    attempt["shows"] = attempt.get("shows", 0) + 1
    if attempt["shows"] >= 2 or attempt["step"] == "excerpt":
        return _serve_steps(data.learner_id, attempt_id, attempt, "show-me")
    view = _serve_excerpt(data.learner_id, attempt_id, attempt, "show-me")
    if view["excerpt"]["label"] == "Weak example":
        view["self_explanation"] = "What is missing here?"
    elif view["excerpt"]["label"]:
        view["self_explanation"] = "Why does this work?"
    return view


@app.post("/scaffold/steps")
def post_scaffold_steps(data: ScaffoldStepsIn):
    """'Just show me the steps': the worked answer, open at any level."""
    attempt_id, attempt = _scaffold_attempt_or_raise(
        data.learner_id, data.attempt_id)
    if attempt["step"] in ("rewrite", "done"):
        return _scaffold_view(attempt_id, attempt)
    return _serve_steps(data.learner_id, attempt_id, attempt, "steps")


@app.post("/scaffold/rewrite")
def post_scaffold_rewrite(data: ScaffoldRewriteIn):
    """Scaffold step (e): accept the learner's rewrite of the task."""
    if not (data.text or "").strip():
        raise HTTPException(status_code=400, detail="Rewrite text is empty")
    attempt_id, attempt = _scaffold_attempt_or_raise(
        data.learner_id, data.attempt_id)
    text = data.text.strip()
    judged = _judge_attempt(data.learner_id, attempt, text)
    attempt["step"] = "done"
    store.log_activity(data.learner_id, attempt["skill"], "learn")
    words = len(text.split())
    store.log_event(data.learner_id, "Scaffold", "twin", "rewrite",
                    f"attempt_id={attempt_id} module={attempt['module']} words={words}")
    extra = {"message": "Saved. Read it once more against the pattern."}
    if judged is not None:
        judged["next_step"] = "done"
        extra["assessment"] = judged
        first, first_score = attempt.get("first_try"), attempt.get("first_score")
        if first is not None and first_score is not None:
            if judged["score"] > first_score:
                line = "You moved up. Well done."
            elif judged["score"] == first_score:
                line = "Same score. Read the hint once more and try again."
            else:
                line = "This one lost the point. Go back to your first line."
            extra["comparison"] = (
                f"First try (score {first_score} of 2): '{first}' "
                f"Rewrite (score {judged['score']} of 2): '{text}'. {line}")
        else:
            extra["comparison"] = (
                f"Rewrite (score {judged['score']} of 2): '{text}'.")
    return _scaffold_view(attempt_id, attempt, extra)


# --- Practice sets: 4 item types ------------------------------------------------
# Each set for a moduled skill mixes recognise (best example from excerpts),
# repair (fix a weak line), produce (write on a topic) and apply (write in
# the discipline genre). Closed answers are letters; repair/produce/apply are
# free text judged by the Practice Assessor. Teachers' published sets win;
# unmoduled skills and thin libraries fall back to the bank. Every third set
# is a mixed review of earlier modules; two sets at 80%+ move the skill up.
PRACTICE_SET_SIZE = 6
PRACTICE_COMPOSITION = ("recognise", "recognise", "repair", "produce",
                        "produce", "apply")
MASTERY_ACCURACY = 80
MASTERY_SETS = 2
REVIEW_EVERY = 3

PRACTICE_LABELS = {
    "topic-sentences": "topic sentence",
    "thesis-statements": "thesis statement",
    "developing-paragraphs": "supporting line",
    "coherence-flow": "continuing line",
    "using-sources": "sourced line",
    "mechanics": "corrected line",
    "referencing-styles": "cited line",
    "academic-vocabulary": "formal line",
    "genre": "{genre} opening",
}

# Deliberately weak lines to repair ({topic} {genre}). These are the task,
# never presented as examples, so they are authored, not retrieved.
WEAK_REPAIRS = {
    "topic-sentences": ["There are many things about {topic}.",
                        "{topic} is very interesting and nice.",
                        "I will tell you about {topic} now."],
    "thesis-statements": ["{topic} is a topic people talk about.",
                          "I like {topic} a lot these days.",
                          "This essay is about {topic} and other things."],
    "developing-paragraphs": ["{topic} is good and nice.",
                              "There is a lot to say here.",
                              "It matters in many ways."],
    "coherence-flow": ["{topic} is big. It rains a lot.",
                       "I saw {topic}. Then I ate lunch.",
                       "{topic} started. Nobody knows why."],
    "using-sources": ["People say {topic} is good.",
                      "Everyone knows about {topic}.",
                      "I heard that {topic} matters."],
    "mechanics": ["{topic} is very interesting",
                  "i like {topic} a lot",
                  "The {topic} are nice and good"],
    "referencing-styles": ["{topic} is good for all, says someone.",
                           "Experts say {topic} matters a lot.",
                           "I read that {topic} is useful somewhere."],
    "academic-vocabulary": ["{topic} is very nice and good.",
                            "{topic} is a big thing for us.",
                            "I like {topic} a lot, it is nice."],
    "genre": ["This {genre} is about {topic} and stuff.",
              "Hello, this is my {genre}.",
              "{topic} is the best, trust me."],
}


def _practice_rubric_line(module_id: str, discipline: str) -> str:
    """The module rubric as one guidance line for write items."""
    rubric = [c.format(genre=DISCIPLINE_GENRES[discipline])
              for c in SCAFFOLD_RUBRICS[module_id]]
    return "Rubric: " + " ".join(rubric)


def _recognise_item(module: dict, skill: str, discipline: str, level: int,
                    num: int, pool: list, dpool: list[str]) -> dict | None:
    """Best-example choice: a claim sentence among distractors, or None."""
    claims = LESSON_IDEA_CLAIMS.get(module["id"], [])
    best = None
    for doc, meta in pool:
        for sent in clean_sentences(doc):
            if any(k.lower() in sent.lower() for claim in claims
                   for k in claim["keywords"]):
                best = (sent, meta or {})
                break
        if best is not None:
            break
    if best is None:
        return None
    sentence, meta = best
    same = [s for d, _ in pool for s in clean_sentences(d) if s != sentence]
    others = [s for s in dpool if s != sentence]
    want = 3 if level >= 3 else 2
    first, second = (same, others) if level >= 3 else (others, same)
    distractors = []
    for sent in first + second:
        if sent not in distractors:
            distractors.append(sent)
        if len(distractors) == want:
            break
    if len(distractors) < 2:
        return None
    options = [sentence, *distractors]
    options = options[num % len(options):] + options[:num % len(options)]
    letters = "ABCD"[:len(options)]
    lettered = [f"{letter}) {s}" for letter, s in zip(letters, options)]
    source, chapter, license = _teacher_source(meta)
    label = PRACTICE_LABELS[module["id"]].format(
        genre=DISCIPLINE_GENRES[discipline])
    return {"id": f"g{num + 1}", "type": "mcq", "kind": "recognise",
            "prompt": f"Which is the best {label}?",
            "options": lettered, "answer": letters[options.index(sentence)],
            "explanation": _teacher_explanation(skill, meta),
            "source": source, "chapter": chapter, "license": license,
            "skill": skill, "module": module["id"]}


def _write_item(kind: str, module: dict, skill: str, discipline: str,
                level: int, num: int) -> dict:
    """A repair/produce/apply item: free text judged against the rubric."""
    topic = DISCIPLINE_TOPICS[discipline]
    genre = DISCIPLINE_GENRES[discipline]
    label = PRACTICE_LABELS[module["id"]].format(genre=genre)
    if kind == "repair":
        lines = [w.format(topic=topic, genre=genre)
                 for w in WEAK_REPAIRS[module["id"]]]
        if level >= 3:
            prompt = f"Fix this weak paragraph: \"{' '.join(lines)}\""
        else:
            prompt = f"Fix this weak line: \"{lines[num % len(lines)]}\""
    elif kind == "produce":
        prompt = f"Write one {label} about {topic}."
    else:
        prompt = (f"Write {2 if level < 3 else 4} lines for your {genre} "
                  f"about {topic}.")
    return {"id": f"g{num + 1}", "type": "write", "kind": kind, "prompt": prompt,
            "options": [], "answer": "",
            "explanation": _practice_rubric_line(module["id"], discipline),
            "source": "", "skill": skill, "module": module["id"]}


def _module_pool(module: dict, discipline: str, genre: str,
                 n_results: int = 6) -> list:
    """Example excerpts for one module (docs with metas, blanks dropped)."""
    docs, metas = _query_guides(module_example_query(module, genre),
                                n_results=n_results)
    return [(d, m or {}) for d, m in zip(docs, metas) if (d or "").strip()]


def _generated_practice_set(skill: str, module_id: str, discipline: str,
                            level: int) -> list[dict]:
    """6 mixed items for a module; the bank fills any gap."""
    modules = {m["id"]: m for m in discipline_modules(discipline)}
    module = modules[module_id]
    genre = DISCIPLINE_GENRES[discipline]
    pool = _module_pool(module, discipline, genre)
    dpool: list[str] = []
    for other in [m for m in discipline_modules(discipline)
                  if m["id"] != module_id][:2]:
        for doc, _ in _module_pool(other, discipline, genre, n_results=2):
            dpool.extend(_excerpt_sentences(doc))
    items = []
    for num, kind in enumerate(PRACTICE_COMPOSITION):
        if kind == "recognise":
            item = _recognise_item(module, skill, discipline, level, num,
                                   pool, dpool)
        else:
            item = _write_item(kind, module, skill, discipline, level, num)
        if item is not None:
            items.append(item)
    if len(items) < PRACTICE_SET_SIZE:
        for bank in practice_items_for(skill, level, discipline):
            if len(items) >= PRACTICE_SET_SIZE:
                break
            fill = dict(bank)
            fill["skill"] = skill
            fill["module"] = SKILL_MODULE.get(skill)
            items.append(fill)
    for i, item in enumerate(items):
        item["id"] = f"g{i + 1}"
    return items


def _earlier_modules(discipline: str, scores: dict) -> list[dict]:
    """Modules before the learner's current one, in unlock order."""
    states = module_states(discipline, scores)
    idx = next((i for i, s in enumerate(states) if s.get("current")), 0)
    return states[max(0, idx - 3):idx]


def _review_set(discipline: str, level: int, earlier: list[dict],
                skill: str) -> list[dict]:
    """Recognise items, two per earlier module (bank fills any gap)."""
    genre = DISCIPLINE_GENRES[discipline]
    modules = {m["id"]: m for m in discipline_modules(discipline)}
    pools = {s["id"]: _module_pool(modules[s["id"]], discipline, genre)
             for s in earlier}
    dpool = [s for pool in pools.values() for d, _ in pool
             for s in _excerpt_sentences(d)]
    items: list[dict] = []
    num = 0
    for state in earlier:
        for _ in range(2):
            item = _recognise_item(modules[state["id"]], state["skill"],
                                   discipline, level, num,
                                   pools[state["id"]], dpool)
            num += 1
            if item is not None:
                items.append(item)
    for bank in practice_items_for(skill, level, discipline):
        if len(items) >= PRACTICE_SET_SIZE:
            break
        fill = dict(bank)
        fill["skill"] = skill
        fill["module"] = SKILL_MODULE.get(skill)
        items.append(fill)
    for i, item in enumerate(items):
        item["id"] = f"g{i + 1}"
    return items


@app.get("/practice")
def get_practice(learner_id: int):
    """Practise step: a short set on the next-win skill and level (no answers).

    A published teacher set wins when one matches skill + level (+ discipline).
    Otherwise a moduled skill gets a generated 4-type set, or a mixed review
    every third set when earlier modules exist; the bank covers the rest.
    """
    learner = store.get_learner(learner_id)
    if learner is None:
        raise HTTPException(status_code=404, detail="Unknown learner_id")
    discipline = learner.get("discipline") or "Sciences"
    saved = latest_scores(learner_id)
    if not saved:
        skill, level = "Paragraphing", 1
    else:
        levels = {s: level_for_score(v) for s, v in saved.items()}
        drafts = store.get_drafts(learner_id)
        latest = drafts[-1]["content"] if drafts else ""
        skill = next_win_skill(levels, latest)
        level = levels.get(skill, 1)
    demo = _demo_mode() and skill == "Paragraphing" and level == 1
    published = None if demo else store.get_teacher_set(skill, level, discipline)
    review: list[dict] | None = None
    if demo:
        items = _demo_practice_set()
    if not published and not demo:
        count = sum(1 for r in store.get_events(learner_id)
                    if r["tool"] == "get_practice")
        if count % REVIEW_EVERY == REVIEW_EVERY - 1:
            earlier = _earlier_modules(discipline, latest_scores(learner_id))
            if len(earlier) >= 2:
                review = earlier
    if published:
        items = [it for it in published["items"]
                 if verify("practice_item", it)["pass"]]
        if len(items) < len(published["items"]):
            store.log_event(learner_id, "Practise", "twin", "verify-items",
                            f"dropped {len(published['items']) - len(items)} failed items")
        if not items:  # every published item failed -> fall back to the bank
            published = None
    if review is not None:
        items = _review_set(discipline, level, review, skill)
    elif not published and not demo and SKILL_MODULE.get(skill) is not None:
        items = _generated_practice_set(skill, SKILL_MODULE[skill], discipline,
                                        level)
    elif not published and not demo:
        items = [it for it in practice_items_for(skill, level, discipline)
                 if verify("practice_item", it,
                           rules=PRACTICE_STRUCTURAL_RULES)["pass"]]
    if published:
        # Teacher actions have no learner of their own, so the set's history
        # is logged here, where it lands in the learner's How-it-decided
        # panel: generated from excerpts, verifier passed, published.
        sources = {it.get("source") for it in items if it.get("source")}
        excerpt_word = "excerpt" if len(sources) == 1 else "excerpts"
        store.log_event(
            learner_id, "Practise", "teacher", "teacher-set",
            f"Teacher set on {skill} Level {level} ({LEVEL_NAMES[level]}): "
            f"{len(items)} items built "
            f"from {len(sources)} {excerpt_word}, verifier passed, published.")
    set_id = uuid.uuid4().hex[:8]
    ISSUED_SETS[set_id] = {"learner_id": learner_id, "skill": skill,
                           "level": level, "discipline": discipline,
                           "published": published is not None,
                           "review": review is not None,
                           "demo": demo,
                           "items": items,
                           "answers": {it["id"]: it["answer"] for it in items}}
    public = [{k: v for k, v in it.items() if k not in ("answer", "variants")}
              for it in items]
    store.log_event(learner_id, "Practise", "twin", "get_practice",
                    f"set_id={set_id} skill={skill} level={level} items={len(items)}")
    return {"set_id": set_id, "learner_id": learner_id,
            "skill": "Mixed review" if review is not None else skill,
            "level": level, "discipline": discipline,
            "published": published is not None,
            "review": review is not None, "items": public}


@app.post("/practice/answers")
def post_answers(data: PracticeAnswersIn):
    """Score submitted answers; assess each; mastery moves skills up."""
    issued = ISSUED_SETS.get(data.set_id)
    if issued is None or issued["learner_id"] != data.learner_id:
        raise HTTPException(status_code=404, detail="Unknown or foreign set_id")
    skill = issued["skill"]
    items = issued.get("items") or practice_items_for(
        skill, issued["level"], issued.get("discipline"))
    judged = _judge_practice_set(data.learner_id, skill, items, data.answers,
                                 demo=issued.get("demo", False))
    details: list[dict] = []
    correct = 0
    per_skill: dict[str, list[int]] = {}
    for item in items:
        got = judged[item["id"]]
        ok = got["ok"]
        correct += ok
        hits = per_skill.setdefault(got["skill"], [0, 0])
        hits[0] += ok
        hits[1] += 1
        details.append({"id": item["id"], "correct": ok,
                        "explanation": item["explanation"] if not ok else "",
                        "assessment": {"feedback": got["feedback"],
                                       "score": got["score"],
                                       "next_step": got["next_step"],
                                       "module": got["module"]}})
    total = len(items)
    accuracy = round(100 * correct / total) if total else 0
    mastery: dict[str, bool] = {}
    moved: dict[str, float] = {}
    level_ups: list[dict] = []
    for iskill, (hit, count) in per_skill.items():
        store.save_practice_result(
            data.learner_id, iskill, round(100 * hit / count))
        start = level_for_score(latest_scores(data.learner_id).get(iskill, 0))
        if _mastery_move_up(data.learner_id, iskill):
            mastery[iskill] = True
            if _demo_mode():
                level_ups.append({"skill": iskill, "from": start,
                                  "to": start + 1})
            else:
                moved[iskill] = latest_scores(data.learner_id)[iskill]
                level_ups.append(
                    {"skill": iskill, "from": start,
                     "to": level_for_score(moved[iskill])})
        else:
            mastery[iskill] = False
    new_score: float | None = max(moved.values()) if moved else None
    store.log_event(data.learner_id, "Practise", "twin", "score_answers",
                    f"set_id={data.set_id} {correct}/{total} "
                    f"leveled_up={bool(level_ups)}")
    store.log_event(data.learner_id, "Practise", "twin", "assess",
                    f"assessed {total} answers")
    store.log_activity(data.learner_id, skill, "practice")
    level = level_for_score(new_score) if new_score is not None \
        else level_for_score(latest_scores(data.learner_id).get(skill, 0))
    return {"correct": correct, "total": total, "accuracy": accuracy,
            "skill": skill, "level": level, "new_score": new_score,
            "leveled_up": bool(level_ups), "mastery": mastery,
            "level_ups": level_ups, "details": details}


@app.post("/level-check")
def post_level_check(data: LevelCheckIn):
    """Grow step: current level per skill plus skills that just leveled up."""
    if store.get_learner(data.learner_id) is None:
        raise HTTPException(status_code=404, detail="Unknown learner_id")
    history: dict[str, list[float]] = {}
    for row in store.get_skill_scores(data.learner_id):  # oldest first
        history.setdefault(row["skill_name"], []).append(row["score"])
    levels, leveled_up = {}, []
    for skill in SKILLS:
        scores = history.get(skill, [])
        if not scores:
            continue
        levels[skill] = {"score": scores[-1], "level": level_for_score(scores[-1])}
        if len(scores) >= 2 and level_for_score(scores[-1]) > level_for_score(scores[-2]):
            leveled_up.append(skill)
    store.log_event(data.learner_id, "Grow", "growth", "level-check",
                    f"leveled_up={leveled_up}")
    return {"learner_id": data.learner_id, "levels": levels, "leveled_up": leveled_up}


@app.get("/growth")
def get_growth(learner_id: int):
    """Current skill levels, reasons and history for the growth chart."""
    if store.get_learner(learner_id) is None:
        raise HTTPException(status_code=404, detail="Unknown learner_id")
    scores = latest_scores(learner_id)
    levels = {skill: level_for_score(score) for skill, score in scores.items()}
    details: dict[str, dict] = {}
    history: dict[str, list[dict]] = {}
    for row in store.get_skill_scores(learner_id):
        details[row["skill_name"]] = {"reason": row.get("reason"),
                                      "evidence": row.get("evidence")}
        history.setdefault(row["skill_name"], []).append(
            {"score": row["score"], "date": row["date"]})
    session = session_state(learner_id)
    daily = {"sessions": session["sessions_done"], "target": SESSIONS_PER_DAY,
             "paragraphs": store.count_drafts_today(learner_id)}
    overall = overall_level(levels)
    strongest = next_win = None
    if levels:
        best = max(SKILLS, key=lambda s: levels.get(s, 1))
        drafts = store.get_drafts(learner_id)
        latest = drafts[-1]["content"] if drafts else ""
        win = next_win_skill(levels, latest)
        evidence = (details.get(win) or {}).get("evidence") or ""
        if not evidence and latest:
            sents = _text_sentences(latest)
            evidence = sents[0] if sents else latest
        strongest = {
            "skill": best,
            "reason": (details.get(best) or {}).get("reason")
            or "Your strongest skill right now."}
        next_win = {"skill": win, "action": NEXT_WIN_ACTIONS[win],
                    "quote": _first_words(evidence, 12)}
    return {"learner_id": learner_id, "scores": scores, "levels": levels,
            "details": details, "history": history,
            "overall": {"level": overall, "name": LEVEL_NAMES[overall]},
            "strongest": strongest, "next_win": next_win, "daily": daily,
            "session": session}


def independence(learner_id: int) -> dict:
    """Hint-use trend across recent scaffold attempts (one task, one session).

    Windows are the last 3 attempts' hint + "Show me now" + worked-steps
    counts, oldest first. Improving when use strictly falls, or stays zero.
    """
    helps: dict[str, int] = {}
    order: list[str] = []
    for row in store.get_scaffold_events(learner_id):
        match = re.search(r"attempt_id=(\S+)", row["result"] or "")
        if not match:
            continue
        aid = match.group(1)
        if aid not in helps:
            helps[aid] = 0
            order.append(aid)
        if row["tool"] in ("hint", "show-me", "steps"):
            helps[aid] += 1
    windows = [helps[a] for a in order[-3:]]
    if not windows:
        return {"attempts": 0, "hints": [], "improving": False,
                "message": "Try a module task to start tracking."}
    improving = all(w == 0 for w in windows) or (
        len(windows) >= 2
        and all(b < a for a, b in zip(windows, windows[1:])))
    return {"attempts": len(order), "hints": windows, "improving": improving,
            "message": f"Hints used: {' → '.join(map(str, windows))}"}


@app.get("/independence")
def get_independence(learner_id: int):
    """Hint-use trend for the My Growth independence card."""
    if store.get_learner(learner_id) is None:
        raise HTTPException(status_code=404, detail="Unknown learner_id")
    return {"learner_id": learner_id, **independence(learner_id)}


@app.post("/delete-data")
def post_delete_data(data: DeleteDataIn):
    """Delete everything for a learner: drafts, scores, results, logs."""
    if store.get_learner(data.learner_id) is None:
        raise HTTPException(status_code=404, detail="Unknown learner_id")
    store.reset_learner(data.learner_id)
    for set_id in [s for s, v in ISSUED_SETS.items()
                   if v.get("learner_id") == data.learner_id]:
        del ISSUED_SETS[set_id]
    for attempt_id in [a for a, v in SCAFFOLD_ATTEMPTS.items()
                       if v.get("learner_id") == data.learner_id]:
        del SCAFFOLD_ATTEMPTS[attempt_id]
    return {"ok": True, "learner_id": data.learner_id,
            "message": "All your data was deleted. Starting fresh."}


# --- Voice input (Muse Voice Transcribe) --------------------------------------
# Push-to-talk dictation: browser mic -> this backend -> Meta's realtime API
# -> transcript back into the text box. Meta message format, per
# dev.meta.ai/docs: the handshake is the first JSON text frame (the credential
# travels inside it, never in an HTTP header), audio is raw PCM16 mono binary
# frames, {"type": "endStream"} ends input, and server events look like
# {"type": "transcript", "transcript": ..., "final": ...}.
MUSE_ASR_URL = "wss://api.meta.ai/v1/asr/realtime"
MUSE_ASR_MODEL = "muse-voice-transcribe-1.0"
TRANSCRIBE_CREDIT = "Transcribed by Muse Voice Transcribe"
# One session budget: connect, handshake, and relay share it, so a stalled
# server answers with a timeout error instead of hanging the mic forever.
VOICE_TIMEOUT = 20


class VoiceError(Exception):
    """A voice failure with a reason and a learner-facing message."""

    def __init__(self, reason: str, message: str):
        super().__init__(message)
        self.reason = reason
        self.message = message

# Meta's documented languageBias names for our learners. Malayalam is not on
# Meta's documented list: the hint is omitted (auto-detect) and Meta is still
# tried first; on failure the browser falls back to its own recognizer.
META_LANGUAGE_HINTS = {"Hindi": "Hindi", "Tamil": "Tamil",
                       "Telugu": "Telugu", "Kannada": "Kannada",
                       "Bengali": "Bengali", "Marathi": "Marathi",
                       "English": "English"}

# BCP-47 tags for the browser fallback recognizer.
BROWSER_SPEECH_LANGS = {"Hindi": "hi-IN", "Tamil": "ta-IN",
                        "Telugu": "te-IN", "Kannada": "kn-IN",
                        "Bengali": "bn-IN", "Marathi": "mr-IN",
                        "Malayalam": "ml-IN", "English": "en-IN"}


def meta_language_hint(language: str | None) -> list[str]:
    """languageBias for the Meta handshake ([] = let Meta detect)."""
    hint = META_LANGUAGE_HINTS.get(language or "")
    return [hint] if hint else []


def browser_speech_lang(language: str | None) -> str:
    """BCP-47 tag for the browser fallback recognizer."""
    return BROWSER_SPEECH_LANGS.get(language or "", "en-IN")


def _env_key(*names: str) -> str | None:
    """First matching key from the environment, else backend .env."""
    for name in names:
        key = os.environ.get(name, "").strip()
        if key:
            return key
    env_path = Path(__file__).resolve().parent / ".env"
    try:
        env_text = env_path.read_text(encoding="utf-8")
    except OSError:
        return None
    for line in env_text.splitlines():
        name, sep, value = line.partition("=")
        if sep and name.strip() in names:
            found = value.strip().strip('"').strip("'")
            if found:
                return found
    return None


def _meta_api_key() -> str | None:
    """Model API key from the environment or backend .env (never the browser)."""
    return _env_key("META_API_KEY")


def _model_api_key() -> str | None:
    """Docs-canonical MODEL_API_KEY, falling back to this repo's META_API_KEY."""
    return _env_key("MODEL_API_KEY", "META_API_KEY")


def muse_handshake(api_key: str, hint: list[str]) -> dict:
    """First JSON frame of a Meta realtime session (documented fields)."""
    handshake = {
        "authorization": {"accessToken": f"Bearer {api_key}"},
        "audioEncoding": "PCM_16KHZ",
        "model": MUSE_ASR_MODEL,
        "mode": "PUSH_TO_TALK",
    }
    if hint:
        handshake["languageBias"] = list(hint)
    return handshake


def parse_muse_event(event: dict) -> dict:
    """One Meta server frame -> transcript / error / ignore (docs: dispatch
    on type, ignore unknown values)."""
    if not isinstance(event, dict):
        return {"kind": "ignore"}
    if event.get("type") == "transcript":
        return {"kind": "transcript", "text": event.get("transcript", ""),
                "final": bool(event.get("final"))}
    if event.get("type") == "error":
        return {"kind": "error", "message": event.get("message", "")}
    return {"kind": "ignore"}


def _meta_close_note(meta) -> str | None:
    """Why Meta closed the session, for the error the learner sees."""
    try:
        code = meta.close_code
    except Exception:
        return None
    if code is None or code == 1000:
        return None
    try:
        reason = meta.close_reason or ""
    except Exception:
        reason = ""
    note = f"Meta closed the session ({code})"
    return f"{note}: {reason}" if reason else note


async def _transcribe_relay(browser: WebSocket, meta
                            ) -> tuple[str | None, bool, str | None]:
    """Pump audio browser -> Meta and transcripts Meta -> browser.

    Returns (final transcript or None, browser still connected, failure note
    or None). Both pump tasks are always stopped, even on cancellation.
    """
    final: str | None = None
    alive = True
    note: str | None = None

    async def upstream() -> None:
        nonlocal alive
        try:
            while True:
                message = await browser.receive()
                if message["type"] == "websocket.disconnect":
                    alive = False
                    break
                if message.get("bytes") is not None:
                    try:
                        await meta.send(message["bytes"])
                    except Exception:
                        break  # Meta went away: nothing more to stream
                else:
                    try:
                        frame = json.loads(message.get("text") or "")
                    except ValueError:
                        continue
                    if frame.get("type") == "stop":
                        try:
                            await meta.send(json.dumps({"type": "endStream"}))
                        except Exception:
                            pass
                        break
        except (RuntimeError, Exception):
            alive = False

    async def downstream() -> None:
        nonlocal final, note
        try:
            async for message in meta:
                if isinstance(message, bytes):
                    continue
                try:
                    event = json.loads(message)
                except ValueError:
                    continue
                parsed = parse_muse_event(event)
                if parsed["kind"] == "transcript":
                    if parsed["final"]:
                        final = parsed["text"]
                        break
                    try:
                        await browser.send_json({"type": "partial",
                                                 "text": parsed["text"]})
                    except Exception:
                        break
                elif parsed["kind"] == "error":
                    note = parsed["message"] or "Meta error"
                    break
        except Exception:
            pass

    up = asyncio.create_task(upstream())
    down = asyncio.create_task(downstream())
    try:
        await asyncio.wait({up, down}, return_when=asyncio.FIRST_COMPLETED)
        if up.done() and alive and not down.done():
            # Stop was sent: keep reading Meta for the final (bounded).
            try:
                await asyncio.wait_for(down, timeout=30)
            except asyncio.TimeoutError:
                down.cancel()
        else:
            # Browser gone, or Meta finished first: stop the other side.
            for task in (up, down):
                if not task.done():
                    task.cancel()
    finally:
        for task in (up, down):
            task.cancel()
        await asyncio.gather(up, down, return_exceptions=True)
    if final is None and note is None:
        note = _meta_close_note(meta)
    return final, alive, note


async def _voice_fail(browser: WebSocket, learner_id: int, reason: str,
                      message: str) -> None:
    """Tell the browser the real failure, log it, and close (never hangs)."""
    try:
        await browser.send_json({"type": "meta_error", "reason": reason,
                                 "message": message})
    except Exception:
        pass
    store.log_event(learner_id, "Voice", "twin", "transcribe",
                    f"voice failed ({reason}): {message[:140]}")
    try:
        await browser.close()
    except Exception:
        pass


async def _meta_voice_session(browser: WebSocket, api_key: str, hint: list[str]
                              ) -> tuple[str | None, bool, str | None]:
    """Meta connect + handshake + relay. Returns (final, alive, note).

    Raises VoiceError with the failure reason. Always closes Meta itself so
    a session timeout never leaks the server-side session.
    """
    try:
        import websockets
    except ImportError:  # pragma: no cover - dependency is installed
        raise VoiceError("no-client",
                         "Voice input is not available (missing client).")
    session_id = f"vibe-{uuid.uuid4().hex[:12]}"
    try:
        meta = await websockets.connect(
            f"{MUSE_ASR_URL}?sessionId={session_id}",
            open_timeout=VOICE_TIMEOUT)
    except Exception as exc:
        raise VoiceError(
            "connect-failed",
            "Could not reach the transcription service "
            f"({str(exc)[:100]}).") from exc
    try:
        try:
            await meta.send(json.dumps(muse_handshake(api_key, hint)))
            ack = json.loads(await meta.recv())
        except Exception:
            ack = {}
        if "sessionId" not in ack:
            parsed = parse_muse_event(ack)
            raise VoiceError(
                "handshake-failed",
                parsed.get("message") or _meta_close_note(meta)
                or "The transcription service rejected the session.")
        return await _transcribe_relay(browser, meta)
    finally:
        try:
            await meta.close()
        except (asyncio.CancelledError, Exception):
            pass


@app.websocket("/ws/transcribe")
async def ws_transcribe(browser: WebSocket, learner_id: int = 0):
    """Relay browser mic audio to Meta and stream the transcript back.

    Browser protocol: connect with ?learner_id=N; first receive ready
    {"type": "ready", "metaHint": [...], "browserLang": "ml-IN"}; send binary
    PCM16 mono 16 kHz frames while holding Speak; send {"type": "stop"} on
    release. The server answers {"type": "partial"/"final", "text"} or
    {"type": "meta_error", "reason", "message"} with the real failure. The
    Meta session shares one VOICE_TIMEOUT budget: a stalled server answers
    with a timeout error instead of hanging the mic.
    """
    await browser.accept()
    learner = store.get_learner(learner_id)
    if learner is None:
        await browser.send_json({"type": "error", "reason": "unknown-learner",
                                 "message": "Learner not found. Try again."})
        await browser.close()
        return
    language = learner.get("language_preference") or ""
    hint = meta_language_hint(language)
    await browser.send_json({"type": "ready", "metaHint": hint,
                             "browserLang": browser_speech_lang(language)})
    api_key = _meta_api_key()
    if not api_key:
        await _voice_fail(browser, learner_id, "no-key",
                          "Voice input is not available (missing API key).")
        return
    try:
        final, alive, note = await asyncio.wait_for(
            _meta_voice_session(browser, api_key, hint),
            timeout=VOICE_TIMEOUT)
    except asyncio.TimeoutError:
        await _voice_fail(
            browser, learner_id, "timeout",
            f"Voice input timed out after {VOICE_TIMEOUT} seconds. Try again.")
        return
    except VoiceError as exc:
        await _voice_fail(browser, learner_id, exc.reason, exc.message)
        return
    if not alive:
        try:
            await browser.close()
        except Exception:
            pass
        return
    if final is None:
        message = f"Transcription failed ({note})." if note \
            else "Transcription failed. Try again."
        await _voice_fail(browser, learner_id, "transcribe-failed", message)
        return
    await browser.send_json({"type": "final", "text": final})
    store.log_event(learner_id, "Voice", "twin", "transcribe",
                    TRANSCRIBE_CREDIT)
    try:
        await browser.close()
    except Exception:
        pass


@app.post("/teacher/practice-sets")
def post_teacher_set(data: TeacherSetIn):
    """Generate items from library excerpts; report the Verifier result."""
    parsed = parse_teacher_request(data.request)
    items, engine = _generate_practice_set(data.request, data.note)
    if not items:
        errors = ["No usable excerpts in the library for this request."]
    else:
        verdict = verify("practice_set", items)
        errors = [_practice_failure_message(items, e) for e in verdict["failed"]]
    return {"passed": not errors, "errors": errors, "items": items,
            "skill": parsed["skill"], "level": parsed["level"],
            "discipline": parsed["discipline"], "engine": engine}


@app.post("/teacher/publish")
def post_teacher_publish(data: TeacherPublishIn):
    """Verify again and publish; published sets appear in learners' Practice."""
    verdict = verify("practice_set", data.items)
    if not verdict["pass"]:
        detail = "; ".join(
            "Practice set is empty." if e == "non-empty"
            else _practice_failure_message(data.items, e)
            for e in verdict["failed"])
        raise HTTPException(status_code=400, detail=detail)
    if data.skill not in SKILLS:
        raise HTTPException(status_code=400, detail="Unknown skill")
    if data.level not in (1, 2, 3, 4, 5):
        raise HTTPException(status_code=400, detail="Level must be 1-5")
    if data.discipline is not None and data.discipline not in store.DISCIPLINES:
        raise HTTPException(status_code=400, detail="Unknown discipline")
    set_id = store.save_teacher_set(data.skill, data.level, data.discipline,
                                    data.items, data.request)
    return {"ok": True, "set_id": set_id}


# --- Verifier for twin replies ----------------------------------------------------------
# Checklist mirrors TWIN_SYSTEM_PROMPT. Returns a list of problems (empty =
# passed), like verify_practice_set. A reply that breaks any rule fails and is
# never served: the endpoint falls back to twin_safe_reply instead.
GENERIC_PRAISE_PHRASES = ("great job", "excellent", "amazing")  # keep in sync with TWIN_SYSTEM_PROMPT


def _has_generic_praise(text: str) -> str | None:
    """First generic-praise phrase found (case-insensitive), else None."""
    lowered = (text or "").lower()
    for phrase in GENERIC_PRAISE_PHRASES:
        if re.search(r"\b" + re.escape(phrase) + r"\b", lowered):
            return phrase
    return None


def verify_twin_reply(reply: str, message: str | None = None) -> list[str]:
    """Checklist for twin replies. Return problems (empty = passed)."""
    result = verify("twin_reply", reply, {"message": message})
    errors = []
    for rule in result["failed"]:
        if rule == "not-empty":
            errors.append("Reply is empty.")
        elif rule == "no-generic-praise":
            found = _has_generic_praise(reply)
            errors.append(f"No generic praise: reply contains '{found}'.")
        else:
            errors.append("No invented examples: quote only the learner's words or book excerpts.")
    return errors


def _has_non_latin(text: str) -> bool:
    """True when the text has letters outside the Latin script."""
    return any(ch.isalpha() and ord(ch) > 0x024F for ch in (text or ""))


# Common Manglish words (Malayalam typed in Latin letters). Any one of these
# marks the message as Manglish so the twin reflects it back in English.
MANGLISH_WORDS = frozenset({
    "enikku", "enne", "ente", "njan", "njaan", "ningal",
    "enth", "entha", "enthu", "enthina", "engane", "eppol", "evide",
    "illa", "alla", "aano", "alle",
    "manassilayi", "manassilayilla", "manassilayo",
    "ariyilla", "ariyamo", "ariyumo",
    "venam", "venda", "vayya",
    "ezhuthi", "ezhuthan", "ezhuthamo", "ezhuthiya",
    "parayu", "parayamo", "paranj",
    "cheyyan", "cheyth", "cheyyamo",
    "tharumo", "thanne",
    "vayich", "padich", "padikkan",
    "sari", "sariyaano", "sahayam",
    "valare", "kurach", "koodi", "mathram",
    "pakshe", "engil", "ennal", "dayavayi",
    "kuzhappamilla", "karyamilla",
})


def _is_manglish(text: str) -> bool:
    """True when the text looks like Manglish (Malayalam in Latin letters)."""
    words = set(re.findall(r"[a-z]+", (text or "").lower()))
    return not MANGLISH_WORDS.isdisjoint(words)


# Distinctive English words (3+ letters; ambiguous shorts like "me" or "is"
# are left out since they collide with other languages). Latin-script input
# with none of these is treated as a non-English language.
ENGLISH_WORDS = frozenset({
    "the", "and", "are", "was", "were", "been", "have", "has", "had",
    "will", "would", "could", "should", "shall", "does", "did",
    "with", "from", "that", "this", "these", "those", "what", "when",
    "where", "which", "how", "why", "because", "than", "then", "them",
    "they", "their", "your", "yours", "you", "about", "into", "over",
    "but", "not", "for", "she", "her", "his", "him", "our", "can",
    "please", "thanks", "thank", "hello", "sorry",
    "help", "hint", "give", "tell", "show", "need", "want",
    "check", "first", "line", "write", "writing",
    "sentence", "sentences", "paragraph", "essay", "grammar", "verb",
    "word", "words", "answer", "question", "correct", "wrong",
    "good", "better", "mistake", "easy", "hard", "difficult",
})


def _is_english(text: str) -> bool:
    """True when Latin-script text shows evidence of English.

    Empty or wordless text defaults to True (no foreign evidence); anything
    with Latin words but no English marker is some other language.
    """
    words = set(re.findall(r"[a-z]+", (text or "").lower()))
    if not words:
        return True
    return not ENGLISH_WORDS.isdisjoint(words)


def twin_safe_reply(message: str, weakest: str) -> str:
    """Compliant fallback: main problem first, then a hint. English only.

    The learner's own words are quoted only when they are English; anything
    else falls back to "your draft" so the reply stays in simple English.
    """
    snippet = " ".join((message or "").split())[:120]
    if snippet and not _has_generic_praise(snippet) and not _has_non_latin(snippet):
        quoted = f'"{snippet}"'
    else:
        quoted = "your draft"
    return (
        f"The main problem in {quoted} is {weakest.lower()}. "
        f"{TWIN_HINTS.get(weakest, TWIN_HINTS['Paragraphing'])}"
    )


TWIN_HINTS = {
    "Grammar": "Check your verbs. Does each he, she, or it need an s at the end?",
    "Vocabulary": "Find one weak word. Use a strong word in its place.",
    "Sentence structure": "Read your longest sentence. Can you cut it in two with because or but?",
    "Paragraphing": "Read only your first line. Does it tell the main idea?",
    "Argument": "Find your reason word: because, so, or therefore. No reason word? No argument yet.",
    "Using sources": "Add 'According to' before one fact. Whose idea was it?",
    "Academic tone": "Find one chatty word. Use a calm word in its place.",
}


TWIN_STARTERS = {
    "Grammar": "She ___ to school daily.",
    "Vocabulary": "The result was ___.",
    "Sentence structure": "She stayed home because ___.",
    "Paragraphing": "My paragraph is about ___.",
    "Argument": "Schools should ___ because ___.",
    "Using sources": "According to ___, ___.",
    "Academic tone": "This suggests that ___.",
}


def twin_scaffold_reply(message: str, weakest: str) -> str:
    """2-3 sentence future-self reply: simple English only, no full answers.

    Learners may write in any language. Anything except English - Malayalam
    script, Manglish, or any other language - gets the idea reflected back
    in simple English plus one sentence starter. (Template until Muse Spark
    lands with real translation.)
    """
    lowered = message.lower()
    if any(t in lowered for t in ["write it for me", "write my", "do my homework",
                                  "full answer", "write the paragraph", "essay for me"]):
        return ("I will not write it for you. "
                "Send me your first line. "
                "I will tell you what is strong in it.")
    if (_has_non_latin(message) or _is_manglish(message)
            or not _is_english(message)):
        starter = TWIN_STARTERS.get(weakest, TWIN_STARTERS["Paragraphing"])
        return ("You are saying that this part is hard for you. "
                f"Start with this: '{starter}'")
    return (f"{TWIN_HINTS.get(weakest, TWIN_HINTS['Paragraphing'])} "
            f"{twin_note(weakest)}")


@app.get("/drafts")
def get_drafts(learner_id: int):
    """List a learner's previous drafts with feedback (for My Writing)."""
    if store.get_learner(learner_id) is None:
        raise HTTPException(status_code=404, detail="Unknown learner_id")
    return {"learner_id": learner_id, "drafts": store.get_drafts(learner_id)}


@app.get("/events")
def get_events(learner_id: int, limit: int = 6):
    """Latest audit rows for the 'How it decided' panel (at most 6 lines)."""
    if store.get_learner(learner_id) is None:
        raise HTTPException(status_code=404, detail="Unknown learner_id")
    return {"learner_id": learner_id,
            "events": store.get_recent_events(learner_id, min(max(limit, 1), 6))}


@app.post("/twin/ask")
def post_twin_ask(data: TwinAskIn):
    """Bridge step: short scaffolded twin reply (template until Muse Spark lands)."""
    if store.get_learner(data.learner_id) is None:
        raise HTTPException(status_code=404, detail="Unknown learner_id")
    weakest, _ = weakest_skill(latest_scores(data.learner_id))
    if _demo_mode():
        drafts = store.get_drafts(data.learner_id)
        if drafts and _demo_text_match(drafts[-1]["content"],
                                       DEMO_WEAK_PARAGRAPH):
            # Fixed script, pre-approved: it quotes the draft, which the
            # verifier (chat message only) would reject.
            store.log_event(data.learner_id, "Bridge", "twin", "demo-twin",
                            "Demo twin reply (fixed)")
            return {"reply": DEMO_TWIN_RESPONSE, "weakest": weakest}
    reply = twin_scaffold_reply(data.message, weakest)
    verdict = verify("twin_reply", reply, {"message": data.message})
    if not verdict["pass"]:  # never serve a reply that breaks the checklist
        store.log_event(data.learner_id, "Bridge", "twin", "verify-reply",
                        f"rejected reply: {verdict['failed']}")
        reply = twin_safe_reply(data.message, weakest)
    store.log_event(data.learner_id, "Bridge", "twin", "scaffold-reply",
                    f"screen={data.screen} weakest={weakest}")
    return {"reply": reply, "weakest": weakest}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000)
