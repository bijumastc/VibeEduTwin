"""Check section: self-rated topic-sentence check with an improved line."""
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
    monkeypatch.setattr(store, "DB_PATH", tmp_path / "check_learners.db")
    return store


def _learner(tmp_db, discipline="Technology"):
    return tmp_db.create_learner("Test", "10", "English", "Malayalam",
                                 discipline=discipline)


def _start(learner_id, discipline="Technology", module="topic-sentences"):
    return main.post_scaffold_start(main.ScaffoldStartIn(
        learner_id=learner_id, discipline=discipline, module=module))


def _check(learner_id, attempt_id, text, self_rating):
    return main.post_scaffold_check(main.ScaffoldCheckIn(
        learner_id=learner_id, attempt_id=attempt_id, text=text,
        self_rating=self_rating))


def test_good_sentence_rated_good(tmp_db):
    lid = _learner(tmp_db)
    view = _start(lid)
    text = main.CHECK_TOPIC_MODELS["Technology"]
    res = _check(lid, view["attempt_id"], text, "good")
    assert res["verdict"] == "good"
    assert res["fails"] == []
    assert res["improved"] == text
    assert "checked yourself right" in res["message"]
    assert "main idea" in res["rule"]
    assert res["fixes"] and res["topic"] == "password safety"


def test_good_sentence_rated_bad_is_encouraged(tmp_db):
    lid = _learner(tmp_db)
    view = _start(lid)
    res = _check(lid, view["attempt_id"],
                 main.CHECK_TOPIC_MODELS["Technology"], "bad")
    assert res["verdict"] == "good"
    assert "too strict" in res["message"]


def test_vague_line_gets_same_topic_model(tmp_db):
    lid = _learner(tmp_db)
    view = _start(lid)
    res = _check(lid, view["attempt_id"],
                 "There are many things about password safety.", "bad")
    assert res["verdict"] == "needs_work"
    assert any("announces" in f for f in res["fails"])
    assert any("Say what exactly" in f for f in res["fixes"])
    assert res["improved"] == main.CHECK_TOPIC_MODELS["Technology"]
    assert "honest check" in res["message"]


def test_rated_good_but_weak_stays_kind(tmp_db):
    lid = _learner(tmp_db)
    view = _start(lid)
    res = _check(lid, view["attempt_id"],
                 "Password safety is very interesting and nice.", "good")
    assert res["verdict"] == "needs_work"
    assert "closer than" in res["message"]


def test_off_topic_line_names_the_topic(tmp_db):
    lid = _learner(tmp_db)
    view = _start(lid)
    res = _check(lid, view["attempt_id"],
                 "Cricket is my favourite game.", "bad")
    assert res["verdict"] == "needs_work"
    assert any("password safety" in f for f in res["fails"])


def test_mechanics_slip_returns_cleaned_own_line(tmp_db):
    lid = _learner(tmp_db)
    view = _start(lid)
    res = _check(lid, view["attempt_id"],
                 "password safety explains why small leaks become big thefts",
                 "bad")
    assert res["verdict"] == "needs_work"
    assert any("mechanics" in f.lower() for f in res["fails"])
    assert res["improved"] == \
        "Password safety explains why small leaks become big thefts."
    assert res["improved_label"] == "Your line, cleaned up:"


def test_spelling_slip_is_fixed_in_improved(tmp_db):
    lid = _learner(tmp_db)
    view = _start(lid)
    res = _check(lid, view["attempt_id"],
                 "Password safety explains why writting passwords down is risky.",
                 "bad")
    assert res["verdict"] == "needs_work"
    assert "writing passwords" in res["improved"]


def test_too_short_and_two_sentences_fail(tmp_db):
    lid = _learner(tmp_db)
    view = _start(lid)
    short = _check(lid, view["attempt_id"], "very good", "bad")
    assert short["verdict"] == "needs_work"
    assert short["improved"] == main.CHECK_TOPIC_MODELS["Technology"]
    two = _check(lid, view["attempt_id"],
                 "Password safety matters. It stops thieves daily now.", "bad")
    assert two["verdict"] == "needs_work"
    assert any("one complete sentence" in f for f in two["fails"])


def test_authored_models_pass_themselves(tmp_db):
    lid = _learner(tmp_db)
    for discipline, model in main.CHECK_TOPIC_MODELS.items():
        view = _start(lid, discipline=discipline)
        res = _check(lid, view["attempt_id"], model, "good")
        assert res["verdict"] == "good", discipline


def test_check_guards_module_rating_text_and_attempt(tmp_db):
    lid = _learner(tmp_db)
    view = _start(lid)
    other = _start(lid, module="thesis-statements")
    with pytest.raises(HTTPException) as exc:
        _check(lid, other["attempt_id"], "Some line here.", "good")
    assert exc.value.status_code == 400
    with pytest.raises(HTTPException) as exc:
        _check(lid, view["attempt_id"], "Some line here.", "maybe")
    assert exc.value.status_code == 400
    with pytest.raises(HTTPException) as exc:
        _check(lid, view["attempt_id"], "   ", "good")
    assert exc.value.status_code == 400
    with pytest.raises(HTTPException) as exc:
        _check(lid, "no-such-attempt", "Some line here.", "good")
    assert exc.value.status_code == 404


def test_check_changes_no_score_or_activity(tmp_db):
    lid = _learner(tmp_db)
    before_scores = dict(main.latest_scores(lid))
    before_acts = store.count_activities(lid, "Paragraphing")
    view = _start(lid)
    _check(lid, view["attempt_id"],
           "There are many things about password safety.", "bad")
    assert dict(main.latest_scores(lid)) == before_scores
    assert store.count_activities(lid, "Paragraphing") == before_acts
