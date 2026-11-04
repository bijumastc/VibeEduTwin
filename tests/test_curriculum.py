"""Curriculum: 6 disciplines x 6 modules, unlock order, verified excerpts."""
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import learner_store as store  # noqa: E402
import main  # noqa: E402
import curriculum_report  # noqa: E402
from fastapi import HTTPException  # noqa: E402


@pytest.fixture
def tmp_db(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "DB_PATH", tmp_path / "curr_learners.db")
    return store


def _learner(tmp_db, discipline="Sciences"):
    return tmp_db.create_learner("Test", "10", "English", "Malayalam",
                                 discipline=discipline)


def _hit(text="First. Second. Third. Fourth."):
    return ([text], [{"source": "guide.pdf", "chapter": "Chapter 2",
                      "license": "CC BY"}])


def _sentences(text):
    return [s for s in re.split(r"[.!?]+", text.strip()) if s.strip()]


# --- Structure ----------------------------------------------------------
def test_six_disciplines_with_genres():
    assert list(main.DISCIPLINE_GENRES) == list(store.DISCIPLINES)
    assert main.DISCIPLINE_GENRES == {
        "Sciences": "lab report",
        "Technology": "technical report",
        "Medicine": "case report",
        "Arts & Humanities": "essay",
        "Commerce & Management": "business report",
        "Social Sciences": "research report",
    }


def test_nine_modules_in_order_with_genre_last():
    shared = ["Topic sentences", "Thesis statements", "Developing paragraphs",
              "Coherence and flow", "Using sources", "Mechanics of writing",
              "Referencing styles", "Academic vocabulary"]
    genres = {"Sciences": "Lab reports", "Technology": "Technical reports",
              "Medicine": "Case reports", "Arts & Humanities": "Essays",
              "Commerce & Management": "Business reports",
              "Social Sciences": "Research reports"}
    for discipline in store.DISCIPLINES:
        modules = main.discipline_modules(discipline)
        assert [m["title"] for m in modules] == shared + [genres[discipline]]
        assert [m["id"] for m in modules] == [
            "topic-sentences", "thesis-statements", "developing-paragraphs",
            "coherence-flow", "using-sources", "mechanics",
            "referencing-styles", "academic-vocabulary", "genre"]


def test_curriculum_echoes_learner_discipline(tmp_db):
    learner_id = _learner(tmp_db, "Medicine")
    res = main.get_curriculum(learner_id)
    assert res["discipline"] == "Medicine"
    assert [d["name"] for d in res["disciplines"]] == list(store.DISCIPLINES)
    with pytest.raises(HTTPException) as exc:
        main.get_curriculum(999)
    assert exc.value.status_code == 404


# --- Open curriculum + recommended module ------------------------------------
def test_all_modules_open_for_fresh_learner(tmp_db):
    states = main.get_curriculum(_learner(tmp_db))["disciplines"][0]["modules"]
    assert all(s["unlocked"] for s in states)
    assert [s["id"] for s in states if s["recommended"]] == ["topic-sentences"]


def test_recommended_follows_weakest_skill(tmp_db):
    learner_id = _learner(tmp_db)
    store.save_skill_scores(learner_id, {s: 70 for s in main.SKILLS}
                            | {"Using sources": 10})
    states = main.get_curriculum(learner_id)["disciplines"][0]["modules"]
    assert all(s["unlocked"] for s in states)
    assert [s["id"] for s in states if s["recommended"]] == ["using-sources"]


def test_recommended_picks_first_module_of_weakest_skill(tmp_db):
    learner_id = _learner(tmp_db)
    store.save_skill_scores(learner_id, {s: 70 for s in main.SKILLS}
                            | {"Paragraphing": 10})
    states = main.get_curriculum(learner_id)["disciplines"][0]["modules"]
    assert [s["id"] for s in states if s["recommended"]] == ["topic-sentences"]


# --- Lesson content -------------------------------------------------------
def test_module_lesson_uses_grounded_idea(tmp_db, monkeypatch):
    doc = ("A topic sentence opens the paragraph. It states the main point "
           "first. Details that follow support it. For example, labs open "
           "with the key finding for the reader.")
    meta = {"source": "Writing for Success (McLean).pdf", "chapter": "Ch 4",
            "license": "CC BY-NC-SA 3.0"}
    monkeypatch.setattr(main, "_query_guides",
                        lambda query, n_results=8: ([doc], [meta]))
    learner_id = _learner(tmp_db)
    res = main.get_curriculum_module(learner_id, "Sciences", "topic-sentences")
    assert res["title"] == "Topic sentences"
    assert res["idea"]["text"] == main.LESSON_IDEAS["topic-sentences"]
    assert "hook" in res and res["hook"].strip()
    assert len(res["try_first"]["options"]) == 3
    assert res["task"].strip() and res["why"].strip()
    assert res["based_on"][0]["title"] == "Writing for Success"
    assert ".pdf" not in res["based_on"][0]["title"]


def test_module_lesson_quotes_when_ungrounded(tmp_db, monkeypatch):
    monkeypatch.setattr(main, "_query_guides", lambda query, n_results=8: _hit())
    learner_id = _learner(tmp_db)
    res = main.get_curriculum_module(learner_id, "Sciences", "topic-sentences")
    assert res["idea"]["text"] == "First. Second."
    assert res["example"]["text"] == main.NO_VERIFIED_EXAMPLE


