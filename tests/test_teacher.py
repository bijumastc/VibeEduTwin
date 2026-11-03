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
    main.post_teacher_set(main.TeacherSetIn(
        request="Make 2 items on grammar", note="focus on conclusions"))
    assert seen and all("focus on conclusions" in q for q in seen)


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
    assert "contentEditable" not in teacher
    practice = (ROOT / "frontend" / "src" / "screens" / "Practice.jsx").read_text(
        encoding="utf-8")
    assert "Teacher set" in practice
