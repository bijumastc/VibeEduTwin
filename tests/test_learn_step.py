"""Learn step: discipline profiles, Learn cards, discipline practice, 5 tabs."""
import re
import sqlite3
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
    monkeypatch.setattr(store, "DB_PATH", tmp_path / "learn_learners.db")
    return store


def _learner(tmp_db, discipline="Sciences"):
    return tmp_db.create_learner("Test", "10", "English", "Malayalam",
                                 discipline=discipline)


def _sentences(text):
    return [s for s in re.split(r"[.!?]+", text.strip()) if s.strip()]


# --- Discipline in the learner profile ------------------------------------
def test_signup_saves_discipline(tmp_db):
    assert len(store.DISCIPLINES) == 6
    for discipline in store.DISCIPLINES:
        learner_id = tmp_db.create_learner("T", "10", "English", "Malayalam",
                                           discipline=discipline)
        assert tmp_db.get_learner(learner_id)["discipline"] == discipline


def test_discipline_defaults_to_sciences(tmp_db):
    learner_id = tmp_db.create_learner("T", "10", "English", "Malayalam")
    assert tmp_db.get_learner(learner_id)["discipline"] == "Sciences"


def test_invalid_discipline_rejected(tmp_db):
    with pytest.raises(ValueError):
        tmp_db.create_learner("T", "10", "English", "Malayalam", discipline="Maths")


def test_migration_adds_discipline_to_old_db(tmp_path, monkeypatch):
    db_path = tmp_path / "old.db"
    conn = sqlite3.connect(db_path)
    conn.execute("""CREATE TABLE learners (
        id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL,
        year TEXT NOT NULL, subject TEXT NOT NULL,
        language_preference TEXT NOT NULL, created_at TEXT NOT NULL)""")
    conn.execute("INSERT INTO learners (name, year, subject, language_preference,"
                 " created_at) VALUES ('Old', '10', 'English', 'Malayalam', 'now')")
    conn.commit()
    conn.close()
    monkeypatch.setattr(store, "DB_PATH", db_path)
    assert store.get_learner(1)["discipline"] == "Sciences"


def test_old_discipline_names_migrated(tmp_db):
    with tmp_db._connect():
        pass  # create tables
    conn = sqlite3.connect(tmp_db.DB_PATH)
    conn.execute("INSERT INTO learners (name, year, subject, language_preference,"
                 " discipline, created_at) VALUES ('A', '10', 'English', 'Malayalam',"
                 " 'Science', 'now')")
    conn.execute("INSERT INTO learners (name, year, subject, language_preference,"
                 " discipline, created_at) VALUES ('B', '10', 'English', 'Malayalam',"
                 " 'Humanities', 'now')")
    conn.execute("INSERT INTO learners (name, year, subject, language_preference,"
                 " discipline, created_at) VALUES ('C', '10', 'English', 'Malayalam',"
                 " 'Commerce', 'now')")
    conn.commit()
    conn.close()
    assert tmp_db.get_learner(1)["discipline"] == "Sciences"
    assert tmp_db.get_learner(2)["discipline"] == "Arts & Humanities"
    assert tmp_db.get_learner(3)["discipline"] == "Commerce & Management"


def test_signup_endpoint(tmp_db):
    body = main.post_learner(main.LearnerIn(name="Asha", discipline="Commerce & Management"))
    assert body["ok"] is True
    assert tmp_db.get_learner(body["learner_id"])["discipline"] == "Commerce & Management"
    with pytest.raises(HTTPException) as exc:
        main.post_learner(main.LearnerIn(name="Asha", discipline="Maths"))
    assert exc.value.status_code == 400


# --- Learn card (verified excerpts only) -------------------------------------
def test_diagnose_includes_learn_card(tmp_db, monkeypatch):
    monkeypatch.setattr(main, "study_material", lambda skill, n_results=2: [])
    monkeypatch.setattr(main, "_query_guides", lambda query, n_results=3: ([], []))
    learner_id = _learner(tmp_db, "Commerce & Management")
    res = main.post_diagnose(main.DiagnoseIn(learner_id=learner_id, content="Nice good."))
    assert res["learn"]["skill"] == res["weakest"]
    assert res["learn"]["discipline"] == "Commerce & Management"
    assert res["learn"]["rule"]["text"] == main.NO_VERIFIED_EXAMPLE
    assert res["learn"]["example"]["text"] == main.NO_VERIFIED_EXAMPLE


# --- Discipline-aware practice ---------------------------------------------
def test_practice_uses_learner_discipline(tmp_db):
    learner_id = _learner(tmp_db, "Arts & Humanities")
    body = main.get_practice(learner_id)
    assert body["discipline"] == "Arts & Humanities"
    assert "variants" not in body["items"][0] and "answer" not in body["items"][0]
    served = main.practice_items_for(body["skill"], body["level"], "Arts & Humanities")
    assert body["items"][0]["prompt"] == served[0]["prompt"]
    other = main.practice_items_for(body["skill"], body["level"], "Sciences")
    assert served[0]["prompt"] != other[0]["prompt"]
    answers = {it["id"]: it["answer"] for it in served}
    scored = main.post_answers(main.PracticeAnswersIn(
        learner_id=learner_id, set_id=body["set_id"], answers=answers))
    assert scored["accuracy"] == 100


def test_practice_variants_keep_answers_valid():
    for (skill, level), items in main.PRACTICE_BANK.items():
        base_ids = [it["id"] for it in items]
        for discipline in store.DISCIPLINES:
            rendered = main.practice_items_for(skill, level, discipline)
            assert [it["id"] for it in rendered] == base_ids
            assert main.verify_practice_set(rendered) == [], (skill, level, discipline)


# --- Tabs and merged screens (static) ---------------------------------------
def test_tabs_are_home_write_learn_practice_growth():
    nav = (ROOT / "frontend" / "src" / "components" / "BottomNav.jsx").read_text(
        encoding="utf-8")
    assert re.findall(r"id: '(\w+)'", nav) == ["home", "write", "learn", "practice", "growth"]
    assert "My Writing" not in nav
    app = (ROOT / "frontend" / "src" / "App.jsx").read_text(encoding="utf-8")
    assert "screens/Learn.jsx" in app and "MyWriting" not in app
    assert not (ROOT / "frontend" / "src" / "screens" / "MyWriting.jsx").exists()


def test_learn_screen_is_discipline_curriculum():
    learn = (ROOT / "frontend" / "src" / "screens" / "Learn.jsx").read_text(encoding="utf-8")
    assert "api.curriculum()" in learn and "api.moduleContent(" in learn
    assert "current" in learn and "Locked" in learn
    assert "res.discipline" in learn  # learner's discipline opens by default
    card = (ROOT / "frontend" / "src" / "components" / "LearnCard.jsx").read_text(
        encoding="utf-8")
    assert "Rule:" in card and "Example:" in card and "Practise this" in card
    assert "chapter" in card and "license" in card


def test_write_shows_learn_card_after_diagnosis():
    write = (ROOT / "frontend" / "src" / "screens" / "Write.jsx").read_text(encoding="utf-8")
    assert "LearnCard" in write and "result.learn.rule" in write
    assert "result.learn.example" in write


def test_my_growth_merged_drafts_with_feedback():
    growth = (ROOT / "frontend" / "src" / "screens" / "MyGrowth.jsx").read_text(
        encoding="utf-8")
    assert "SkillBars" in growth and "api.drafts()" in growth
    assert "feedback" in growth and "My drafts" in growth
