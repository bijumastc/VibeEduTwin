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
    monkeypatch.setattr(main, "_model_api_key", lambda: None)  # no assessor
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
    assert res["hints"] == [2, 1, 0]
    assert res["improving"] is True
    assert res["message"] == "Hints used: 2 → 1 → 0"


def test_independence_new_and_steady(tmp_db):
    fresh = _learner(tmp_db)
    res = main.get_independence(fresh)
    assert res["hints"] == [] and res["improving"] is False
    assert res["message"] == "Try a module task to start tracking."
    steady = _learner(tmp_db)
    for _ in range(2):
        attempt = _start(steady)["attempt_id"]
        _help(steady, attempt)
    res = main.get_independence(steady)
    assert res["hints"] == [1, 1]
    assert res["improving"] is False
    with pytest.raises(HTTPException) as exc:
        main.get_independence(999)
    assert exc.value.status_code == 404


def test_independence_encourages_unless_falling(tmp_db):
    rising = _learner(tmp_db)
    first = _start(rising)["attempt_id"]
    _help(rising, first)  # 1 hint
    second = _start(rising)["attempt_id"]
    _help(rising, second)
    main.post_scaffold_show(main.ScaffoldShowIn(
        learner_id=rising, attempt_id=second))  # hint + show-me
    res = main.get_independence(rising)
    assert res["hints"] == [1, 2]
    assert res["improving"] is False
    calm = _learner(tmp_db)
    _start(calm)
    _start(calm)  # no help at all
    res = main.get_independence(calm)
    assert res["hints"] == [0, 0]
    assert res["improving"] is True


def test_steps_serve_sequential_worked_answer(tmp_db, monkeypatch):
    monkeypatch.setattr(main, "_model_api_key", lambda: None)  # no assessor
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
    assert res["hints"] == [1, 0]
    assert res["improving"] is True
    assert res["message"] == "Hints used: 1 → 0"


def _assess_reply(status="ok", score=1, next_step="question", **over):
    import json
    base = {"status": status,
            "strength": "You name the topic.",
            "problem": "Your line has no clear point yet: \"plants need sun\".",
            "quote": "plants need sun",
            "next_action": "Add the one point your paragraph will prove.",
            "score": score, "next_step": next_step}
    base.update(over)
    return json.dumps(base)


def _keyed_assessor(monkeypatch, reply):
    monkeypatch.setattr(main, "_model_api_key", lambda: "K")
    monkeypatch.setattr(main, "_spark_chat", lambda messages: reply)


def test_assessed_weak_try_serves_question_and_scores(tmp_db, monkeypatch):
    _keyed_assessor(monkeypatch, _assess_reply())
    learner_id = _learner(tmp_db, {"Paragraphing": 25})
    attempt = _start(learner_id)["attempt_id"]
    helped = _help(learner_id, attempt, "Plants need sun to grow tall.")
    assert helped["step"] == "question"
    assert helped["question"].strip()
    got = helped["assessment"]
    assert got["score"] == 1 and got["skill"] == "Paragraphing"
    assert got["skill_score"] == 30 and got["skill_level"] == 2
    assert got["feedback"] == ("You name the topic. Your line has no clear "
                               "point yet: \"plants need sun\". Add the one "
                               "point your paragraph will prove.")
    assert main.verify_twin_reply(
        got["feedback"], "Plants need sun to grow tall.") == []
    tools = [row["tool"] for row in store.get_scaffold_events(learner_id)]
    assert "assess" in tools
    assert _help(learner_id, attempt)["step"] == "hint"  # ladder continues


def test_good_answer_moves_to_rewrite(tmp_db, monkeypatch):
    _keyed_assessor(monkeypatch, _assess_reply(
        score=2, next_step="hint", problem="Your point is clear in \"rises fast\".",
        quote="rises fast", next_action="Keep this line as your opener."))
    learner_id = _learner(tmp_db)
    attempt = _start(learner_id)["attempt_id"]
    helped = _help(learner_id, attempt, "Evaporation rises fast on hot days.")
    assert helped["step"] == "rewrite"
    assert "final version" in helped["prompt"]
    assert helped["assessment"]["score"] == 2
    assert helped["assessment"]["skill_score"] == 10


