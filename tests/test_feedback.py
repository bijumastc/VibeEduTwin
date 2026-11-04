"""Feedback on Write refers to the learner's own text (levels only)."""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import learner_store as store  # noqa: E402
import main  # noqa: E402

EXAMPLE = "I like plants. plants give water and keep climate well"


@pytest.fixture
def tmp_db(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "DB_PATH", tmp_path / "feedback_learners.db")
    monkeypatch.setattr(main, "study_material", lambda skill, n_results=2: [])
    monkeypatch.setattr(main, "_query_guide_chunks",
                        lambda skill, n_results=1: ([], []))
    monkeypatch.setattr(main, "_model_api_key", lambda: None)  # template path
    return store


def _learner(tmp_db):
    return tmp_db.create_learner("T", "10", "English", "Malayalam",
                                 discipline="Sciences")


def _diagnose_ok(levels, evidence):
    return json.dumps({
        skill: {"level": levels.get(skill, 3),
                "reason": f"{skill} checked.",
                "evidence": evidence}
        for skill in main.SKILLS})


def _feedback_ok(text):
    first, _, _ = text.partition(". ")
    return json.dumps({
        "strength": {"quote": "keep climate well",
                     "line": "You name what plants do for us."},
        "problems": [
            {"quote": first,
             "wrong": "The line starts with a small letter.",
             "why": "Readers stop at small slips like this.",
             "fix": "Start the line with a capital letter."},
            {"quote": "keep climate well",
             "wrong": "No source is named.",
             "why": "Readers trust named sources.",
             "fix": "Say where you read this."}],
        "model": {"before": first + ".",
                  "after": "Plants give water and keep the air clean.",
                  "changed": "It starts with a capital letter."},
        "your_turn": "Fix your other lines the same way."})


# --- Template fallback (no key): quotes the learner, no rewrite ---------------
def test_template_feedback_quotes_learner_text(tmp_db):
    learner_id = _learner(tmp_db)
    res = main.post_diagnose(main.DiagnoseIn(learner_id=learner_id,
                                             content=EXAMPLE))
    assert res["weakest"] in main.SKILLS
    assert res["levels"] == {s: main.level_for_score(res["scores"][s])
                             for s in main.SKILLS}
    assert [d["skill"] for d in res["skills_details"]] == main.SKILLS
    for detail in res["skills_details"]:
        assert 1 <= detail["level"] <= 5
        assert detail["reason"].strip()
        assert detail["evidence"] in EXAMPLE
    card = res["feedback"]
    assert len(card["problems"]) == 2
    for problem in card["problems"]:
        assert problem["quote"] in EXAMPLE
        assert problem["wrong"].strip() and problem["why"].strip()
        assert problem["fix"].strip()
    quotes = [p["quote"] for p in card["problems"]]
    assert quotes[0] != quotes[1]  # two different sentences
    assert card["model"] is None  # template never rewrites
    assert card["your_turn"].strip()
    assert main.verify("feedback",
                       main._feedback_verify_payload(card, EXAMPLE))["pass"]


def test_fallback_caps_levels_and_shows_notice(tmp_db):
    learner_id = _learner(tmp_db)
    text = ("I like plants. Plants give water and keep climate well. "
            "Trees give shade to all.")
    assert max(main.diagnose_text(text).values()) >= 60  # cap must bite
    res = main.post_diagnose(main.DiagnoseIn(learner_id=learner_id,
                                             content=text))
    assert max(res["levels"].values()) <= 3
    assert res["notice"] == main.FALLBACK_NOTICE
    assert res["notice"] == \
        "Quick estimate - full feedback unavailable right now."


def test_short_paragraph_caps_fallback_at_level_two(tmp_db):
    learner_id = _learner(tmp_db)
    res = main.post_diagnose(main.DiagnoseIn(learner_id=learner_id,
                                             content=EXAMPLE))
    assert max(res["levels"].values()) <= 2
    assert res["notice"] == main.FALLBACK_NOTICE