def test_module_content_falls_back_to_no_verified(tmp_db, monkeypatch):
    monkeypatch.setattr(main, "_query_guides", lambda query, n_results=8: ([], []))
    learner_id = _learner(tmp_db)
    res = main.get_curriculum_module(learner_id, "Sciences", "topic-sentences")
    assert res["idea"]["text"] == main.NO_VERIFIED_EXAMPLE
    assert res["example"]["text"] == main.NO_VERIFIED_EXAMPLE
    assert res["based_on"] == []


def test_new_modules_build_lessons_and_tasks(tmp_db, monkeypatch):
    monkeypatch.setattr(main, "_query_guides", lambda query, n_results=8: ([], []))
    learner_id = _learner(tmp_db)
    skills = {"mechanics": "Grammar", "referencing-styles": "Using sources",
              "academic-vocabulary": "Vocabulary"}
    ids = [m["id"] for m in main.get_curriculum(learner_id)["disciplines"][0]
           ["modules"]]
    assert len(ids) == 9
    for module_id, skill in skills.items():
        assert module_id in ids
        lesson = main.get_curriculum_module(
            learner_id, "Sciences", module_id)
        assert lesson["skill"] == skill
        assert lesson["idea"]["text"] == main.NO_VERIFIED_EXAMPLE
        assert lesson["task"].strip() and lesson["why"].strip()
        view = main.post_scaffold_start(main.ScaffoldStartIn(
            learner_id=learner_id, discipline="Sciences", module=module_id))
        assert view["step"] == "try" and view["task"].strip()


def test_every_module_opens_without_scores(tmp_db):
    learner_id = _learner(tmp_db)
    res = main.get_curriculum_module(learner_id, "Sciences", "thesis-statements")
    assert res["title"] == "Thesis statements"


def test_module_errors(tmp_db):
    learner_id = _learner(tmp_db)
    with pytest.raises(HTTPException) as bad_disc:
        main.get_curriculum_module(learner_id, "Cooking", "topic-sentences")
    assert bad_disc.value.status_code == 400
    with pytest.raises(HTTPException) as bad_mod:
        main.get_curriculum_module(learner_id, "Sciences", "spelling")
    assert bad_mod.value.status_code == 404
    with pytest.raises(HTTPException) as bad_learner:
        main.get_curriculum_module(999, "Sciences", "topic-sentences")
    assert bad_learner.value.status_code == 404


def test_verified_excerpt_skips_empty_docs(monkeypatch):
    monkeypatch.setattr(
        main, "_query_guides",
        lambda query, n_results=3: (
            ["", "  ", "Good one. Two. Three. Four."],
            [{}, {}, {"source": "b.pdf", "chapter": "Ch 1", "license": "CC BY"}]))
    excerpt = main.verified_excerpt("anything")
    assert excerpt["text"] == "Good one. Two. Three."
    assert excerpt["source"] == "b.pdf"


def test_learn_card_queries_rule_and_example(monkeypatch):
    seen = []

    def fake_query(query, n_results=3):
        seen.append(query)
        return _hit(f"Alpha {query} one. Beta {query} two. "
                    f"Gamma {query} three. Delta {query} four.")

    monkeypatch.setattr(main, "_query_guides", fake_query)
    card = main.learn_card("Grammar", 1, "Sciences")
    assert "rule" in seen[0] and "lab report" in seen[1]
    assert len(_sentences(card["idea"]["text"])) <= 2
    assert "guide.pdf" not in card["based_on"][0]["title"]
    assert card["idea"]["text"] != card["example"]["text"]


# --- Practice genre families -----------------------------------------------
def test_practice_genre_families_share_variants():
    for (skill, level) in list(main.PRACTICE_BANK)[:2]:
        sciences = main.practice_items_for(skill, level, "Sciences")
        assert main.practice_items_for(skill, level, "Technology") == sciences
        assert main.practice_items_for(skill, level, "Medicine") == sciences
        arts = main.practice_items_for(skill, level, "Arts & Humanities")
        assert main.practice_items_for(skill, level, "Social Sciences") == arts
        assert sciences[0]["prompt"] != arts[0]["prompt"]


# --- Coverage report ---------------------------------------------------------
def test_report_lists_gaps():
    def fake_excerpt(query, sentences=3):
        if "example" in query:
            return {"text": main.NO_VERIFIED_EXAMPLE, "source": None,
                    "chapter": None, "license": None}
        return {"text": "Rule text.", "source": "guide.pdf",
                "chapter": "Ch 1", "license": "CC BY"}

    rows = curriculum_report.build_coverage(fake_excerpt)
    assert len(rows) == 54  # 6 disciplines x 9 modules
    assert all(r["rule_ok"] for r in rows)
    assert not any(r["example_ok"] for r in rows)
    assert rows[0]["discipline"] == "Sciences"
    assert rows[0]["module"] == "Topic sentences"


def test_report_queries_use_module_and_genre():
    seen = []

    def fake_excerpt(query, sentences=3):
        seen.append(query)
        return {"text": "t", "source": "s", "chapter": "c", "license": "l"}

    curriculum_report.build_coverage(fake_excerpt)
    assert any("topic sentences rule" in q for q in seen)
    assert any("lab report" in q for q in seen)
    assert any("case report" in q for q in seen)
