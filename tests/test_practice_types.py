"""Practice sets: 4 item types, mastery moves, mixed review."""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import learner_store as store  # noqa: E402
import main  # noqa: E402


@pytest.fixture
def tmp_db(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "DB_PATH", tmp_path / "types_learners.db")
    return store


def _learner(tmp_db, scores=None, discipline="Sciences"):
    learner_id = tmp_db.create_learner("Test", "10", "English", "Malayalam",
                                       discipline=discipline)
    if scores:
        tmp_db.save_skill_scores(learner_id, scores)
    return learner_id


def _rich_query(query, n_results=6):
    docs = [f"Alpha point {i} names the topic first. A thesis takes a clear "
            f"position and argues it well. Details follow and support it."
            for i in range(n_results)]
    metas = [{"source": f"book{i}.pdf", "chapter": f"Ch {i + 1}",
              "license": "CC BY"} for i in range(n_results)]
    return docs, metas


def _para_weak(scores_value=10):
    return {s: 50 for s in main.SKILLS} | {"Paragraphing": scores_value}


def test_generated_set_has_four_types(tmp_db, monkeypatch):
    monkeypatch.setattr(main, "_query_guides", _rich_query)
    monkeypatch.setattr(main, "_model_api_key", lambda: None)
    learner_id = _learner(tmp_db, _para_weak())
    body = main.get_practice(learner_id)
    assert body["published"] is False and body["review"] is False
    kinds = [it.get("kind", it["type"]) for it in body["items"]]
    assert kinds == ["recognise", "recognise", "repair", "produce", "produce",
                     "apply"]
    assert all(it["module"] == "topic-sentences" for it in body["items"])
    first = body["items"][0]
    assert first["type"] == "mcq" and len(first["options"]) == 3
    assert main.verify("practice_item", main.ISSUED_SETS[body["set_id"]][
        "items"][0])["pass"] is True
    assert "evaporation" in body["items"][3]["prompt"]
    assert body["items"][5]["type"] == "write"


def test_recognise_level4_has_four_options(tmp_db, monkeypatch):
    monkeypatch.setattr(main, "_query_guides", _rich_query)
    monkeypatch.setattr(main, "_model_api_key", lambda: None)
    scores = {s: 90 for s in main.SKILLS} | {"Paragraphing": 65}
    body = main.get_practice(_learner(tmp_db, scores))
    assert body["level"] == 4
    assert len(body["items"][0]["options"]) == 4


def test_write_answers_assessed_without_level_move(tmp_db, monkeypatch):
    monkeypatch.setattr(main, "_query_guides", _rich_query)
    monkeypatch.setattr(main, "_model_api_key", lambda: None)
    learner_id = _learner(tmp_db, _para_weak())
    body = main.get_practice(learner_id)
    issued = main.ISSUED_SETS[body["set_id"]]
    answers = {}
    for it in issued["items"]:
        if it["type"] == "write":
            answers[it["id"]] = ("Evaporation rises fast on hot windy days "
                                 "over the lake.")
        else:
            answers[it["id"]] = it["answer"]
    scored = main.post_answers(main.PracticeAnswersIn(
        learner_id=learner_id, set_id=body["set_id"], answers=answers))
    assert scored["accuracy"] == 100
    for detail in scored["details"]:
        assert detail["assessment"]["score"] == 2
    assert "Evaporation rises fast" in scored["details"][3]["assessment"][
        "feedback"]
    assert scored["new_score"] is None  # one set cannot move mastery
    assert scored["mastery"] == {"Paragraphing": False}
    assert len(store.get_skill_scores(learner_id)) == 7  # nothing saved yet


def test_mastery_moves_up_after_two_strong_sets(tmp_db, monkeypatch):
    monkeypatch.setattr(main, "_query_guides", _rich_query)
    monkeypatch.setattr(main, "_model_api_key", lambda: None)
    learner_id = _learner(tmp_db, _para_weak(35))
    store.save_practice_result(learner_id, "Paragraphing", 85)
    body = main.get_practice(learner_id)
    issued = main.ISSUED_SETS[body["set_id"]]
    answers = {}
    for it in issued["items"]:
        answers[it["id"]] = it["answer"] if it["type"] != "write" else (
            "Evaporation rises fast on hot windy days over the lake.")
    scored = main.post_answers(main.PracticeAnswersIn(
        learner_id=learner_id, set_id=body["set_id"], answers=answers))
    assert scored["accuracy"] == 100
    assert scored["mastery"] == {"Paragraphing": True}
    assert scored["new_score"] == 40
    assert scored["leveled_up"] is True


def test_review_set_mixes_earlier_modules(tmp_db, monkeypatch):
    monkeypatch.setattr(main, "_query_guides", _rich_query)
    monkeypatch.setattr(main, "_model_api_key", lambda: None)
    scores = {"Paragraphing": 50, "Argument": 50}
    learner_id = _learner(tmp_db, scores)
    first = main.get_practice(learner_id)
    assert first["review"] is False
    assert main.get_practice(learner_id)["review"] is False
    review = main.get_practice(learner_id)
    assert review["review"] is True
    assert len(review["items"]) == 6
    modules = {it.get("module") for it in review["items"]
               if it.get("kind") == "recognise"}
    # Weakest skill is Grammar (unscored): review mixes the three modules
    # before the recommended mechanics module.
    assert modules <= {"developing-paragraphs", "coherence-flow",
                       "using-sources"}
    assert len(modules) >= 2


def test_teacher_sets_assessed_here(tmp_db, monkeypatch):
    monkeypatch.setattr(main, "_model_api_key", lambda: None)
    learner_id = _learner(tmp_db)
    store.save_teacher_set("Paragraphing", 1, "Sciences", [
        {"id": "t1", "type": "mcq", "prompt": "Which names the topic?",
         "options": ["A) Rivers run fast.", "B) I like rain."],
         "answer": "A", "explanation": "A names it.", "source": "b.pdf"},
        {"id": "t2", "type": "mcq", "prompt": "Which proves a point?",
         "options": ["A) Fish swim deep.", "B) Boats float high."],
         "answer": "B", "explanation": "B proves it.", "source": "b.pdf"}],
        "r")
    body = main.get_practice(learner_id)
    assert body["published"] is True
    scored = main.post_answers(main.PracticeAnswersIn(
        learner_id=learner_id, set_id=body["set_id"],
        answers={"t1": "A", "t2": "B"}))
    assert scored["accuracy"] == 100
    assert all(d["assessment"]["score"] == 2 for d in scored["details"])


def test_write_ui_strings():
    practice = (ROOT / "frontend" / "src" / "screens" / "Practice.jsx").read_text(
        encoding="utf-8")
    assert "textarea" in practice
    assert "Save & continue" in practice
    assert "Review set" in practice
