"""Unified Verifier (docs/plan.md) + How-it-decided panel."""
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
    monkeypatch.setattr(store, "DB_PATH", tmp_path / "verifier_learners.db")
    return store


def _learner(tmp_db):
    return tmp_db.create_learner("Test", "10", "English", "Malayalam",
                                 discipline="Sciences")


def _sourced_item(**over):
    item = {"id": "t1", "type": "mcq", "prompt": "Pick one.",
            "options": ["A) first", "B) second"], "answer": "A",
            "explanation": "Because.", "source": "guide.pdf",
            "chapter": "Ch 1", "license": "CC BY"}
    item.update(over)
    return item


# --- Checklist doc ---------------------------------------------------------
def test_plan_checklist_matches_verifier_rules():
    plan = (ROOT / "docs" / "plan.md").read_text(encoding="utf-8")
    for rule in ("not-empty", "non-empty", "unique-id", "no-generic-praise",
                 "no-invented-examples", "valid-type", "min-options",
                 "has-answer", "answer-matches-option", "has-explanation",
                 "grounded-in-excerpt", "has-controlling-idea",
                 "not-task-topic", "grounded-in-excerpts", "valid-score",
                 "feedback-shape", "quotes-learner"):
        assert f"`{rule}`" in plan, rule
    assert '"pass"' in plan and '"failed"' in plan and '"fix"' in plan
    assert "No invented examples" in plan


# --- JSON-only replies -------------------------------------------------------
def test_verify_replies_only_json():
    verdict = main.verify("twin_reply", "Read only your first line.")
    assert set(verdict) == {"pass", "failed", "fix"}
    assert verdict == {"pass": True, "failed": [], "fix": ""}


def test_verify_rejects_unknown_kind():
    with pytest.raises(ValueError):
        main.verify("essay", "text")


# --- Twin replies ---------------------------------------------------------------
def test_twin_reply_rejects_invented_example():
    verdict = main.verify(
        "twin_reply", "For example, 'Plants need sunlight every day.' Study it.",
        {"message": "help me"})
    assert verdict["pass"] is False
    assert verdict["failed"] == ["no-invented-examples"]
    assert "knowledge base" in verdict["fix"]


def test_twin_reply_allows_learner_words_starters_ellipsis():
    quoted = main.verify(
        "twin_reply", 'The main problem in "She go to school daily." is grammar.',
        {"message": "She go to school daily"})
    assert quoted["pass"] is True
    starter = main.verify("twin_reply", "Start with this: 'She ___ to school daily.'")
    assert starter["pass"] is True
    bare = main.verify("twin_reply", "Swap one chatty word like 'very' today.")
    assert bare["pass"] is True


def test_twin_reply_still_catches_generic_praise():
    verdict = main.verify("twin_reply", "Great job on that line!")
    assert verdict["pass"] is False
    assert "no-generic-praise" in verdict["failed"]
    assert main.verify_twin_reply("") == ["Reply is empty."]


# --- Practice items --------------------------------------------------------------
def test_item_requires_book_source():
    assert main.verify("practice_item", _sourced_item())["pass"] is True
    verdict = main.verify("practice_item", _sourced_item(source=""))
    assert verdict["pass"] is False
    assert verdict["failed"] == ["no-invented-examples"]


def test_set_reports_item_failures_with_fix():
    items = [_sourced_item(), _sourced_item(id="t1", source="")]
    verdict = main.verify("practice_set", items)
    assert verdict["pass"] is False
    assert "item 2: unique-id" in verdict["failed"]
    assert "item 2: no-invented-examples" in verdict["failed"]
    assert verdict["fix"]
    assert main.verify("practice_set", [])["failed"] == ["non-empty"]


def test_legacy_wrappers_keep_messages():
    assert main.verify_twin_reply("Nice work, excellent!") == [
        "No generic praise: reply contains 'excellent'."]
    assert main.verify_practice_set([]) == ["Practice set is empty."]
    dup = [_sourced_item(), _sourced_item()]
    assert "item 2: missing or duplicate id." in main.verify_practice_set(dup)


def test_publish_rejects_sourceless_items(tmp_db):
    with pytest.raises(HTTPException) as exc:
        main.post_teacher_publish(main.TeacherPublishIn(
            request="r", skill="Grammar", level=1,
            items=[_sourced_item(source="")]))
    assert exc.value.status_code == 400
    assert "knowledge base" in exc.value.detail


def test_practice_still_serves_curated_bank(tmp_db):
    body = main.get_practice(_learner(tmp_db))
    assert body["published"] is False
    assert len(body["items"]) >= 2


# --- Events + panel ---------------------------------------------------------------
def test_events_endpoint_returns_at_most_six_lines(tmp_db):
    learner_id = _learner(tmp_db)
    for i in range(8):
        store.log_event(learner_id, f"Step{i}", "twin", f"tool{i}", f"result{i}")
    res = main.get_events(learner_id)
    assert len(res["events"]) == 6
    assert res["events"][0]["step"] == "Step7"
    assert set(res["events"][0]) == {"step", "agent", "tool", "result"}
    assert len(main.get_events(learner_id, limit=99)["events"]) <= 6
    with pytest.raises(HTTPException) as exc:
        main.get_events(999)
    assert exc.value.status_code == 404


def test_panel_is_collapsed_plain_text_with_six_line_cap():
    panel = (ROOT / "frontend" / "src" / "components" / "HowItDecided.jsx").read_text(
        encoding="utf-8")
    assert "<details" in panel and "open=" not in panel.replace("openModule", "")
    assert "How it decided" in panel
    assert "slice(0, 6)" in panel
    assert "e.step" in panel and "e.agent" in panel and "e.tool" in panel and "e.result" in panel
    for screen in ("Write.jsx", "Practice.jsx"):
        content = (ROOT / "frontend" / "src" / "screens" / screen).read_text(encoding="utf-8")
        assert "HowItDecided" in content
    api = (ROOT / "frontend" / "src" / "api.js").read_text(encoding="utf-8")
    assert "events: ()" in api and "/events?" in api
