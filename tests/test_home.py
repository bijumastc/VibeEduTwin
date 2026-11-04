"""Home loads on a fresh learner; the client reports real errors.

Also: named levels and the Today's session derivation.
"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import learner_store as store  # noqa: E402
import main  # noqa: E402


@pytest.fixture
def tmp_db(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "DB_PATH", tmp_path / "home_learners.db")
    return store


def test_home_first_requests_succeed_on_fresh_learner(tmp_db):
    learner_id = tmp_db.create_learner("T", "10", "English", "Malayalam")
    growth = main.get_growth(learner_id)
    assert growth["scores"] == {} and growth["history"] == {}
    levels = main.post_level_check(main.LevelCheckIn(learner_id=learner_id))
    assert levels["levels"] == {} and levels["leveled_up"] == []


def test_next_win_prefers_craft_skills_first():
    levels = {"Grammar": 2, "Using sources": 1, "Vocabulary": 2,
              "Sentence structure": 2, "Paragraphing": 2, "Argument": 2,
              "Academic tone": 2}
    assert main.next_win_skill(levels, "I like plants.") == "Grammar"
    cited = "According to Rao, trees cool streets."
    assert main.next_win_skill(levels, cited) == "Using sources"
    assert main.next_win_skill(levels, "Half the class, 50%, agreed.") == \
        "Using sources"


def test_next_win_sources_only_when_others_high_or_evidence():
    low = {"Grammar": 1, "Using sources": 1, "Vocabulary": 2,
           "Sentence structure": 2, "Paragraphing": 2, "Argument": 2,
           "Academic tone": 2}
    assert main.next_win_skill(low, "I like plants.") == "Grammar"
    high = {"Grammar": 4, "Using sources": 2, "Vocabulary": 3,
            "Sentence structure": 3, "Paragraphing": 3, "Argument": 3,
            "Academic tone": 3}
    assert main.next_win_skill(high, "I like plants.") == "Using sources"
    strong_sources = {"Grammar": 1, "Using sources": 4, "Vocabulary": 2,
                      "Sentence structure": 2, "Paragraphing": 2,
                      "Argument": 2, "Academic tone": 2}
    assert main.next_win_skill(strong_sources, "I like plants.") == "Grammar"


def test_growth_serves_profile_and_short_quote(tmp_db, monkeypatch):
    monkeypatch.setattr(main, "study_material", lambda skill, n_results=2: [])
    monkeypatch.setattr(main, "_query_guide_chunks",
                        lambda skill, n_results=1: ([], []))
    monkeypatch.setattr(main, "_model_api_key", lambda: None)
    learner_id = tmp_db.create_learner("T", "10", "English", "Malayalam")
    text = ("I like plants. Plants give water and keep climate well. "
            "Trees give shade to all.")
    draft_id = tmp_db.save_draft(learner_id, text, "")
    main.post_diagnose(main.DiagnoseIn(learner_id=learner_id,
                                       draft_id=draft_id))
    growth = main.get_growth(learner_id)
    assert growth["strongest"]["skill"] in main.SKILLS
    assert growth["strongest"]["reason"].strip()
    win = growth["next_win"]
    assert win["skill"] in main.SKILLS
    assert win["action"] == main.NEXT_WIN_ACTIONS[win["skill"]]
    assert win["quote"] and len(win["quote"].split()) <= 13  # 12 + ellipsis
    assert win["quote"] != text  # short quote, not the whole paragraph


def test_home_profile_strings():
    home = (ROOT / "frontend" / "src" / "screens" / "Home.jsx").read_text(
        encoding="utf-8")
    assert "Discover your writing level" in home and "✍️" in home
    assert "Write 4-5 lines on any topic" in home
    assert "Find my level" in home
    assert "Speak it" in home and "Scan my notebook" in home
    assert "Your writing profile" in home
    assert "You do well:" in home and "Your next win:" in home
    assert "Start my next win (5 min)" in home
    assert "Check my level again" in home
    assert "OpenModule" in home and "SKILL_MODULE" in home
    assert "Teacher tools" in home
    nav = (ROOT / "frontend" / "src" / "components" / "BottomNav.jsx"
           ).read_text(encoding="utf-8")
    assert "My Level" in nav
    learn = (ROOT / "frontend" / "src" / "screens" / "Learn.jsx").read_text(
        encoding="utf-8")
    assert "OpenModule.consume()" in learn
    api = (ROOT / "frontend" / "src" / "api.js").read_text(encoding="utf-8")
    assert "OpenModule" in api


def test_api_client_reports_target_and_real_errors():
    api = (ROOT / "frontend" / "src" / "api.js").read_text(encoding="utf-8")
    assert "Cannot reach the backend at ${API_URL}" in api
    assert "invalid response" in api
    assert "python scripts/reset_demo.py" in api


# --- Named levels ------------------------------------------------------------
def test_level_names_cover_all_levels():
    assert main.LEVEL_NAMES == {
        1: "Starter", 2: "Elementary", 3: "Intermediate",
        4: "Upper-Intermediate", 5: "Advanced"}


def test_growth_names_overall_level(tmp_db):
    learner_id = tmp_db.create_learner("T", "10", "English", "Malayalam")
    assert main.get_growth(learner_id)["overall"] == {
        "level": 1, "name": "Starter"}
    tmp_db.save_skill_scores(learner_id, {s: 50 for s in main.SKILLS})
    assert main.get_growth(learner_id)["overall"] == {
        "level": 3, "name": "Intermediate"}


# --- Today's session ---------------------------------------------------------
def test_session_steps_and_resume(tmp_db):
    learner_id = tmp_db.create_learner("T", "10", "English", "Malayalam")
    fresh = main.get_growth(learner_id)["session"]
    assert fresh["level_name"] == "Starter" and fresh["target"] == 50
    assert fresh["step"] == 1 and fresh["started"] is False
    assert fresh["sessions_done"] == 0
    long = " ".join(f"word{i}" for i in range(60))
    tmp_db.save_draft(learner_id, long, "")
    mid = main.get_growth(learner_id)["session"]
    assert mid["started"] is True and mid["step"] == 2  # resume here
    assert mid["steps_done"] == [True, False, False]
    tmp_db.save_draft(learner_id, "My rewrite fixes the first line.", "")
    assert main.get_growth(learner_id)["session"]["step"] == 3
    tmp_db.log_event(learner_id, "Practise", "twin", "score_answers", "done")
    done = main.get_growth(learner_id)["session"]
    assert done["sessions_done"] == 1 and done["step"] == 1
    assert done["just_completed"] is True
    assert main.get_growth(learner_id)["daily"]["sessions"] == 1


def test_short_paragraph_does_not_start_session(tmp_db):
    learner_id = tmp_db.create_learner("T", "10", "English", "Malayalam")
    tmp_db.save_draft(learner_id, "Too short.", "")
    session = main.get_growth(learner_id)["session"]
    assert session["step"] == 1 and session["started"] is True


def test_named_levels_and_session_strings():
    api = (ROOT / "frontend" / "src" / "api.js").read_text(encoding="utf-8")
    assert "LEVEL_NAMES" in api and "Upper-Intermediate" in api
    home = (ROOT / "frontend" / "src" / "screens" / "Home.jsx").read_text(
        encoding="utf-8")
    assert "levelName(levels[skill])" in home
    assert "Today" in home and "session" in home
    assert "Continue today" in home and "Session complete" in home
    assert "sessions today" in home
    for parts in [("components", "SkillBars.jsx"), ("screens", "Learn.jsx"),
                  ("screens", "MyGrowth.jsx"), ("screens", "Practice.jsx"),
                  ("screens", "Write.jsx"), ("screens", "Teacher.jsx")]:
        src = (ROOT / "frontend" / "src" / Path(*parts)).read_text(
            encoding="utf-8")
        assert "levelName(" in src, parts
