"""Teacher page: excerpt-built sets, verifier, publish into Practice."""
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
    monkeypatch.setattr(store, "DB_PATH", tmp_path / "teacher_learners.db")
    return store


def _learner(tmp_db, discipline="Sciences", scores=None):
    learner_id = tmp_db.create_learner("Test", "10", "English", "Malayalam",
                                       discipline=discipline)
    if scores:
        tmp_db.save_skill_scores(learner_id, scores)
    return learner_id


def _fake_query(query, n_results=2):
    docs = [f"Alpha point {i} about {query}. Beta point {i} about {query}. "
            f"Gamma point {i} about {query}. Delta point {i} about {query}."
            for i in range(n_results)]
    metas = [{"source": f"book{i}.pdf", "chapter": f"Ch {i}", "license": "CC BY"}
             for i in range(n_results)]
    return docs, metas


def _valid_items():
    return [
        {"id": "t1", "type": "mcq", "prompt": "Pick one.",
         "options": ["A) first", "B) second"], "answer": "A",
         "explanation": "Because.", "source": "b.pdf"},
        {"id": "t2", "type": "order", "prompt": "Order them.",
         "options": ["1,2", "2,1"], "answer": "1,2",
         "explanation": "Because.", "source": "b.pdf"},
    ]


# --- Request parsing -----------------------------------------------------
def test_parse_example_request():
    parsed = main.parse_teacher_request(
        "Make 5 practice items on topic sentences for first-year Science students at Level 2")
    assert parsed == {"skill": "Paragraphing", "count": 5, "level": 2,
                      "discipline": "Sciences"}


def test_parse_defaults_and_clamps():
    assert main.parse_teacher_request("Something about grammar") == {
        "skill": "Grammar", "count": 3, "level": 1, "discipline": None}
    assert main.parse_teacher_request("Make 20 items on verbs")["count"] == 10
    assert main.parse_teacher_request("Items on nouns at Level 9")["level"] == 1
    assert main.parse_teacher_request("Sets for nursing students")["discipline"] == "Medicine"


# --- Excerpt-built generation ----------------------------------------------
def test_generate_uses_only_excerpts_with_sources(monkeypatch):
    monkeypatch.setattr(main, "_query_guides", _fake_query)
    monkeypatch.setattr(main, "_model_api_key", lambda: None)  # template path
    items = main.generate_practice_set("Make 4 practice items on grammar")
    assert len(items) == 4
    assert main.verify_practice_set(items) == []
    for item in items:
        assert item["source"] and item["source"].endswith(".pdf")
        assert item["source"] in item["explanation"]
    order = next(i for i in items if i["type"] == "order")
    assert "Alpha point" in order["prompt"]  # excerpt sentences in prompt
    mcq = next(i for i in items if i["type"] == "mcq")
    assert any("Alpha point" in o for o in mcq["options"])


def test_generate_mixed_types_and_deterministic(monkeypatch):
    monkeypatch.setattr(main, "_query_guides", _fake_query)
    monkeypatch.setattr(main, "_model_api_key", lambda: None)  # template path
    first = main.generate_practice_set("Make 4 practice items on grammar")
    second = main.generate_practice_set("Make 4 practice items on grammar")
    assert first == second
    assert {i["type"] for i in first} == {"mcq", "order"}


def test_generate_empty_library_fails_cleanly(monkeypatch):
    monkeypatch.setattr(main, "_query_guides", lambda query, n_results=2: ([], []))
    assert main.generate_practice_set("Make 3 items on grammar") == []
    res = main.post_teacher_set(main.TeacherSetIn(request="Make 3 items on grammar"))
    assert res["passed"] is False and res["items"] == []
    assert any("excerpt" in e.lower() for e in res["errors"])


def test_generate_passes_and_reports_parsed_fields(monkeypatch):
    monkeypatch.setattr(main, "_query_guides", _fake_query)
    monkeypatch.setattr(main, "_model_api_key", lambda: None)  # template path
    res = main.post_teacher_set(main.TeacherSetIn(
        request="Make 2 practice items on verbs at Level 2"))
    assert res["passed"] is True and res["errors"] == []
    assert len(res["items"]) == 2
    assert (res["skill"], res["level"], res["discipline"]) == ("Grammar", 2, None)


def test_regenerate_note_steers_retrieval(monkeypatch):
    seen = []

    def spy(query, n_results=2):
        seen.append(query)
        return _fake_query(query, n_results)

    monkeypatch.setattr(main, "_query_guides", spy)
    monkeypatch.setattr(main, "_model_api_key", lambda: None)  # template path
    main.post_teacher_set(main.TeacherSetIn(
        request="Make 2 items on grammar", note="focus on conclusions"))
    assert seen and all("focus on conclusions" in q for q in seen)


# --- Muse Spark grounding ------------------------------------------------------
def _spark_reply(items):
    import json
    return json.dumps(items)