def test_learn_card_connects_to_learner_sentence(tmp_db):
    learner_id = _learner(tmp_db)
    res = main.post_diagnose(main.DiagnoseIn(learner_id=learner_id,
                                             content=EXAMPLE))
    connect = res["learn"]["connect"]
    assert connect.startswith("Your sentence '")
    assert main._skill_evidence(res["weakest"], EXAMPLE) in connect


# --- Live Spark feedback -------------------------------------------------------
def test_spark_feedback_serves_one_model_rewrite(tmp_db, monkeypatch):
    text = EXAMPLE
    calls = []

    def fake_chat(messages, temperature=None):
        calls.append(messages)
        if "give feedback" in messages[0]["content"]:
            return _feedback_ok(text)
        return _diagnose_ok({"Grammar": 2}, "plants give water")

    monkeypatch.setattr(main, "_model_api_key", lambda: "K")
    monkeypatch.setattr(main, "_spark_chat", fake_chat)
    learner_id = _learner(tmp_db)
    res = main.post_diagnose(main.DiagnoseIn(learner_id=learner_id,
                                             content=text))
    assert len(calls) == 2  # diagnosis + feedback
    assert res["notice"] is None  # full Spark path: no estimate note
    card = res["feedback"]
    assert card["model"]["before"] in text
    assert card["model"]["after"] not in text
    assert len([s for s in card["model"]["after"].split(".")
                if s.strip()]) == 1
    logged = [r for r in store.get_events(learner_id)
              if r["tool"] == "diagnose-feedback-spark"]
    assert len(logged) == 1
    assert "Muse Spark" in logged[0]["result"]


def test_bad_feedback_retries_then_template(tmp_db, monkeypatch):
    text = EXAMPLE
    bad = json.dumps(json.loads(_feedback_ok(text)) | {"problems": [
        {"quote": "zebras drink lava", "wrong": "x", "why": "y",
         "fix": "z"},
        {"quote": "keep climate well", "wrong": "x", "why": "y",
         "fix": "z"}]})
    calls = []

    def fake_chat(messages, temperature=None):
        calls.append(messages)
        if "give feedback" in messages[0]["content"]:
            return bad
        return _diagnose_ok({}, "I like plants.")

    monkeypatch.setattr(main, "_model_api_key", lambda: "K")
    monkeypatch.setattr(main, "_spark_chat", fake_chat)
    learner_id = _learner(tmp_db)
    res = main.post_diagnose(main.DiagnoseIn(learner_id=learner_id,
                                             content=text))
    feedback_calls = [c for c in calls if "give feedback" in c[0]["content"]]
    assert len(feedback_calls) == 1 + main.SPARK_MAX_REGENS
    assert res["feedback"]["model"] is None  # template fallback
    rejected = [r for r in store.get_events(learner_id)
                if r["tool"] == "verify-feedback"]
    assert rejected and "quotes-in-text" in rejected[0]["result"]


def test_feedback_shape_rejects_two_sentence_after():
    data = json.loads(_feedback_ok(EXAMPLE))
    data["model"]["after"] = "Plants give water. They clean the air."
    assert main._validate_feedback_shape(data) is None


# --- Verifier rules ------------------------------------------------------------
def _payload(**over):
    base = {"text": EXAMPLE, "quotes": ["I like plants."],
            "fields": ["Start the line with a capital letter."],
            "before": "I like plants.", "after": "I like green plants."}
    base.update(over)
    return base


def test_feedback_verifier_rules():
    assert main.verify("feedback", _payload())["pass"] is True
    assert "quotes-in-text" in main.verify(
        "feedback", _payload(quotes=["zebras drink lava"]))["failed"]
    assert "one-rewrite" in main.verify(
        "feedback", _payload(after="One. Two."))["failed"]
    assert "one-rewrite" in main.verify(
        "feedback", _payload(after="I like plants."))["failed"]
    assert "no-generic-praise" in main.verify(
        "feedback", _payload(fields=["Great job on this line."]))["failed"]
    assert "simple-english" in main.verify(
        "feedback", _payload(
            fields=["We must facilitate better plant outcomes."]))["failed"]


