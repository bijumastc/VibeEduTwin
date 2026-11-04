"""My Growth: delete-my-data wipes the learner back to fresh."""
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
    monkeypatch.setattr(store, "DB_PATH", tmp_path / "growth_learners.db")
    return store


def test_delete_data_clears_everything(tmp_db, monkeypatch):
    wiped = []
    monkeypatch.setattr(store, "delete_writing_samples", wiped.append)
    learner_id = tmp_db.create_learner("T", "10", "English", "Malayalam",
                                       discipline="Medicine")
    tmp_db.save_draft(learner_id, "x", "")
    tmp_db.save_skill_scores(learner_id, {"Paragraphing": 50})
    tmp_db.save_practice_result(learner_id, "Paragraphing", 100)
    tmp_db.log_event(learner_id, "Write", "twin", "x", "y")
    main.ISSUED_SETS["gone-set"] = {"learner_id": learner_id}
    main.SCAFFOLD_ATTEMPTS["gone-attempt"] = {"learner_id": learner_id}
    other = tmp_db.create_learner("O", "10", "English", "Malayalam")
    tmp_db.save_draft(other, "keep", "")
    main.ISSUED_SETS["kept-set"] = {"learner_id": other}
    try:
        res = main.post_delete_data(main.DeleteDataIn(learner_id=learner_id))
    finally:
        main.ISSUED_SETS.pop("gone-set", None)
        main.SCAFFOLD_ATTEMPTS.pop("gone-attempt", None)
        main.ISSUED_SETS.pop("kept-set", None)
    assert res["ok"] is True
    assert wiped == [learner_id]
    assert tmp_db.get_learner(learner_id)["discipline"] == "Sciences"
    assert tmp_db.get_drafts(learner_id) == []
    assert tmp_db.get_skill_scores(learner_id) == []
    assert tmp_db.get_practice_results(learner_id, "Paragraphing") == []
    assert tmp_db.get_events(learner_id) == []
    assert "gone-set" not in main.ISSUED_SETS
    assert "gone-attempt" not in main.SCAFFOLD_ATTEMPTS
    assert len(tmp_db.get_drafts(other)) == 1  # others untouched


def test_delete_data_rejects_unknown_learner(tmp_db):
    with pytest.raises(HTTPException) as exc:
        main.post_delete_data(main.DeleteDataIn(learner_id=999))
    assert exc.value.status_code == 404


def test_delete_data_ui_strings():
    growth = (ROOT / "frontend" / "src" / "screens" / "MyGrowth.jsx").read_text(
        encoding="utf-8")
    assert "Delete my data" in growth
    assert "Yes, delete everything" in growth
    assert "Keep my data" in growth
    assert "cannot be undone" in growth
    assert "api.deleteData()" in growth
    assert "LeveledUp.clear()" in growth
    api = (ROOT / "frontend" / "src" / "api.js").read_text(encoding="utf-8")
    assert "deleteData" in api and "clear" in api
