"""Home loads on a fresh learner; the client reports real errors."""
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


def test_api_client_reports_target_and_real_errors():
    api = (ROOT / "frontend" / "src" / "api.js").read_text(encoding="utf-8")
    assert "Cannot reach the backend at ${API_URL}" in api
    assert "invalid response" in api
    assert "python scripts/reset_demo.py" in api