def test_demo_fixed_cards_pass_verifier():
    assert main.verify(
        "feedback", main._feedback_verify_payload(
            main.DEMO_FEEDBACK_WEAK, main.DEMO_WEAK_PARAGRAPH))["pass"]
    assert main.verify(
        "feedback", main._feedback_verify_payload(
            main.DEMO_FEEDBACK_IMPROVED,
            main.DEMO_IMPROVED_PARAGRAPH))["pass"]


# --- Twin voice: future-self only ----------------------------------------------
def test_twin_note_is_future_self_without_shared_struggle():
    for skill in main.SKILLS:
        note = main.twin_note(skill)
        assert note.startswith("You will get this: start by "), note
        assert "hard too" not in note.lower()
        assert " I " not in f" {note} " and not note.startswith("I ")


# --- Growth stores reasons + levels --------------------------------------------
def test_growth_returns_levels_and_details(tmp_db):
    learner_id = _learner(tmp_db)
    main.post_diagnose(main.DiagnoseIn(learner_id=learner_id, content=EXAMPLE))
    growth = main.get_growth(learner_id)
    assert set(growth["levels"]) == set(main.SKILLS)
    assert all(1 <= lv <= 5 for lv in growth["levels"].values())
    for skill in main.SKILLS:
        assert growth["details"][skill]["evidence"] in EXAMPLE


def test_practice_result_carries_level(tmp_db):
    learner_id = _learner(tmp_db)
    set_id = f"practice-level-{len(main.ISSUED_SETS)}"
    item = {"id": "a1", "type": "mcq", "prompt": "Which names the topic?",
            "options": ["A) Rivers run fast.", "B) I like rain."],
            "answer": "A", "explanation": "A names it.", "source": "b.pdf"}
    main.ISSUED_SETS[set_id] = {
        "learner_id": learner_id, "skill": "Paragraphing", "level": 1,
        "discipline": "Sciences", "published": False, "items": [item],
        "answers": {"a1": "A"}}
    res = main.post_answers(main.PracticeAnswersIn(
        learner_id=learner_id, set_id=set_id, answers={"a1": "A"}))
    assert 1 <= res["level"] <= 5


# --- Levels-only UI strings ------------------------------------------------------
def _src(*parts):
    return (ROOT / "frontend" / "src" / Path(*parts)).read_text(encoding="utf-8")


def test_skill_bars_show_levels_reasons_evidence():
    bars = _src("components", "SkillBars.jsx")
    assert "of 5" in bars and "Level" in bars
    assert "/100" not in bars and "Math.round(scores" not in bars
    assert "reason" in bars and "evidence" in bars


def test_feedback_card_shape_and_single_emoji():
    card = _src("components", "FeedbackCard.jsx")
    for needle in ("Feedback on your paragraph", "What works",
                   "Let me show you one", "Before:", "After:",
                   "Rewrite my paragraph"):
        assert needle in card
    assert card.count("✏️") == 1
    for other in ("🚀", "⚡", "✨", "🎯", "💡", "❤️", "👍", "🌟", "📚"):
        assert other not in card
    write = _src("screens", "Write.jsx")
    assert "FeedbackCard" in write and "feedback={result.feedback}" in write


def test_learn_card_read_more_and_connect():
    lesson = _src("components", "CompactLesson.jsx")
    assert "Read more from the book" in lesson
    assert "connect" in lesson
    write = _src("screens", "Write.jsx")
    assert "connect={result.learn.connect}" in write


def test_write_shows_fallback_notice():
    write = _src("screens", "Write.jsx")
    assert "result.notice" in write


def test_no_hundred_point_scores_on_screen():
    for path in (("screens", "Home.jsx"), ("screens", "MyGrowth.jsx"),
                 ("screens", "Practice.jsx"), ("screens", "Write.jsx"),
                 ("components", "SkillBars.jsx")):
        text = _src(*path)
        assert "/100" not in text, path
        assert "accuracy}%" not in text, path
    assert "of 5" in _src("screens", "Home.jsx")
    assert "of 5" in _src("screens", "MyGrowth.jsx")
    assert "Level {result.level} of 5" in _src("screens", "Practice.jsx")
