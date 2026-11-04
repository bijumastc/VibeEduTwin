"""Practice Assessor: rubric feedback, 0-2 scoring and study routing."""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import learner_store as store  # noqa: E402
import main  # noqa: E402

MCQ = {"id": "a1", "type": "mcq", "prompt": "Which sentence names the topic?",
       "options": ["A) Rivers run fast.", "B) I like rain.", "C) Rain is wet."],
       "answer": "A", "explanation": "A names it.", "source": "b.pdf"}
MCQ2 = {"id": "a3", "type": "mcq", "prompt": "Which sentence proves a point?",
        "options": ["A) Fish swim deep.", "B) Boats float high.",
                    "C) Water is blue."],
        "answer": "B", "explanation": "B proves it.", "source": "b.pdf"}
ORDER = {"id": "a2", "type": "order",
         "prompt": "Put the paragraph in order. Sentences: 1) 'Rivers run "
                   "fast.' 2) 'Fish swim deep.' 3) 'Boats float high.'",
         "options": ["1,2,3", "3,2,1"], "answer": "1,2,3",
         "explanation": "River order.", "source": "b.pdf"}


@pytest.fixture
def tmp_db(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "DB_PATH", tmp_path / "practice_learners.db")
    return store


def _learner(tmp_db):
    return tmp_db.create_learner("Test", "10", "English", "Malayalam",
                                 discipline="Sciences")


def _issue(learner_id, items, skill="Paragraphing", tag="t"):
    set_id = f"practice-{tag}-{len(main.ISSUED_SETS)}"
    main.ISSUED_SETS[set_id] = {
        "learner_id": learner_id, "skill": skill, "level": 1,
        "discipline": "Sciences", "published": False, "items": items,
        "answers": {it["id"]: it["answer"] for it in items}}
    return set_id


def _score(learner_id, set_id, answers):
    return main.post_answers(main.PracticeAnswersIn(
        learner_id=learner_id, set_id=set_id, answers=answers))


def test_correct_answers_scored_without_level_move(tmp_db, monkeypatch):
    monkeypatch.setattr(main, "_model_api_key", lambda: None)
    learner_id = _learner(tmp_db)
    set_id = _issue(learner_id, [MCQ, ORDER])
    scored = _score(learner_id, set_id, {"a1": "A", "a2": "1,2,3"})
    assert scored["accuracy"] == 100
    by_id = {d["id"]: d for d in scored["details"]}
    assert by_id["a1"]["assessment"]["score"] == 2
    assert "Rivers run fast." in by_id["a1"]["assessment"]["feedback"]
    assert "Fish swim deep." in by_id["a2"]["assessment"]["feedback"]
    assert scored["new_score"] is None  # one set cannot move mastery
    assert scored["mastery"] == {"Paragraphing": False}
    assert store.get_skill_scores(learner_id) == []
    rows = [r for r in store.get_events(learner_id) if r["tool"] == "assess"]
    assert len(rows) == 1 and "assessed 2 answers" in rows[0]["result"]


def test_wrong_answer_quotes_choice_and_suggests_study(tmp_db, monkeypatch):
    monkeypatch.setattr(main, "_model_api_key", lambda: None)
    learner_id = _learner(tmp_db)
    set_id = _issue(learner_id, [MCQ, MCQ2, ORDER])
    scored = _score(learner_id, set_id,
                    {"a1": "B", "a3": "A", "a2": "3,2,1"})
    by_id = {d["id"]: d for d in scored["details"]}
    assert by_id["a1"]["correct"] is False
    assert by_id["a1"]["explanation"] == "A names it."
    assert "I like rain." in by_id["a1"]["assessment"]["feedback"]
    assert by_id["a1"]["assessment"]["score"] == 0
    assert by_id["a1"]["assessment"]["next_step"] == "next"
    assert by_id["a3"]["assessment"]["next_step"] == "next"
    assert by_id["a2"]["assessment"]["next_step"] == "study"
    assert by_id["a2"]["assessment"]["module"] == "topic-sentences"
    assert scored["new_score"] is None  # nothing earned, nothing saved


def test_spark_batch_judges_whole_set_once(tmp_db, monkeypatch):
    import json

    calls = []
    monkeypatch.setattr(main, "_model_api_key", lambda: "K")

    def fake_chat(messages):
        calls.append(messages)
        return json.dumps([
            {"id": "a1", "status": "ok",
             "strength": "You spotted it: \"Rivers run fast.\".",
             "problem": "", "quote": "Rivers run fast.",
             "next_action": "Keep going.", "score": 2},
            {"id": "a2", "status": "ok", "strength": "",
             "problem": "Your order breaks the flow: \"Boats float high. Fish swim deep.\"",
             "quote": "Boats float high. Fish swim deep.",
             "next_action": "Start from the river, not the boats.", "score": 1}])

    monkeypatch.setattr(main, "_spark_chat", fake_chat)
    learner_id = _learner(tmp_db)
    set_id = _issue(learner_id, [MCQ, ORDER])
    scored = _score(learner_id, set_id, {"a1": "A", "a2": "3,2,1"})
    assert len(calls) == 1
    assert "Names the paragraph topic" in calls[0][-1]["content"]
    assert "Rivers run fast." in calls[0][-1]["content"]
    by_id = {d["id"]: d for d in scored["details"]}
    assert "You spotted it:" in by_id["a1"]["assessment"]["feedback"]
    assert "Start from the river" in by_id["a2"]["assessment"]["feedback"]
    assert (by_id["a1"]["assessment"]["score"],
            by_id["a2"]["assessment"]["score"]) == (2, 1)
    assert scored["new_score"] is None


