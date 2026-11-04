"""Write fallback shows the full card: evidence, strength, model, focus rule."""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import learner_store as store  # noqa: E402
import main  # noqa: E402

HACK = ("hackthons give developers opportunity to experiment with their apps "
        "and they get suggestion")


@pytest.fixture
def tmp_db(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "DB_PATH", tmp_path / "write_fallback.db")
    monkeypatch.setattr(main, "study_material", lambda skill, n_results=2: [])
    monkeypatch.setattr(main, "_query_guide_chunks",
                        lambda skill, n_results=1: ([], []))
    monkeypatch.setattr(main, "_model_api_key", lambda: None)  # fallback path
    return store


def _learner(tmp_db):
    return tmp_db.create_learner("T", "10", "English", "Malayalam",
                                 discipline="Sciences")


def test_fallback_full_card_for_own_paragraph(tmp_db):
    learner_id = _learner(tmp_db)
    res = main.post_diagnose(main.DiagnoseIn(learner_id=learner_id,
                                             content=HACK))
    # Evidence quote under every skill.
    assert [d["skill"] for d in res["skills_details"]] == main.SKILLS
    for detail in res["skills_details"]:
        assert detail["reason"].strip()
        assert detail["evidence"] in HACK
    # Full feedback card.
    card = res["feedback"]
    assert card["strength"] is not None
    assert card["strength"]["quote"] in HACK
    assert card["strength"]["line"].strip()
    assert len(card["problems"]) == 2
    for problem in card["problems"]:
        assert problem["quote"] in HACK
        assert problem["wrong"].strip() and problem["why"].strip()
        assert problem["fix"].strip()
    assert card["problems"][0]["quote"] != card["problems"][1]["quote"]
    assert card["model"] is not None
    assert card["model"]["before"] in HACK
    assert len([s for s in card["model"]["after"].split(".")
                if s.strip()]) == 1
    assert card["model"]["after"] not in HACK or \
        card["model"]["after"].strip() != card["model"]["before"].strip()
    assert card["your_turn"].strip()
    assert main.verify("feedback",
                       main._feedback_verify_payload(card, HACK))["pass"]
    # Future-self voice, never shared struggle.
    assert res["twin_note"].startswith("You will get this: start by ")
    assert "hard too" not in res["twin_note"].lower()
    assert "I found" not in res["twin_note"]
    assert "hard too" not in card["motivation"]["twin_message"].lower()
    # New focus rule: no evidence tried, others not all L3 -> craft skill.
    levels = {s: main.level_for_score(res["scores"][s]) for s in main.SKILLS}
    assert res["weakest"] == main.next_win_skill(levels, HACK)
    assert res["weakest"] != "Using sources"
    assert res["notice"] == main.FALLBACK_NOTICE


def test_no_old_template_lines_remain():
    src = (ROOT / "main.py").read_text(encoding="utf-8")
    assert "I found" not in src
    assert "hard too" not in src


def test_scaffold_start_reports_guided_progress(tmp_db, monkeypatch):
    monkeypatch.setattr(main, "_query_guides",
                        lambda query, n_results=8: ([], []))
    learner_id = _learner(tmp_db)
    view = main.post_scaffold_start(main.ScaffoldStartIn(
        learner_id=learner_id, discipline="Sciences",
        module="topic-sentences"))
    assert view["mode"] == "guided"
    assert view["activities_done"] == 0
    assert view["activities_needed"] == main.GUIDED_ACTIVITIES == 6
    for _ in range(4):
        tmp_db.log_activity(learner_id, "Paragraphing", "write")
    view = main.post_scaffold_start(main.ScaffoldStartIn(
        learner_id=learner_id, discipline="Sciences",
        module="topic-sentences"))
    assert view["activities_done"] == 4
    helped = main.post_scaffold_help(main.ScaffoldHelpIn(
        learner_id=learner_id, attempt_id=view["attempt_id"]))
    assert helped["mode"] == "guided"
    assert helped["activities_done"] == 4


def test_task_card_shows_guided_progress():
    task = (ROOT / "frontend" / "src" / "components" / "ScaffoldTask.jsx"
            ).read_text(encoding="utf-8")
    assert "Guided \u00b7" in task
    assert "activities_needed" in task
    assert "of" in task and "activities" in task
