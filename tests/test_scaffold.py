"""Productive-struggle ladder: try -> question -> hint -> excerpt -> rewrite."""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import learner_store as store  # noqa: E402
import main  # noqa: E402
from fastapi import HTTPException  # noqa: E402


@pytest.fixture
def tmp_db(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "DB_PATH", tmp_path / "scaffold_learners.db")
    return store


def _learner(tmp_db, scores=None):
    learner_id = tmp_db.create_learner("Test", "10", "English", "Malayalam",
                                       discipline="Sciences")
    if scores:
        tmp_db.save_skill_scores(learner_id, scores)
    return learner_id


def _start(learner_id, module="topic-sentences"):
    return main.post_scaffold_start(main.ScaffoldStartIn(
        learner_id=learner_id, discipline="Sciences", module=module))


def _help(learner_id, attempt_id, text=""):
    return main.post_scaffold_help(main.ScaffoldHelpIn(
        learner_id=learner_id, attempt_id=attempt_id, attempt_text=text))


def _hit():
    return (["First. Second. Third. Fourth."],
            [{"source": "guide.pdf", "chapter": "Chapter 2", "license": "CC BY"}])


def test_level_bands_are_five():
    assert [(s, main.level_for_score(s)) for s in (0, 19, 20, 39, 40, 59, 60, 79, 80, 100)] == [
        (0, 1), (19, 1), (20, 2), (39, 2), (40, 3),
        (59, 3), (60, 4), (79, 4), (80, 5), (100, 5)]


def test_start_hands_out_task_with_no_help(tmp_db):
    view = _start(_learner(tmp_db))
    assert view["step"] == "try" and view["level"] == 1
    assert "evaporation" in view["task"]
    assert "question" not in view and "hint" not in view
    with pytest.raises(HTTPException) as exc:
        _start(999)
    assert exc.value.status_code == 404


def test_start_rejects_bad_or_locked_module(tmp_db):
    learner_id = _learner(tmp_db)
    with pytest.raises(HTTPException) as bad_disc:
        main.post_scaffold_start(main.ScaffoldStartIn(
            learner_id=learner_id, discipline="Cooking", module="topic-sentences"))
    assert bad_disc.value.status_code == 400
    with pytest.raises(HTTPException) as bad_mod:
        main.post_scaffold_start(main.ScaffoldStartIn(
            learner_id=learner_id, discipline="Sciences", module="spelling"))
    assert bad_mod.value.status_code == 404
    with pytest.raises(HTTPException) as locked:
        _start(learner_id, "thesis-statements")
    assert locked.value.status_code == 403


def test_level1_gets_hint_immediately(tmp_db):
    learner_id = _learner(tmp_db)
    attempt = _start(learner_id)["attempt_id"]
    helped = _help(learner_id, attempt)
    assert helped["step"] == "hint" and helped["hint"].strip()


def test_level2_gets_one_question_then_hint(tmp_db):
    learner_id = _learner(tmp_db, {"Paragraphing": 25})
    attempt = _start(learner_id)["attempt_id"]
    assert _help(learner_id, attempt)["step"] == "question"
    assert _help(learner_id, attempt)["step"] == "hint"


def test_level3_gets_two_questions_then_hint(tmp_db):
    learner_id = _learner(tmp_db, {"Paragraphing": 50})
    attempt = _start(learner_id)["attempt_id"]
    first = _help(learner_id, attempt)
    second = _help(learner_id, attempt)
    assert first["step"] == second["step"] == "question"
    assert first["question"] != second["question"]
    assert _help(learner_id, attempt)["step"] == "hint"


@pytest.mark.parametrize("score", [70, 90])
def test_levels4_and_5_get_only_questions(tmp_db, score):
    learner_id = _learner(tmp_db, {"Paragraphing": score})
    attempt = _start(learner_id)["attempt_id"]
    for _ in range(4):
        assert _help(learner_id, attempt)["step"] == "question"


def test_ladder_reaches_excerpt_then_rewrite(tmp_db, monkeypatch):
    monkeypatch.setattr(main, "_query_guides", lambda query, n_results=3: _hit())
    learner_id = _learner(tmp_db, {"Paragraphing": 50})
    attempt = _start(learner_id)["attempt_id"]
    _help(learner_id, attempt)
    _help(learner_id, attempt)
    assert _help(learner_id, attempt)["step"] == "hint"
    shown = _help(learner_id, attempt)
    assert shown["step"] == "excerpt"
    assert shown["excerpt"]["source"] == "guide.pdf"
    assert shown["excerpt"]["chapter"] == "Chapter 2"
    rewritten = _help(learner_id, attempt)
    assert rewritten["step"] == "rewrite" and "pattern" in rewritten["prompt"]
    done = main.post_scaffold_rewrite(main.ScaffoldRewriteIn(
        learner_id=learner_id, attempt_id=attempt, text="Evaporation speeds up in wind."))
    assert done["step"] == "done" and "Saved" in done["message"]
    with pytest.raises(HTTPException) as exc:
        main.post_scaffold_rewrite(main.ScaffoldRewriteIn(
            learner_id=learner_id, attempt_id=attempt, text="  "))
    assert exc.value.status_code == 400