def test_spark_garbage_falls_back_to_template(tmp_db, monkeypatch):
    monkeypatch.setattr(main, "_model_api_key", lambda: "K")
    monkeypatch.setattr(main, "_spark_chat", lambda messages: "nope")
    learner_id = _learner(tmp_db)
    set_id = _issue(learner_id, [MCQ])
    scored = _score(learner_id, set_id, {"a1": "A"})
    got = scored["details"][0]["assessment"]
    assert got["score"] == 2 and "Rivers run fast." in got["feedback"]


def test_blank_answer_scores_zero(tmp_db, monkeypatch):
    monkeypatch.setattr(main, "_model_api_key", lambda: None)
    learner_id = _learner(tmp_db)
    set_id = _issue(learner_id, [MCQ])
    scored = _score(learner_id, set_id, {})
    got = scored["details"][0]["assessment"]
    assert got["score"] == 0
    assert "no answer" in got["feedback"]
    assert scored["new_score"] is None


def test_skill_without_module_skips_spark(tmp_db, monkeypatch):
    def boom(messages):
        raise AssertionError("Grammar has no rubric; Spark must not run")

    monkeypatch.setattr(main, "_model_api_key", lambda: "K")
    monkeypatch.setattr(main, "_spark_chat", boom)
    learner_id = _learner(tmp_db)
    set_id = _issue(learner_id, [MCQ, MCQ2, ORDER], skill="Grammar")
    scored = _score(learner_id, set_id,
                    {"a1": "B", "a3": "A", "a2": "3,2,1"})
    steps = [d["assessment"]["next_step"] for d in scored["details"]]
    assert steps == ["next", "next", "next"]  # nowhere to study
    assert all(d["assessment"]["score"] == 0 for d in scored["details"])


def test_practice_assessment_ui_strings():
    practice = (ROOT / "frontend" / "src" / "screens" / "Practice.jsx").read_text(
        encoding="utf-8")
    assert "assessment" in practice
    assert "Study this in Learn" in practice
    assert "go('learn')" in practice
    app = (ROOT / "frontend" / "src" / "App.jsx").read_text(encoding="utf-8")
    assert "<Practice go={go} />" in app


# --- Retry bounds: regen resends only failed items, then templates -------------
def test_practice_batch_retries_only_failed_items(tmp_db, monkeypatch):
    import json

    replies = [
        json.dumps([{"id": "a1", "status": "ok",
                     "strength": "You spotted it: \"Rivers run fast.\".",
                     "problem": "", "quote": "Rivers run fast.",
                     "next_action": "Keep going.", "score": 2}]),
        json.dumps([{"id": "a2", "status": "ok", "strength": "",
                     "problem": "Your order breaks the flow: "
                                "\"Boats float high. Fish swim deep.\"",
                     "quote": "Boats float high. Fish swim deep.",
                     "next_action": "Start from the river.", "score": 1}])]
    calls = []

    def chat(messages):
        calls.append(messages)
        return replies[len(calls) - 1]

    monkeypatch.setattr(main, "_model_api_key", lambda: "K")
    monkeypatch.setattr(main, "_spark_chat", chat)
    learner_id = _learner(tmp_db)
    set_id = _issue(learner_id, [MCQ, ORDER])
    scored = _score(learner_id, set_id, {"a1": "A", "a2": "3,2,1"})
    assert len(calls) == 2
    retry_text = calls[1][-1]["content"]
    assert "id a2" in retry_text and "id a1" not in retry_text
    by_id = {d["id"]: d for d in scored["details"]}
    assert "You spotted it:" in by_id["a1"]["assessment"]["feedback"]
    assert "Start from the river" in by_id["a2"]["assessment"]["feedback"]


def test_practice_batch_exhausts_regens_then_templates(tmp_db, monkeypatch):
    calls = []

    def bad_chat(messages):
        calls.append(messages)
        return "nope"

    monkeypatch.setattr(main, "_model_api_key", lambda: "K")
    monkeypatch.setattr(main, "_spark_chat", bad_chat)
    learner_id = _learner(tmp_db)
    set_id = _issue(learner_id, [MCQ])
    scored = _score(learner_id, set_id, {"a1": "A"})
    assert len(calls) == 3  # 1 initial + 2 regens
    got = scored["details"][0]["assessment"]
    assert got["score"] == 2 and "Rivers run fast." in got["feedback"]