def _grounded_order():
    return {"type": "order",
            "prompt": "Put the paragraph in order. Sentences: 1) 'Alpha point 0 "
                      "about Grammar writing.' 2) 'Beta point 0 about Grammar "
                      "writing.'",
            "options": ["1,2", "2,1"], "answer": "1,2",
            "answerExcerpt": "E1"}


def _grounded_mcq():
    return {"type": "mcq",
            "prompt": "Which sentence gives grammar advice?",
            "options": ["A) Alpha point 1 about Grammar writing.",
                        "B) Beta point 1 about Grammar writing."],
            "answer": "A", "answerExcerpt": "E2"}


def _invented_mcq():
    return {"type": "mcq", "prompt": "Which sentence is true?",
            "options": ["A) Zebras drink lava nightly.",
                        "B) Clouds file taxes quarterly."],
            "answer": "A", "answerExcerpt": "E1"}


def test_spark_grounded_items_pass_through(monkeypatch):
    monkeypatch.setattr(main, "_query_guides", _fake_query)
    monkeypatch.setattr(main, "_spark_chat",
                        lambda messages: _spark_reply(
                            [_grounded_order(), _grounded_mcq()]))
    items = main.generate_practice_set("Make 2 practice items on grammar")
    assert len(items) == 2
    assert main.verify_practice_set(items) == []
    assert items[0]["source"] == "book0.pdf"  # E1 resolved server-side
    assert items[1]["source"] == "book1.pdf"  # E2 resolved server-side
    assert "book0.pdf" in items[0]["explanation"]
    res = main.post_teacher_set(main.TeacherSetIn(
        request="Make 2 practice items on grammar"))
    assert res["passed"] is True and res["engine"] == "spark"


def test_spark_invented_items_dropped_and_backfilled(monkeypatch):
    monkeypatch.setattr(main, "_query_guides", _fake_query)
    monkeypatch.setattr(main, "_spark_chat",
                        lambda messages: _spark_reply(
                            [_grounded_mcq(), _invented_mcq()]))
    items = main.generate_practice_set("Make 2 practice items on grammar")
    assert len(items) == 2
    blob = " ".join(i["prompt"] + " " + " ".join(i["options"]) for i in items)
    assert "Zebra" not in blob and "lava" not in blob
    assert "Alpha point" in blob  # template backfill kept the count
    res = main.post_teacher_set(main.TeacherSetIn(
        request="Make 2 practice items on grammar"))
    assert res["engine"] == "mixed"


def test_spark_failure_falls_back_to_template(monkeypatch):
    def boom(messages):
        raise main.SparkError("down")

    monkeypatch.setattr(main, "_query_guides", _fake_query)
    monkeypatch.setattr(main, "_spark_chat", boom)
    items = main.generate_practice_set("Make 4 practice items on grammar")
    assert len(items) == 4
    assert any("Alpha point" in o for i in items for o in i["options"])
    res = main.post_teacher_set(main.TeacherSetIn(
        request="Make 4 practice items on grammar"))
    assert res["engine"] == "template"


def test_no_key_uses_template(monkeypatch):
    monkeypatch.setattr(main, "_query_guides", _fake_query)
    monkeypatch.setattr(main, "_model_api_key", lambda: None)
    res = main.post_teacher_set(main.TeacherSetIn(
        request="Make 2 practice items on grammar"))
    assert res["engine"] == "template"
    assert len(res["items"]) == 2


def test_spark_prompt_shows_excerpts_and_note(monkeypatch):
    monkeypatch.setattr(main, "_query_guides", _fake_query)
    seen = {}
    monkeypatch.setattr(main, "_model_api_key", lambda: "K")

    def fake_post(url, body, key, timeout):
        seen["url"] = url
        seen["body"] = body
        seen["key"] = key
        return {"choices": [{"message": {"content": "[]"}}]}

    monkeypatch.setattr(main, "_spark_post", fake_post)
    main.generate_practice_set("Make 2 items on grammar", note="focus on verbs")
    assert seen["url"] == "https://api.meta.ai/v1/chat/completions"
    assert seen["key"] == "K"
    assert seen["body"]["model"] == "muse-spark-1.3"
    assert seen["body"]["response_format"] == {"type": "json_object"}
    user_text = seen["body"]["messages"][-1]["content"]
    assert "E1" in user_text and "Alpha point 0" in user_text
    assert "focus on verbs" in user_text
    assert "word-for-word" in seen["body"]["messages"][0]["content"]


def test_excerpt_grounding_verifier():
    excerpts = ["Alpha point here. Beta point here."]
    good = {"prompt": "Pick: Alpha point here.", "options": ["A", "B"]}
    verdict = main.verify("excerpt_grounding",
                          {"items": [good], "excerpts": excerpts})
    assert verdict == {"pass": True, "failed": [], "fix": ""}
    bad = {"prompt": "Pick: Zebras drink lava.", "options": ["A", "B"]}
    verdict = main.verify("excerpt_grounding",
                          {"items": [good, bad], "excerpts": excerpts})
    assert verdict["pass"] is False
    assert verdict["failed"] == ["item 2: grounded-in-excerpts"]
    assert verdict["fix"]


