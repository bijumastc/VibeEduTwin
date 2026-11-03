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
  POST /scaffold/rewrite      accept the learner's rewrite
  POST /teacher/practice-sets  generate a set from plain language + verify it

Every endpoint writes to the event log (learner_store), so the app can
later show "How it decided". Skill scoring is simple heuristic logic for
now; each scorer is one function so Muse Spark can replace it later.

Run:
  .venv\\Scripts\\python.exe -m uvicorn main:app --reload     (dev)
  .venv\\Scripts\\python.exe main.py                          (direct)
"""

import json
import re
import uuid
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.encoders import jsonable_encoder
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

import learner_store as store

# --- Twin system prompt ---------------------------------------------------------
# Used by every LLM call once Muse Spark is wired in. The twin speaks as the
# learner's future self, guides instead of answering, in simple English only.
TWIN_SYSTEM_PROMPT = (
    "You are the learner's future self: a confident student who once found "
    "English writing hard and now writes well. Speak warmly, in first person, "
    "as someone who remembers the struggle. Reply ONLY in simple, short "
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
LEVEL_PASS_SCORE = 80  # practice accuracy % needed to bump a skill
SKILL_BUMP = 10        # points added to a skill after a strong practice set

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


class DiagnoseIn(BaseModel):
    learner_id: int
    draft_id: int | None = None   # either draft_id or raw content is required
    content: str | None = None


class PracticeAnswersIn(BaseModel):
    learner_id: int
    set_id: str
    answers: dict[str, str]  # item_id -> learner's answer


class LevelCheckIn(BaseModel):
    learner_id: int


class TeacherSetIn(BaseModel):
    request: str = Field(min_length=1, description="Plain-language practice request")


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


class ScaffoldRewriteIn(BaseModel):
    learner_id: int
    attempt_id: str
    text: str = ""


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


def twin_note(weakest: str) -> str:
    """Short future-self note in the twin's voice (template until LLM lands)."""
    return (
        f"I found {weakest.lower()} hard too. "
        f"Let's fix one small part today."
    )


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


def verified_excerpt(query_text: str, sentences: int = 3) -> dict:
    """Best library excerpt for a query, with book/chapter/license provenance.

    Returns {"text", "source", "chapter", "license"}; when nothing suitable
    exists, text is NO_VERIFIED_EXAMPLE and provenance is None.
    """
    docs, metas = _query_guides(query_text, n_results=3)
    for doc, meta in zip(docs, metas):
        text = first_sentences(doc or "", sentences)
        if text.strip():
            meta = meta or {}
            return {"text": text, "source": meta.get("source"),
                    "chapter": meta.get("chapter"), "license": meta.get("license")}
    return {"text": NO_VERIFIED_EXAMPLE, "source": None,
            "chapter": None, "license": None}


def learn_card(skill: str, level: int, discipline: str) -> dict:
    """Build a short Learn card from verified library excerpts only."""
    genre = DISCIPLINE_GENRES[discipline]
    return {"skill": skill, "level": level, "discipline": discipline,
            "rule": verified_excerpt(f"{skill} writing rule"),
            "example": verified_excerpt(f"{skill} writing example {genre}")}


# --- Curriculum ---------------------------------------------------------------
# Six disciplines, six ordered modules each. The first five modules are shared;
# the sixth teaches the discipline's genre (Medicine: writing about case
# reports only - never health advice).
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
]


def genre_module(discipline: str) -> dict:
    """The sixth module: writing the discipline's genre."""
    genre = DISCIPLINE_GENRES[discipline]
    return {"id": "genre", "title": (genre + "s").capitalize(),
            "skill": "Academic tone", "required_level": 3,
            "query": f"{genre} writing"}


def discipline_modules(discipline: str) -> list[dict]:
    """All six modules for a discipline, in unlock order."""
    return [*CURRICULUM_MODULES, genre_module(discipline)]


def module_states(discipline: str, scores: dict[str, float]) -> list[dict]:
    """Module list with unlock state; the highest unlocked module is current.

    Modules unlock in order: a module opens when every earlier module is open
    and the learner's level in the module's skill meets required_level.
    """
    states = []
    prev_open = True
    for module in discipline_modules(discipline):
        level = level_for_score(scores.get(module["skill"], 0))
        unlocked = prev_open and level >= module["required_level"]
        states.append({"id": module["id"], "title": module["title"],
                       "skill": module["skill"],
                       "required_level": module["required_level"],
                       "learner_level": level, "unlocked": unlocked,
                       "current": False})
        prev_open = unlocked
    for state in reversed(states):
        if state["unlocked"]:
            state["current"] = True
            break
    return states