def test_excerpt_falls_back_to_no_verified(tmp_db, monkeypatch):
    monkeypatch.setattr(main, "_query_guides", lambda query, n_results=3: ([], []))
    learner_id = _learner(tmp_db)
    attempt = _start(learner_id)["attempt_id"]
    _help(learner_id, attempt)  # hint
    shown = _help(learner_id, attempt)  # excerpt
    assert shown["excerpt"]["text"] == main.NO_VERIFIED_EXAMPLE
    assert shown["excerpt"]["source"] is None


def test_show_me_jumps_to_excerpt(tmp_db, monkeypatch):
    monkeypatch.setattr(main, "_query_guides", lambda query, n_results=3: _hit())
    learner_id = _learner(tmp_db)
    attempt = _start(learner_id)["attempt_id"]
    shown = main.post_scaffold_show(main.ScaffoldShowIn(
        learner_id=learner_id, attempt_id=attempt))
    assert shown["step"] == "excerpt"
    assert shown["excerpt"]["source"] == "guide.pdf"
    assert shown["self_explanation"] == "In one line, why does this example work?"


def test_foreign_attempt_rejected(tmp_db):
    first = _learner(tmp_db)
    second = _learner(tmp_db)
    attempt = _start(first)["attempt_id"]
    with pytest.raises(HTTPException) as exc:
        _help(second, attempt)
    assert exc.value.status_code == 404


def test_targeted_hint_spots_weakness():
    assert "According to" in main.targeted_hint(
        "using-sources", "plants need sun", "evaporation")
    assert "own words" in main.targeted_hint(
        "using-sources", "According to the book, plants need sun", "evaporation")
    assert "ONE sentence" in main.targeted_hint("topic-sentences", "", "evaporation")


def test_twin_never_writes_the_answer():
    for module_id, questions in main.SCAFFOLD_QUESTIONS.items():
        assert len(questions) == 2
        for question in questions:
            assert question.format(genre="lab report").endswith("?"), question
            assert main.verify_twin_reply(question.format(genre="x")) == []
    for module_id in main.SCAFFOLD_TASKS:
        assert main.scaffold_task("Sciences", module_id).startswith("Write")
    attempts = ["", " Plants need sun. It is hot. Yes indeed.", "According to me it rains."]
    for module_id in main.SCAFFOLD_TASKS:
        for text in attempts:
            hint = main.targeted_hint(module_id, text, "evaporation")
            assert hint and main.verify_twin_reply(hint) == [], (module_id, text)


def test_independence_improving(tmp_db):
    learner_id = _learner(tmp_db)
    first = _start(learner_id)["attempt_id"]
    _help(learner_id, first)  # hint
    main.post_scaffold_show(main.ScaffoldShowIn(
        learner_id=learner_id, attempt_id=first))  # show-me
    second = _start(learner_id)["attempt_id"]
    _help(learner_id, second)  # hint
    _start(learner_id)  # no help
    res = main.get_independence(learner_id)
    assert res["attempts"] == 3
    assert (res["recent_helps"], res["previous_helps"]) == (0, 1)
    assert res["trend"] == "improving"
    assert "Working more independently" in res["message"]


def test_independence_new_and_steady(tmp_db):
    fresh = _learner(tmp_db)
    assert main.get_independence(fresh)["trend"] == "new"
    steady = _learner(tmp_db)
    for _ in range(2):
        attempt = _start(steady)["attempt_id"]
        _help(steady, attempt)
    assert main.get_independence(steady)["trend"] == "steady"
    with pytest.raises(HTTPException) as exc:
        main.get_independence(999)
    assert exc.value.status_code == 404


def test_scaffold_ui_strings():
    task = (ROOT / "frontend" / "src" / "components" / "ScaffoldTask.jsx").read_text(
        encoding="utf-8")
    assert "Show me now" in task
    learn = (ROOT / "frontend" / "src" / "screens" / "Learn.jsx").read_text(encoding="utf-8")
    assert "Try the task" in learn
    growth = (ROOT / "frontend" / "src" / "screens" / "MyGrowth.jsx").read_text(
        encoding="utf-8")
    assert "Working more independently" in growth
    assert "api.independence()" in growth
