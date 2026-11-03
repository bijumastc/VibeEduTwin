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


def _learner(tmp_db, discipline="Science"):
    return tmp_db.create_learner("Test", "10", "English", "Malayalam",
                                 discipline=discipline)


def _sentences(text):
    return [s for s in re.split(r"[.!?]+", text.strip()) if s.strip()]


# --- Discipline in the learner profile ------------------------------------
def test_signup_saves_discipline(tmp_db):
    for discipline in ("Science", "Humanities", "Commerce"):
        learner_id = tmp_db.create_learner("T", "10", "English", "Malayalam",
                                           discipline=discipline)
        assert tmp_db.get_learner(learner_id)["discipline"] == discipline


def test_discipline_defaults_to_science(tmp_db):
    learner_id = tmp_db.create_learner("T", "10", "English", "Malayalam")
    assert tmp_db.get_learner(learner_id)["discipline"] == "Science"


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
    assert store.get_learner(1)["discipline"] == "Science"


def test_signup_endpoint(tmp_db):
    body = main.post_learner(main.LearnerIn(name="Asha", discipline="Commerce"))
    assert body["ok"] is True
    assert tmp_db.get_learner(body["learner_id"])["discipline"] == "Commerce"
    with pytest.raises(HTTPException) as exc:
        main.post_learner(main.LearnerIn(name="Asha", discipline="Maths"))
    assert exc.value.status_code == 400


# --- Learn card ------------------------------------------------------------
def test_learn_endpoint_returns_card(tmp_db, monkeypatch):
    monkeypatch.setattr(main, "_query_guide_chunks", lambda skill, n_results=1: ([], []))
    learner_id = _learner(tmp_db, "Humanities")
    tmp_db.save_skill_scores(learner_id, {"Grammar": 85})
    card = main.get_learn(learner_id, "Grammar")
    assert card["skill"] == "Grammar" and card["level"] == 3
    assert card["discipline"] == "Humanities"
    assert len(_sentences(card["rule"])) <= 3
    assert card["source"] and card["license"]
    assert card["good_example"] and card["weak_example"]
    assert card["good_example"] != card["weak_example"]
    with pytest.raises(HTTPException) as bad_skill:
        main.get_learn(learner_id, "Cooking")
    assert bad_skill.value.status_code == 400
    with pytest.raises(HTTPException) as bad_learner:
        main.get_learn(999, "Grammar")
    assert bad_learner.value.status_code == 404


def test_learn_card_uses_chromadb_rule_and_chapter(monkeypatch):
    monkeypatch.setattr(
        main, "_query_guide_chunks",
        lambda skill, n_results=1: (
            ["First. Second. Third. Fourth. Fifth."],
            [{"source": "guide.pdf", "chapter": "Chapter 2", "license": "CC BY"}]))
    card = main.learn_card("Grammar", 1, "Science")
    assert card["rule"] == "First. Second. Third."
    assert card["source"] == "guide.pdf" and card["chapter"] == "Chapter 2"
    assert card["license"] == "CC BY"


def test_learn_card_falls_back_without_guides(monkeypatch):
    monkeypatch.setattr(main, "_query_guide_chunks", lambda skill, n_results=1: ([], []))
    card = main.learn_card("Grammar", 1, "Science")
    assert card["rule"] == main.FALLBACK_RULES["Grammar"]
    assert len(_sentences(card["rule"])) <= 3
    assert card["source"] and card["license"]


def test_discipline_examples_cover_all_skills():
    for skill in main.SKILLS:
        goods = set()
        for discipline in store.DISCIPLINES:
            pair = main.DISCIPLINE_EXAMPLES[skill][discipline]
            assert pair["good"].strip() and pair["weak"].strip()
            assert pair["good"] != pair["weak"]
            goods.add(pair["good"])
        assert len(goods) == 3, f"{skill} examples are not discipline-specific"


def test_diagnose_includes_learn_card(tmp_db, monkeypatch):
    monkeypatch.setattr(main, "study_material", lambda skill, n_results=2: [])
    monkeypatch.setattr(main, "_query_guide_chunks", lambda skill, n_results=1: ([], []))
    learner_id = _learner(tmp_db, "Commerce")
    res = main.post_diagnose(main.DiagnoseIn(learner_id=learner_id, content="Nice good."))
    assert res["learn"]["skill"] == res["weakest"]
    assert res["learn"]["discipline"] == "Commerce"
    assert len(_sentences(res["learn"]["rule"])) <= 3


# --- Discipline-aware practice ---------------------------------------------
def test_practice_uses_learner_discipline(tmp_db):
    learner_id = _learner(tmp_db, "Humanities")
    body = main.get_practice(learner_id)
    assert body["discipline"] == "Humanities"
    assert "variants" not in body["items"][0] and "answer" not in body["items"][0]
    prompts = {d: main.practice_items_for(body["skill"], body["level"], d)[0]["prompt"]
               for d in store.DISCIPLINES}
    assert body["items"][0]["prompt"] == prompts["Humanities"]
    assert len(set(prompts.values())) == 3
    answers = {it["id"]: it["answer"]
               for it in main.practice_items_for(body["skill"], body["level"], "Humanities")}
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


def test_learn_screen_lists_skills_with_levels():
    learn = (ROOT / "frontend" / "src" / "screens" / "Learn.jsx").read_text(encoding="utf-8")
    for skill in main.SKILLS:
        assert skill in learn
    assert "api.learn" in learn and "levelCheck" in learn
    card = (ROOT / "frontend" / "src" / "components" / "LearnCard.jsx").read_text(
        encoding="utf-8")
    assert "Good:" in card and "Weak:" in card and "Practise this" in card


def test_write_shows_learn_card_after_diagnosis():
    write = (ROOT / "frontend" / "src" / "screens" / "Write.jsx").read_text(encoding="utf-8")
    assert "LearnCard" in write and "result.learn" in write


def test_my_growth_merged_drafts_with_feedback():
    growth = (ROOT / "frontend" / "src" / "screens" / "MyGrowth.jsx").read_text(
        encoding="utf-8")
    assert "SkillBars" in growth and "api.drafts()" in growth
    assert "feedback" in growth and "My drafts" in growth