def module_rule_query(module: dict) -> str:
    """ChromaDB query for a module's rule excerpt."""
    return f"{module['query']} rule"


def module_example_query(module: dict, genre: str) -> str:
    """ChromaDB query for a module's discipline example excerpt."""
    return f"{module['query']} example {genre}"


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
    if _attempt_sentences(text) < 1 or len(text.split()) < 5:
        return "Write one full sentence of five or more words."
    return "Use calm, exact words. No 'very' or 'really'."


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


def score_academic_tone(text: str) -> int:
    """Penalise chatty words, reward formal/hedging words."""
    informal = ["very", "really", "a lot", "thing", "things", "get", "got",
                "gonna", "wanna", "can't", "don't", "doesn't", "isn't"]
    formal = ["however", "moreover", "furthermore", "significant", "demonstrate",
              "indicate", "suggest", "therefore"]
    lowered = text.lower()
    score = 70 - 6 * min(5, sum(lowered.count(w) for w in informal))
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
    """Score text on all 7 skills with the current (heuristic) scorers."""
    return {skill: SCORERS[skill](text) for skill in SKILLS}


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


# --- Verifier for teacher-generated sets ----------------------------------------------
def verify_practice_set(items: list[dict]) -> list[str]:
    """Return a list of problems (empty = passed). Rules are deliberately strict."""
    errors: list[str] = []
    if not items:
        return ["Practice set is empty."]
    seen_ids: set[str] = set()
    for i, item in enumerate(items):
        where = f"item {i + 1}"
        if not isinstance(item, dict):
            errors.append(f"{where}: not an object.")
            continue
        item_id = item.get("id", "")
        if not item_id or item_id in seen_ids:
            errors.append(f"{where}: missing or duplicate id.")
        seen_ids.add(item_id)
        if not (item.get("prompt") or "").strip():
            errors.append(f"{where}: empty prompt.")
        if item.get("type") not in ("mcq", "order"):
            errors.append(f"{where}: type must be 'mcq' or 'order'.")
        options = item.get("options") or []
        if len(options) < 2:
            errors.append(f"{where}: need at least 2 options.")
        answer = (item.get("answer") or "").strip()
        if not answer:
            errors.append(f"{where}: missing answer.")
        elif item.get("type") == "mcq" and not any(
                str(o).strip().lower().startswith(answer.lower()) for o in options):
            errors.append(f"{where}: answer '{answer}' matches no option.")
        if not (item.get("explanation") or "").strip():
            errors.append(f"{where}: missing explanation (learners need feedback).")
    return errors


def generate_practice_set(request_text: str) -> list[dict]:
    """Build a practice set from a plain-language request (template logic now).

    Muse Spark will replace this body later; the verifier below stays the same.
    """
    lowered = request_text.lower()
    skill = next((s for s in SKILLS if s.lower() in lowered), "Paragraphing")
    base = practice_items_for(skill, 1)
    count = 3 if any(w in lowered for w in ["three", "3"]) else 2
    items = []
    for i, item in enumerate(base[:count]):
        items.append({
            "id": f"t{i + 1}",
            "type": item["type"],
            "prompt": f"[{skill}] {item['prompt']}",
            "options": list(item["options"]),
            "answer": item["answer"],
            "explanation": item["explanation"],
        })
    return items


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
    draft_id = store.save_draft(data.learner_id, data.content, feedback="")
    store.save_writing_sample(data.learner_id, data.content)
    store.log_event(data.learner_id, "Write", "twin", "post_draft",
                    f"draft_id={draft_id} words={len(data.content.split())}")
    return {"ok": True, "draft_id": draft_id, "learner_id": data.learner_id,
            "message": "Draft saved."}


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
    scores = diagnose_text(text)
    weakest = min(SKILLS, key=lambda s: scores[s])
    store.save_skill_scores(data.learner_id, scores)
    store.log_event(data.learner_id, "Diagnose", "diagnose", "heuristic-scorer",
                    f"weakest={weakest} scores={scores}")
    level = level_for_score(scores[weakest])
    discipline = learner.get("discipline") or "Sciences"
    if prev_scores:
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
    return {"scores": scores, "weakest": weakest,
            "level": level,
            "twin_note": twin_note(weakest),
            "comparison": comparison,
            "level_changes": level_changes,
            "study_material": study_material(weakest),
            "learn": learn_card(weakest, level, discipline)}


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
    """(unlock state, module content) for a learner, or raise 404/400/403."""
    if store.get_learner(learner_id) is None:
        raise HTTPException(status_code=404, detail="Unknown learner_id")
    if discipline not in DISCIPLINE_GENRES:
        raise HTTPException(status_code=400, detail="Unknown discipline")
    modules = {m["id"]: m for m in discipline_modules(discipline)}
    if module_id not in modules:
        raise HTTPException(status_code=404, detail="Unknown module")
    states = {s["id"]: s for s in module_states(discipline, latest_scores(learner_id))}
    state = states[module_id]
    if not state["unlocked"]:
        if state["learner_level"] < state["required_level"]:
            detail = (f"Reach Level {state['required_level']} in "
                      f"{state['skill']} to unlock this module.")
        else:
            detail = "Unlock earlier modules first."
        raise HTTPException(status_code=403, detail=detail)
    return state, modules[module_id]