def test_repeated_weak_reaches_excerpt(tmp_db, monkeypatch):
    monkeypatch.setattr(main, "_query_guides", lambda query, n_results=3: _hit())
    _keyed_assessor(monkeypatch, _assess_reply())
    learner_id = _learner(tmp_db, {"Paragraphing": 50})
    attempt = _start(learner_id)["attempt_id"]
    first = _help(learner_id, attempt, "Plants need sun to grow tall.")
    assert first["step"] == "question"
    second = _help(learner_id, attempt, "Plants need sun and rain daily.")
    assert second["step"] == "excerpt"
    assert second["excerpt"]["source"] == "guide.pdf"
    assert second["assessment"]["skill_level"] == 4


def test_copied_attempt_stays_and_scores_zero(tmp_db, monkeypatch):
    def boom(messages):
        raise AssertionError("copied attempts must not call Spark")

    monkeypatch.setattr(main, "_model_api_key", lambda: "K")
    monkeypatch.setattr(main, "_spark_chat", boom)
    learner_id = _learner(tmp_db)
    attempt = _start(learner_id)["attempt_id"]
    model = main.worked_model("topic-sentences", "Sciences")
    helped = _help(learner_id, attempt, model)
    assert helped["step"] == "try"
    got = helped["assessment"]
    assert got["status"] == "copied" and got["score"] == 0
    assert "own words" in got["feedback"]
    assert store.get_skill_scores(learner_id) == []


def test_nonsense_short_attempt(tmp_db, monkeypatch):
    def boom(messages):
        raise AssertionError("nonsense attempts must not call Spark")

    monkeypatch.setattr(main, "_model_api_key", lambda: "K")
    monkeypatch.setattr(main, "_spark_chat", boom)
    learner_id = _learner(tmp_db)
    attempt = _start(learner_id)["attempt_id"]
    helped = _help(learner_id, attempt, "yes ok")
    assert helped["step"] == "try"
    assert helped["assessment"]["status"] == "nonsense"
    assert helped["assessment"]["score"] == 0


def test_off_task_attempt_asks_for_real_try(tmp_db, monkeypatch):
    _keyed_assessor(monkeypatch, _assess_reply(
        status="off_task", score=0, next_step="retry", strength="",
        problem="", quote="",
        next_action="Write one line about evaporation."))
    learner_id = _learner(tmp_db)
    attempt = _start(learner_id)["attempt_id"]
    helped = _help(learner_id, attempt, "Cricket is fun to watch daily.")
    assert helped["step"] == "try"
    assert "evaporation" in helped["assessment"]["feedback"]


def test_no_key_keeps_fixed_ladder(tmp_db, monkeypatch):
    monkeypatch.setattr(main, "_model_api_key", lambda: None)
    learner_id = _learner(tmp_db)
    attempt = _start(learner_id)["attempt_id"]
    helped = _help(learner_id, attempt, "Plants need sun to grow tall daily.")
    assert helped["step"] == "hint"
    assert "assessment" not in helped


def test_level5_assessed_hint_becomes_question(tmp_db, monkeypatch):
    _keyed_assessor(monkeypatch, _assess_reply(next_step="hint"))
    learner_id = _learner(tmp_db, {"Paragraphing": 90})
    attempt = _start(learner_id)["attempt_id"]
    helped = _help(learner_id, attempt, "Plants need sun to grow tall.")
    assert helped["step"] == "question"
    assert "hint" not in helped
    assert helped["assessment"]["next_step"] == "question"


def test_assessor_verifier():
    good = main.verify("assessor", {
        "status": "ok",
        "feedback": "You name the topic. Sharpen this line: \"plants need "
                    "sun\". Add your point.",
        "attempt": "Plants need sun daily.", "quote": "plants need sun",
        "score": 1})
    assert good == {"pass": True, "failed": [], "fix": ""}
    bad_score = main.verify("assessor", {
        "status": "ok", "feedback": "Plants start. Second.",
        "attempt": "Plants grow.", "quote": "plants", "score": 5})
    assert bad_score["failed"] == ["valid-score"]
    one_line = main.verify("assessor", {
        "status": "ok", "feedback": "Plants only.", "attempt": "Plants grow.",
        "quote": "plants", "score": 1})
    assert one_line["failed"] == ["feedback-shape"]
    no_quote = main.verify("assessor", {
        "status": "ok", "feedback": "First. Second.", "attempt": "Plants grow.",
        "quote": "zebras", "score": 1})
    assert no_quote["failed"] == ["quotes-learner"]
    off_task = main.verify("assessor", {
        "status": "off_task", "feedback": "Not the task. Try it freshly.",
        "attempt": "Cricket rules.", "quote": "", "score": 0})
    assert off_task["pass"] is True