# --- Publish -----------------------------------------------------------------
def test_publish_roundtrip_and_validation(tmp_db):
    body = main.post_teacher_publish(main.TeacherPublishIn(
        request="r", skill="Grammar", level=1, discipline="Sciences",
        items=_valid_items()))
    assert body["ok"] is True
    found = store.get_teacher_set("Grammar", 1, "Sciences")
    assert found and len(found["items"]) == 2
    with pytest.raises(HTTPException) as exc:
        main.post_teacher_publish(main.TeacherPublishIn(
            request="r", skill="Grammar", level=1, items=[]))
    assert exc.value.status_code == 400
    with pytest.raises(HTTPException) as exc:
        main.post_teacher_publish(main.TeacherPublishIn(
            request="r", skill="Cooking", level=1, items=_valid_items()))
    assert exc.value.status_code == 400
    with pytest.raises(HTTPException) as exc:
        main.post_teacher_publish(main.TeacherPublishIn(
            request="r", skill="Grammar", level=9, items=_valid_items()))
    assert exc.value.status_code == 400
    with pytest.raises(HTTPException) as exc:
        main.post_teacher_publish(main.TeacherPublishIn(
            request="r", skill="Grammar", level=1, discipline="Maths",
            items=_valid_items()))
    assert exc.value.status_code == 400


def test_specific_beats_generic_set(tmp_db):
    store.save_teacher_set("Grammar", 1, None, _valid_items(), "generic")
    store.save_teacher_set("Grammar", 1, "Sciences", _valid_items(), "specific")
    assert store.get_teacher_set("Grammar", 1, "Sciences")["request"] == "specific"
    assert store.get_teacher_set("Grammar", 1, "Medicine")["request"] == "generic"
    assert store.get_teacher_set("Grammar", 2, "Sciences") is None


# --- Published sets in Practice -----------------------------------------------
def test_practice_serves_published_set(tmp_db):
    sciences = _learner(tmp_db, "Sciences")  # no scores: Paragraphing L1
    medicine = _learner(tmp_db, "Medicine")
    store.save_teacher_set("Paragraphing", 1, "Sciences", _valid_items(), "r")
    got = main.get_practice(sciences)
    assert got["published"] is True
    assert [i["id"] for i in got["items"]] == ["t1", "t2"]
    bank = main.get_practice(medicine)
    assert bank["published"] is False
    answers = {"t1": "A", "t2": "1,2"}
    scored = main.post_answers(main.PracticeAnswersIn(
        learner_id=sciences, set_id=got["set_id"], answers=answers))
    assert scored["accuracy"] == 100


def test_practice_serves_generic_set_to_all(tmp_db):
    store.save_teacher_set("Paragraphing", 1, None, _valid_items(), "r")
    for discipline in ("Sciences", "Medicine"):
        learner_id = _learner(tmp_db, discipline)
        got = main.get_practice(learner_id)
        assert got["published"] is True
        assert [i["id"] for i in got["items"]] == ["t1", "t2"]


# --- Panel logging -------------------------------------------------------------
def test_published_set_logs_provenance_in_panel(tmp_db):
    learner_id = _learner(tmp_db, "Sciences")
    store.save_teacher_set("Paragraphing", 1, "Sciences", _valid_items(), "r")
    main.get_practice(learner_id)
    rows = [r for r in store.get_events(learner_id) if r["tool"] == "teacher-set"]
    assert len(rows) == 1
    assert rows[0]["step"] == "Practise" and rows[0]["agent"] == "teacher"
    assert "2 items" in rows[0]["result"]
    assert "1 excerpt" in rows[0]["result"]
    assert "verifier passed" in rows[0]["result"]
    assert "published" in rows[0]["result"]


def test_bank_sets_log_no_teacher_provenance(tmp_db):
    learner_id = _learner(tmp_db, "Sciences")
    main.get_practice(learner_id)
    assert "teacher-set" not in [r["tool"] for r in store.get_events(learner_id)]


# --- Page wiring (static) -------------------------------------------------------
def test_teacher_page_wiring():
    home = (ROOT / "frontend" / "src" / "screens" / "Home.jsx").read_text(encoding="utf-8")
    assert "Teacher tools" in home and "go('teacher')" in home
    app = (ROOT / "frontend" / "src" / "App.jsx").read_text(encoding="utf-8")
    assert "screens/Teacher.jsx" in app and "tab === 'teacher'" in app
    nav = (ROOT / "frontend" / "src" / "components" / "BottomNav.jsx").read_text(
        encoding="utf-8")
    assert "teacher" not in nav.lower()
    teacher = (ROOT / "frontend" / "src" / "screens" / "Teacher.jsx").read_text(
        encoding="utf-8")
    assert "Generate items" in teacher and "Verifier" in teacher
    assert "Publish" in teacher and "Regenerate" in teacher
    assert "Muse Spark" in teacher
    assert "contentEditable" not in teacher
    practice = (ROOT / "frontend" / "src" / "screens" / "Practice.jsx").read_text(
        encoding="utf-8")
    assert "Teacher set" in practice