@app.get("/curriculum/modules")
def get_curriculum_module(learner_id: int, discipline: str, module: str):
    """Learn step: one module's verified rule + example excerpts."""
    _, content = _module_state_or_raise(learner_id, discipline, module)
    genre = DISCIPLINE_GENRES[discipline]
    store.log_event(learner_id, "Learn", "twin", "get_module",
                    f"discipline={discipline} module={module}")
    return {"discipline": discipline, "module": module, "title": content["title"],
            "skill": content["skill"],
            "rule": verified_excerpt(module_rule_query(content)),
            "example": verified_excerpt(module_example_query(content, genre))}


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


def _serve_excerpt(learner_id: int, attempt_id: str, attempt: dict,
                   tool: str) -> dict:
    """Serve step (d): a real book excerpt with source. Never an answer."""
    genre = DISCIPLINE_GENRES[attempt["discipline"]]
    modules = {m["id"]: m for m in discipline_modules(attempt["discipline"])}
    excerpt = verified_excerpt(
        module_example_query(modules[attempt["module"]], genre))
    attempt["step"] = "excerpt"
    store.log_event(learner_id, "Scaffold", "twin", tool,
                    f"attempt_id={attempt_id} module={attempt['module']}")
    return _scaffold_view(attempt_id, attempt, {"excerpt": excerpt})


@app.post("/scaffold/start")
def post_scaffold_start(data: ScaffoldStartIn):
    """Scaffold step (a): hand out the task; the learner tries with no help."""
    state, content = _module_state_or_raise(
        data.learner_id, data.discipline, data.module)
    attempt_id = uuid.uuid4().hex[:8]
    SCAFFOLD_ATTEMPTS[attempt_id] = {
        "learner_id": data.learner_id, "discipline": data.discipline,
        "module": data.module, "skill": content["skill"],
        "level": state["learner_level"], "step": "try", "q_index": 0,
    }
    store.log_event(data.learner_id, "Scaffold", "twin", "start",
                    f"attempt_id={attempt_id} module={data.module}")
    return _scaffold_view(attempt_id, SCAFFOLD_ATTEMPTS[attempt_id],
                          {"level": state["learner_level"]})


@app.post("/scaffold/help")
def post_scaffold_help(data: ScaffoldHelpIn):
    """Move one rung up the ladder: question -> hint -> excerpt -> rewrite.

    Levels 1-2 reach hints sooner; Levels 4-5 get only questions.
    """
    attempt_id, attempt = _scaffold_attempt_or_raise(
        data.learner_id, data.attempt_id)
    if attempt["step"] in ("rewrite", "done"):
        return _scaffold_view(attempt_id, attempt)
    level = attempt["level"]
    genre = DISCIPLINE_GENRES[attempt["discipline"]]
    topic = DISCIPLINE_TOPICS[attempt["discipline"]]
    if attempt["step"] == "excerpt":
        attempt["step"] = "rewrite"
        return _scaffold_view(attempt_id, attempt, {
            "prompt": "Now rewrite using the pattern."})
    if attempt["step"] == "hint":
        return _serve_excerpt(data.learner_id, attempt_id, attempt, "excerpt")
    allowed = QUESTIONS_BEFORE_HINT.get(level)
    if level >= 4 or attempt["q_index"] < (allowed or 0):
        question = scaffold_question(
            attempt["module"], attempt["q_index"], genre)
        attempt["q_index"] += 1
        attempt["step"] = "question"
        store.log_event(data.learner_id, "Scaffold", "twin", "question",
                        f"attempt_id={attempt_id} module={attempt['module']}")
        return _scaffold_view(attempt_id, attempt, {"question": question})
    hint = targeted_hint(attempt["module"], data.attempt_text, topic)
    attempt["step"] = "hint"
    store.log_event(data.learner_id, "Scaffold", "twin", "hint",
                    f"attempt_id={attempt_id} module={attempt['module']}")
    return _scaffold_view(attempt_id, attempt, {"hint": hint})