def test_rewrite_is_assessed(tmp_db, monkeypatch):
    monkeypatch.setattr(main, "_query_guides", lambda query, n_results=3: _hit())
    _keyed_assessor(monkeypatch, _assess_reply(
        score=2, next_step="rewrite", problem="Your point is clear in \"rises fast\".",
        quote="rises fast", next_action="Keep this line as your opener."))
    learner_id = _learner(tmp_db)
    attempt = _start(learner_id)["attempt_id"]
    _help(learner_id, attempt)
    _help(learner_id, attempt)
    _help(learner_id, attempt)
    done = main.post_scaffold_rewrite(main.ScaffoldRewriteIn(
        learner_id=learner_id, attempt_id=attempt,
        text="Evaporation rises fast on hot days."))
    assert done["step"] == "done" and "Saved" in done["message"]
    assert done["assessment"]["score"] == 2
    assert done["assessment"]["skill_score"] == 10


def test_steps_rule_is_about_the_module(tmp_db, monkeypatch):
    good = ("A topic sentence names the topic. It states the main point "
            "first. Details follow and support it.")
    bad = "Cite every source you borrow with care today. Check dates twice."
    metas = [{"source": "off-topic.pdf", "chapter": "Ch 9", "license": "CC BY"},
             {"source": "Writing for Success (McLean).pdf", "chapter": "Ch 2",
              "license": "CC BY-NC-SA 3.0"}]
    monkeypatch.setattr(main, "_query_guides",
                        lambda query, n_results=8: ([bad, good], metas))
    learner_id = _learner(tmp_db)
    attempt = _start(learner_id)["attempt_id"]
    rule = main.post_scaffold_steps(main.ScaffoldStepsIn(
        learner_id=learner_id, attempt_id=attempt))["rule"]
    assert "topic sentence" in rule["text"]
    assert rule["book"]["title"] == "Writing for Success"
    assert ".pdf" not in rule["book"]["title"]
    assert rule["book"]["license"]


def test_assessment_and_book_ui_strings():
    task = (ROOT / "frontend" / "src" / "components" / "ScaffoldTask.jsx").read_text(
        encoding="utf-8")
    assert "assessment" in task and "Twin's feedback" in task
    assert "BasedOn" in task
    assert "license unknown" not in task


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


def test_growth_hint_card_gates_heading():
    growth = (ROOT / "frontend" / "src" / "screens" / "MyGrowth.jsx").read_text(
        encoding="utf-8")
    assert "Working more independently" in growth
    assert "Hints help you learn - try one step on your own next time." in growth
    assert "independence.improving" in growth


# --- Retry bounds: 2 regens, then the fixed ladder -----------------------------
def test_assessor_retries_twice_then_fixed_ladder(tmp_db, monkeypatch):
    calls = []

    def bad_chat(messages):
        calls.append(messages)
        return "nope"

    monkeypatch.setattr(main, "_model_api_key", lambda: "K")
    monkeypatch.setattr(main, "_spark_chat", bad_chat)
    learner_id = _learner(tmp_db)
    attempt = _start(learner_id)["attempt_id"]
    helped = _help(learner_id, attempt, "Plants need sun to grow tall.")
    assert len(calls) == 3  # 1 initial + 2 regens
    assert helped["step"] == "hint"  # L1 fixed ladder, no assessment
    assert "assessment" not in helped


def test_assessor_retry_success_is_used(tmp_db, monkeypatch):
    replies = ["nope", _assess_reply()]
    calls = []

    def chat(messages):
        calls.append(messages)
        return replies[len(calls) - 1]

    monkeypatch.setattr(main, "_model_api_key", lambda: "K")
    monkeypatch.setattr(main, "_spark_chat", chat)
    learner_id = _learner(tmp_db, {"Paragraphing": 25})
    attempt = _start(learner_id)["attempt_id"]
    helped = _help(learner_id, attempt, "Plants need sun to grow tall.")
    assert len(calls) == 2
    assert helped["step"] == "question"
    assert helped["assessment"]["score"] == 1
