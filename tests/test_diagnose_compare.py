"""Every diagnosis compares with the previous draft (or starts fresh)."""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import learner_store as store  # noqa: E402
import main  # noqa: E402


@pytest.fixture
def tmp_db(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "DB_PATH", tmp_path / "compare_learners.db")
    monkeypatch.setattr(main, "study_material", lambda skill, n_results=2: [])
    monkeypatch.setattr(main, "_query_guide_chunks", lambda skill, n_results=1: ([], []))
    return store


def test_first_diagnosis_is_starting_point(tmp_db):
    learner_id = tmp_db.create_learner("T", "10", "English", "Malayalam")
    res = main.post_diagnose(main.DiagnoseIn(learner_id=learner_id, content="Nice good."))
    assert res["comparison"] == "This is your starting point."
    for skill in main.SKILLS:
        assert res["level_changes"][skill]["previous"] is None
        assert res["level_changes"][skill]["current"] == \
            main.level_for_score(res["scores"][skill])


def test_second_diagnosis_compares_with_previous(tmp_db):
    learner_id = tmp_db.create_learner("T", "10", "English", "Malayalam")
    first = main.post_diagnose(main.DiagnoseIn(learner_id=learner_id, content="Nice good."))
    second = main.post_diagnose(main.DiagnoseIn(
        learner_id=learner_id,
        content="My favourite festival is Onam because families gather. "
                "First, people lay flower carpets. Finally, all share a feast."))
    assert second["comparison"].startswith(
        ("In your last paragraph", "Like your last paragraph"))
    assert main.verify_twin_reply(second["comparison"]) == []
    for skill in main.SKILLS:
        assert second["level_changes"][skill]["previous"] == \
            main.level_for_score(first["scores"][skill])
        assert second["level_changes"][skill]["current"] == \
            main.level_for_score(second["scores"][skill])


def test_draft_flow_compares_previous_draft(tmp_db):
    learner_id = tmp_db.create_learner("T", "10", "English", "Malayalam")
    draft1 = tmp_db.save_draft(learner_id, "I like holidays. They are fun.", "")
    first = main.post_diagnose(main.DiagnoseIn(learner_id=learner_id, draft_id=draft1))
    assert first["comparison"] == "This is your starting point."
    draft2 = tmp_db.save_draft(
        learner_id, "Onam is Kerala's harvest festival because families gather "
                    "for the feast. First, people lay flower carpets called pookkalam.",
        "")
    second = main.post_diagnose(main.DiagnoseIn(learner_id=learner_id, draft_id=draft2))
    assert "last paragraph" in second["comparison"]
    assert second["level_changes"]["Paragraphing"]["previous"] == \
        main.level_for_score(first["scores"]["Paragraphing"])


def test_compare_note_branches():
    assert main.compare_note("Paragraphing", 1, 2) == (
        "In your last paragraph you had no topic sentence; "
        "this time you have a topic sentence. Make your topic sentence narrower.")
    assert main.compare_note("Paragraphing", 2, 1) == (
        "In your last paragraph you had a topic sentence; "
        "this time you have no topic sentence. "
        "Start with one line that tells the main idea.")
    assert main.compare_note("Paragraphing", 1, 1).startswith("Like your last paragraph")
    assert main.compare_note("Paragraphing", 3, 3).startswith("Like your last paragraph")
    for skill in main.SKILLS:
        for prev, new in [(1, 2), (2, 1), (1, 1), (2, 2), (3, 3)]:
            note = main.compare_note(skill, prev, new)
            assert note and main.verify_twin_reply(note) == [], (skill, prev, new)


def test_write_shows_comparison_and_level_changes():
    write = (ROOT / "frontend" / "src" / "screens" / "Write.jsx").read_text(encoding="utf-8")
    assert "result.comparison" in write and "level_changes" in write
    bars = (ROOT / "frontend" / "src" / "components" / "SkillBars.jsx").read_text(
        encoding="utf-8")
    assert "Level ${" in bars and "→" in bars
