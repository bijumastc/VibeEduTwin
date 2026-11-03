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


def _steps(learner_id, attempt_id):
    return main.post_scaffold_steps(main.ScaffoldStepsIn(
        learner_id=learner_id, attempt_id=attempt_id))


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


def test_steps_serve_sequential_worked_answer(tmp_db):
    learner_id = _learner(tmp_db)
    attempt = _start(learner_id)["attempt_id"]
    served = _steps(learner_id, attempt)
    assert served["step"] == "steps"
    assert len(served["steps"]) == 4
    for step, marker in zip(served["steps"], ("First", "Next", "Then", "Finally")):
        assert step.startswith(marker), step
    assert "evaporation" in " ".join(served["steps"])
    rewritten = _help(learner_id, attempt)
    assert rewritten["step"] == "rewrite" and "steps" in rewritten["prompt"]
    done = main.post_scaffold_rewrite(main.ScaffoldRewriteIn(
        learner_id=learner_id, attempt_id=attempt, text="Everyone cares about evaporation."))
    assert done["step"] == "done"


def test_second_show_me_escalates_to_steps(tmp_db, monkeypatch):
    monkeypatch.setattr(main, "_query_guides", lambda query, n_results=3: _hit())
    learner_id = _learner(tmp_db)
    attempt = _start(learner_id)["attempt_id"]
    first = main.post_scaffold_show(main.ScaffoldShowIn(
        learner_id=learner_id, attempt_id=attempt))
    assert first["step"] == "excerpt"
    second = main.post_scaffold_show(main.ScaffoldShowIn(
        learner_id=learner_id, attempt_id=attempt))
    assert second["step"] == "steps"
    assert len(second["steps"]) == 4


def test_steps_open_at_any_level(tmp_db):
    learner_id = _learner(tmp_db, {"Paragraphing": 90})
    attempt = _start(learner_id)["attempt_id"]
    assert _steps(learner_id, attempt)["step"] == "steps"
    with pytest.raises(HTTPException) as exc:
        _steps(learner_id, "no-such-attempt")
    assert exc.value.status_code == 404


def test_worked_steps_are_short_simple_sequential():
    import re
    for module_id in main.SCAFFOLD_TASKS:
        for discipline in store.DISCIPLINES:
            steps = main.worked_steps(module_id, discipline)
            assert len(steps) == 4, (module_id, discipline)
            for step, marker in zip(steps, ("First", "Next", "Then", "Finally")):
                assert step.startswith(marker), (module_id, step)
                assert len(step.split()) <= 30, (module_id, step)
                assert step.isascii(), (module_id, step)
                assert not re.search(r"\d", step), (module_id, step)
                assert main.verify_twin_reply(step) == [], (module_id, step)
            assert main.DISCIPLINE_TOPICS[discipline] in steps[0], (module_id, steps[0])
            assert "check" in steps[-1].lower(), (module_id, steps[-1])
            assert "model" in steps[-1].lower(), (module_id, steps[-1])


def test_worked_models_show_controlling_idea():
    for module_id in main.SCAFFOLD_TASKS:
        seen = set()
        for discipline in store.DISCIPLINES:
            model = main.worked_model(module_id, discipline)
            verdict = main.verify("worked_model", {
                "module": module_id, "model": model,
                "task_topic": main.DISCIPLINE_TOPICS[discipline]})
            assert verdict == {"pass": True, "failed": [], "fix": ""}, \
                (module_id, discipline, model)
            seen.add(model)
        assert len(seen) == 6, module_id  # each discipline its own point
    assert main.worked_model("topic-sentences", "Sciences") == \
        ("Friction explains why cycling uphill feels harder than cycling "
         "on flat ground.")


def test_models_share_no_task_topic_word():
    import re
    for (module_id, discipline), model in main.WORKED_MODELS.items():
        task_words = (set(re.findall(
            r"[a-z]+", main.DISCIPLINE_TOPICS[discipline].lower()))
            - main._STOPWORDS)
        model_words = set(re.findall(
            r"[a-z]+", model.format(genre="report").lower()))
        assert not (task_words & model_words), (module_id, discipline, model)