@app.post("/scaffold/show")
def post_scaffold_show(data: ScaffoldShowIn):
    """'Show me now': jump to the book excerpt, then one self-explanation ask."""
    attempt_id, attempt = _scaffold_attempt_or_raise(
        data.learner_id, data.attempt_id)
    if attempt["step"] in ("rewrite", "done"):
        return _scaffold_view(attempt_id, attempt)
    view = _serve_excerpt(data.learner_id, attempt_id, attempt, "show-me")
    view["self_explanation"] = SELF_EXPLANATION
    return view


@app.post("/scaffold/rewrite")
def post_scaffold_rewrite(data: ScaffoldRewriteIn):
    """Scaffold step (e): accept the learner's rewrite of the task."""
    if not (data.text or "").strip():
        raise HTTPException(status_code=400, detail="Rewrite text is empty")
    attempt_id, attempt = _scaffold_attempt_or_raise(
        data.learner_id, data.attempt_id)
    attempt["step"] = "done"
    words = len(data.text.split())
    store.log_event(data.learner_id, "Scaffold", "twin", "rewrite",
                    f"attempt_id={attempt_id} module={attempt['module']} words={words}")
    return _scaffold_view(attempt_id, attempt, {
        "message": "Saved. Read it once more against the pattern."})


@app.get("/practice")
def get_practice(learner_id: int):
    """Practise step: a short set for the weakest skill and level (no answers).

    Items use examples from the learner's discipline.
    """
    learner = store.get_learner(learner_id)
    if learner is None:
        raise HTTPException(status_code=404, detail="Unknown learner_id")
    discipline = learner.get("discipline") or "Sciences"
    skill, level = weakest_skill(latest_scores(learner_id))
    items = practice_items_for(skill, level, discipline)
    set_id = uuid.uuid4().hex[:8]
    ISSUED_SETS[set_id] = {"learner_id": learner_id, "skill": skill,
                           "level": level, "discipline": discipline,
                           "answers": {it["id"]: it["answer"] for it in items}}
    public = [{k: v for k, v in it.items() if k not in ("answer", "variants")}
              for it in items]
    store.log_event(learner_id, "Practise", "twin", "get_practice",
                    f"set_id={set_id} skill={skill} level={level} items={len(items)}")
    return {"set_id": set_id, "learner_id": learner_id, "skill": skill,
            "level": level, "discipline": discipline, "items": public}


@app.post("/practice/answers")
def post_answers(data: PracticeAnswersIn):
    """Score submitted answers; bump the skill when accuracy passes 80%."""
    issued = ISSUED_SETS.get(data.set_id)
    if issued is None or issued["learner_id"] != data.learner_id:
        raise HTTPException(status_code=404, detail="Unknown or foreign set_id")
    skill = issued["skill"]
    items = practice_items_for(skill, issued["level"], issued.get("discipline"))
    details: list[dict] = []
    correct = 0
    for item in items:
        ok = check_answer(item, data.answers.get(item["id"], ""))
        correct += ok
        details.append({"id": item["id"], "correct": ok,
                        "explanation": item["explanation"] if not ok else ""})
    total = len(items)
    accuracy = round(100 * correct / total) if total else 0
    leveled_up = False
    new_score: float | None = None
    if accuracy >= LEVEL_PASS_SCORE:  # did well -> raise the skill score
        current = latest_scores(data.learner_id).get(skill, 0)
        new_score = min(100, current + SKILL_BUMP)
        store.save_skill_scores(data.learner_id, {skill: new_score})
        leveled_up = level_for_score(new_score) > level_for_score(current)
    store.log_event(data.learner_id, "Practise", "twin", "score_answers",
                    f"set_id={data.set_id} {correct}/{total} leveled_up={leveled_up}")
    return {"correct": correct, "total": total, "accuracy": accuracy,
            "skill": skill, "new_score": new_score, "leveled_up": leveled_up,
            "details": details}


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
    """Current skill scores (plus history) for the growth chart."""
    if store.get_learner(learner_id) is None:
        raise HTTPException(status_code=404, detail="Unknown learner_id")
    scores = latest_scores(learner_id)
    history: dict[str, list[dict]] = {}
    for row in store.get_skill_scores(learner_id):
        history.setdefault(row["skill_name"], []).append(
            {"score": row["score"], "date": row["date"]})
    return {"learner_id": learner_id, "scores": scores, "history": history}