def test_worked_model_verifier_rejects_weak():
    weak = "Everyone cares about evaporation."
    verdict = main.verify("worked_model", {"module": "topic-sentences",
                                           "model": weak,
                                           "task_topic": "evaporation"})
    assert verdict["pass"] is False
    assert verdict["failed"] == ["has-controlling-idea", "not-task-topic"]
    assert verdict["fix"]
    vague = "I believe evaporation must get more care."
    verdict = main.verify("worked_model", {"module": "thesis-statements",
                                           "model": vague,
                                           "task_topic": "evaporation"})
    assert verdict["pass"] is False
    assert verdict["failed"] == ["has-controlling-idea", "not-task-topic"]
    same_topic = ("Evaporation explains why wet clothes dry faster "
                  "on a windy day.")
    verdict = main.verify("worked_model", {"module": "topic-sentences",
                                           "model": same_topic,
                                           "task_topic": "evaporation"})
    assert verdict["pass"] is False
    assert verdict["failed"] == ["not-task-topic"]


def test_steps_payload_carries_rule_and_model(tmp_db, monkeypatch):
    doc = "A topic sentence names the topic and the controlling idea first."
    meta = {"source": "guide.pdf", "chapter": "Ch 1", "license": "CC BY"}
    monkeypatch.setattr(main, "_query_guides",
                        lambda query, n_results=8: ([doc], [meta]))
    learner_id = _learner(tmp_db)
    attempt = _start(learner_id)["attempt_id"]
    served = _steps(learner_id, attempt)
    assert served["step"] == "steps"
    assert served["rule"]["source"] == "guide.pdf"
    assert "controlling idea" in served["rule"]["text"]
    assert served["model"] == main.worked_model("topic-sentences", "Sciences")


def test_steps_omit_failing_model(tmp_db, monkeypatch):
    monkeypatch.setattr(main, "_query_guides",
                        lambda query, n_results=8: ([], []))
    monkeypatch.setitem(main.WORKED_MODELS, ("topic-sentences", "Sciences"),
                        "Everyone cares about evaporation.")
    learner_id = _learner(tmp_db)
    attempt = _start(learner_id)["attempt_id"]
    served = _steps(learner_id, attempt)
    assert served["step"] == "steps"
    assert "model" not in served
    assert served["rule"]["text"] == main.NO_VERIFIED_EXAMPLE
    tools = [row["tool"] for row in store.get_scaffold_events(learner_id)]
    assert "verify-steps" in tools


def test_steps_count_as_help_in_independence(tmp_db):
    learner_id = _learner(tmp_db)
    first = _start(learner_id)["attempt_id"]
    _steps(learner_id, first)
    _start(learner_id)  # no help
    res = main.get_independence(learner_id)
    assert res["attempts"] == 2
    assert (res["recent_helps"], res["previous_helps"]) == (0, 1)
    assert res["trend"] == "improving"


def test_steps_ui_strings():
    task = (ROOT / "frontend" / "src" / "components" / "ScaffoldTask.jsx").read_text(
        encoding="utf-8")
    assert "Just show me the steps" in task
    assert "scaffoldSteps" in task and "<ol>" in task
    assert "Write my version" in task
    assert "Study this model" in task
    assert "The rule from the books" in task
    api = (ROOT / "frontend" / "src" / "api.js").read_text(encoding="utf-8")
    assert "scaffoldSteps" in api


def test_scaffold_ui_strings():
    task = (ROOT / "frontend" / "src" / "components" / "ScaffoldTask.jsx").read_text(
        encoding="utf-8")
    assert "Show me now" in task
    lesson = (ROOT / "frontend" / "src" / "components" / "LessonView.jsx").read_text(
        encoding="utf-8")
    assert "Your turn" in lesson and "Start task" in lesson
    assert "ScaffoldTask" in lesson
    growth = (ROOT / "frontend" / "src" / "screens" / "MyGrowth.jsx").read_text(
        encoding="utf-8")
    assert "Working more independently" in growth
    assert "api.independence()" in growth