def independence(learner_id: int) -> dict:
    """Hint-use trend across scaffold attempts: fewer hints = more independent.

    Compares hint + "Show me now" uses in the most recent attempts against the
    same number of attempts just before (up to 5 each side).
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
        if row["tool"] in ("hint", "show-me"):
            helps[aid] += 1
    if len(order) < 2:
        return {"attempts": len(order), "recent_helps": sum(helps.values()),
                "previous_helps": 0, "trend": "new",
                "message": "Try a module task to start tracking."}
    k = min(5, max(1, len(order) // 2))
    recent, previous = order[-k:], order[-2 * k:-k]
    recent_helps = sum(helps[a] for a in recent)
    previous_helps = sum(helps[a] for a in previous)
    if recent_helps == 0 and previous_helps == 0:
        trend, message = "independent", \
            "Fully independent: no hints in your recent tries."
    elif recent_helps < previous_helps:
        trend = "improving"
        message = (f"Working more independently: {recent_helps} hints in your "
                   f"last {k} {'tries' if k > 1 else 'try'}, down from {previous_helps}.")
    elif recent_helps == previous_helps:
        trend, message = "steady", \
            f"Steady: {recent_helps} hints across your recent tries."
    else:
        trend, message = "more-help", \
            (f"{recent_helps} hints in your last {k} "
             f"{'tries' if k > 1 else 'try'}. Hints help you learn.")
    return {"attempts": len(order), "recent_helps": recent_helps,
            "previous_helps": previous_helps, "trend": trend, "message": message}


@app.get("/independence")
def get_independence(learner_id: int):
    """Hint-use trend for the My Growth independence card."""
    if store.get_learner(learner_id) is None:
        raise HTTPException(status_code=404, detail="Unknown learner_id")
    return {"learner_id": learner_id, **independence(learner_id)}


@app.post("/teacher/practice-sets")
def post_teacher_set(data: TeacherSetIn):
    """Generate a practice set from plain language; return it only if verified."""
    items = generate_practice_set(data.request)
    errors = verify_practice_set(items)
    if errors:
        return {"passed": False, "errors": errors, "items": []}
    return {"passed": True, "errors": [], "items": items}


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


def verify_twin_reply(reply: str) -> list[str]:
    """Checklist for twin replies. Return problems (empty = passed)."""
    errors: list[str] = []
    if not (reply or "").strip():
        return ["Reply is empty."]
    found = _has_generic_praise(reply)
    if found:
        errors.append(f"No generic praise: reply contains '{found}'.")
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
            f"I found {weakest.lower()} hard too.")


@app.get("/drafts")
def get_drafts(learner_id: int):
    """List a learner's previous drafts with feedback (for My Writing)."""
    if store.get_learner(learner_id) is None:
        raise HTTPException(status_code=404, detail="Unknown learner_id")
    return {"learner_id": learner_id, "drafts": store.get_drafts(learner_id)}


@app.post("/twin/ask")
def post_twin_ask(data: TwinAskIn):
    """Bridge step: short scaffolded twin reply (template until Muse Spark lands)."""
    if store.get_learner(data.learner_id) is None:
        raise HTTPException(status_code=404, detail="Unknown learner_id")
    weakest, _ = weakest_skill(latest_scores(data.learner_id))
    reply = twin_scaffold_reply(data.message, weakest)
    errors = verify_twin_reply(reply)
    if errors:  # never serve a reply that breaks the checklist
        store.log_event(data.learner_id, "Bridge", "twin", "verify-reply",
                        f"rejected reply: {errors}")
        reply = twin_safe_reply(data.message, weakest)
    store.log_event(data.learner_id, "Bridge", "twin", "scaffold-reply",
                    f"screen={data.screen} weakest={weakest}")
    return {"reply": reply, "weakest": weakest}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000)
