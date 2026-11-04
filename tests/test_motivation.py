"""Motivation layer: twin message, fixes, tips, goal, polish, celebrations."""
import json
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import learner_store as store  # noqa: E402
import main  # noqa: E402

EXAMPLE = "I like plants. plants give water and keep climate well"
EMOJI = re.compile("[\U0001F31F\U0001F44D\U0001F4AA\U0001F331"
                   "\U0000270F\uFE0F\U0001F44B]")


@pytest.fixture
def tmp_db(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "DB_PATH", tmp_path / "motivation_learners.db")
    monkeypatch.setattr(main, "study_material", lambda skill, n_results=2: [])
    monkeypatch.setattr(main, "_query_guide_chunks",
                        lambda skill, n_results=1: ([], []))
    monkeypatch.setattr(main, "_model_api_key", lambda: None)
    return store


def _learner(tmp_db, name="Meera"):
    return tmp_db.create_learner(name, "10", "English", "Malayalam",
                                 discipline="Sciences")


def _sentences(text):
    return [s for s in re.split(r"[.!?]+", text) if s.strip()]


# --- Twin message ---------------------------------------------------------------
def test_twin_message_bands_use_name_mood_and_one_emoji():
    moods = {"strong": "Outstanding work!", "good": "You're thinking well!",
             "fair": "Good effort - you're getting there!",
             "weak": "Every expert started here. Let's learn from this one!"}
    for band, mood in moods.items():
        msg = main._twin_message("Meera", band, "fish is dying")
        assert mood in msg and "Meera" in msg
        assert 2 <= len(_sentences(msg)) <= 3, (band, msg)
        assert len(EMOJI.findall(msg)) == 1, (band, msg)
        assert "fish is dying" in msg
        assert main._uses_simple_english(msg), (band, msg)
        assert main._has_generic_praise(msg) is None, (band, msg)


def test_twin_message_without_quote_stays_honest():
    msg = main._twin_message("Meera", "fair", None)
    assert "Meera" in msg and msg.count("Meera") == 1
    assert 2 <= len(_sentences(msg)) <= 3


# --- Grammar fixes ---------------------------------------------------------------
def test_grammar_fix_rules_catch_real_errors():
    text = ("plants need sun. I like it when i read. "
            "The the line has a error. Well.Done. I recieve it.")
    fixes = main._grammar_fixes(text)
    assert len(fixes) == 3  # capped
    for fix in fixes:
        assert fix["wrong"] in text
        assert fix["right"] != fix["wrong"]
        assert fix["rule"].strip()
    assert fixes[0]["right"].startswith("Plants")
    assert " I " in fixes[1]["right"]


def test_grammar_fixes_cap_at_three_and_stay_simple():
    text = "one. two. three. four. five."
    fixes = main._grammar_fixes(text)
    assert len(fixes) == 3
    for fix in fixes:
        assert fix["wrong"] in text
        assert main._uses_simple_english(fix["rule"])
        assert main._uses_simple_english(fix["right"])


def test_vocab_tips_only_use_their_words():
    tips = main._vocab_tips("It is very nice and good.")
    assert 1 <= len(tips) <= 2
    assert tips[0]["word"] in "it is very nice and good."
    assert main._vocab_tips("Plants photosynthesize daily.") == []


def test_motivation_card_shape_and_critical_tip():
    card = main._motivation_card(
        "Meera", "fair", {"quote": "fish is dying", "line": "x"},
        "Fish need rivers. Rivers carry fish far.",
        ["Make your first sentence say your main idea."], "evaporation",
        "Next goal: Make your first sentence say your main idea.")
    assert set(card) == {"twin_message", "grammar_fixes", "vocab_tips",
                         "improve", "critical_tip", "next_goal"}
    assert "fish" in card["critical_tip"]  # linked to their topic
    assert card["improve"] == ["Make your first sentence say your main idea."]


# --- Write path -------------------------------------------------------------------
def test_diagnose_serves_motivation_with_name_and_band(tmp_db):
    learner_id = _learner(tmp_db)
    draft_id = store.save_draft(learner_id, EXAMPLE, "")
    res = main.post_diagnose(main.DiagnoseIn(learner_id=learner_id,
                                             draft_id=draft_id))
    card = res["feedback"]["motivation"]
    assert "Meera" in card["twin_message"]
    assert "Good effort - you're getting there!" in card["twin_message"]
    assert len(card["grammar_fixes"]) >= 1
    assert all(f["wrong"] in EXAMPLE for f in card["grammar_fixes"])
    assert 1 <= len(card["improve"]) <= 3
    assert card["next_goal"].startswith("Next goal: ")
    assert main.verify(
        "feedback", main._feedback_verify_payload(res["feedback"], EXAMPLE)
    )["pass"]


def test_demo_motivation_uses_fixed_layout(tmp_db, monkeypatch):
    monkeypatch.setenv("DEMO_MODE", "true")
    monkeypatch.setattr(main, "_model_api_key", lambda: "K")
    learner_id = _learner(tmp_db)
    draft_id = store.save_draft(learner_id, main.DEMO_WEAK_PARAGRAPH, "")
    res = main.post_diagnose(main.DiagnoseIn(learner_id=learner_id,
                                             draft_id=draft_id))
    card = res["feedback"]["motivation"]
    assert len(card["grammar_fixes"]) == 3
    assert card["vocab_tips"][0]["word"] == "very"
    assert "Make your first sentence say your main idea." in card["improve"]
    assert "plastic" in card["critical_tip"]
    assert card["next_goal"].startswith("Next goal: ")
    assert "Meera" in card["twin_message"]  # profile name, live built
    assert "Every expert started here" in card["twin_message"]
    assert main.verify(
        "feedback", main._feedback_verify_payload(
            res["feedback"], main.DEMO_WEAK_PARAGRAPH))["pass"]
    improved_id = store.save_draft(learner_id, main.DEMO_IMPROVED_PARAGRAPH,
                                   "")
    again = main.post_diagnose(main.DiagnoseIn(learner_id=learner_id,
                                               draft_id=improved_id))
    assert again["feedback"]["motivation"]["grammar_fixes"] == []
    assert main.verify(
        "feedback", main._feedback_verify_payload(
            again["feedback"], main.DEMO_IMPROVED_PARAGRAPH))["pass"]


# --- Assessor path -----------------------------------------------------------------
def _start(tmp_db, learner_id, module="topic-sentences"):
    return main.post_scaffold_start(main.ScaffoldStartIn(
        learner_id=learner_id, discipline="Sciences",
        module=module))["attempt_id"]


def test_assessor_serves_motivation_and_next_action(tmp_db):
    learner_id = _learner(tmp_db)
    attempt = _start(tmp_db, learner_id)
    helped = main.post_scaffold_help(main.ScaffoldHelpIn(
        learner_id=learner_id, attempt_id=attempt,
        attempt_text="Plants need sun to grow tall daily."))
    got = helped["assessment"]
    assert got["next_action"].strip()
    card = got["motivation"]
    assert "Meera" in card["twin_message"]
    assert "Good effort - you're getting there!" in card["twin_message"]
    assert card["next_goal"].startswith("Next goal: ")
    assert main.verify("assessor", {
        "status": got["status"], "feedback": got["feedback"],
        "attempt": "Plants need sun to grow tall daily.",
        "quote": got["quote"], "score": got["score"],
        "grammar_quotes": [f["wrong"] for f in card["grammar_fixes"]],
        "fields": [got["strength"], got["problem"], got["next_action"],
                   card["twin_message"], card["critical_tip"],
                   card["next_goal"]]})["pass"]


def test_assessor_verifier_new_rules():
    base = {"status": "ok", "feedback": "Good line here. Fix that there.",
            "attempt": "Good line here.", "quote": "Good line",
            "score": 1}
    assert main.verify("assessor", base)["pass"] is True
    assert "grammar-quotes" in main.verify(
        "assessor", base | {"grammar_quotes": ["zebras drink lava"]}
    )["failed"]
    assert "simple-english" in main.verify(
        "assessor", base | {"fields": ["We must facilitate better outcomes."]}
    )["failed"]
    assert "no-generic-praise" in main.verify(
        "assessor", base | {"fields": ["Excellent work on this line."]}
    )["failed"]


def test_demo_assessor_carries_motivation(tmp_db, monkeypatch):
    monkeypatch.setenv("DEMO_MODE", "true")
    monkeypatch.setattr(main, "_model_api_key", lambda: "K")
    learner_id = _learner(tmp_db)
    attempt = _start(tmp_db, learner_id)
    helped = main.post_scaffold_help(main.ScaffoldHelpIn(
        learner_id=learner_id, attempt_id=attempt,
        attempt_text=main.DEMO_ASSESS_ATTEMPT))
    card = helped["assessment"]["motivation"]
    assert "Meera" in card["twin_message"]
    assert helped["assessment"]["next_action"].strip()


# --- Polish --------------------------------------------------------------------------
def _two_drafts(tmp_db, learner_id):
    first = store.save_draft(learner_id, "I like plants.", "")
    second = store.save_draft(
        learner_id, "I like plants because they clean the air.", "")
    return first, second


def test_polish_rewrites_after_rewrite(tmp_db, monkeypatch):
    learner_id = _learner(tmp_db)
    _, second = _two_drafts(tmp_db, learner_id)
    seen = {}

    def fake_post(url, body, key, timeout):
        seen["timeout"] = timeout
        return {"choices": [{"message": {"content": json.dumps(
            {"polished": "I like plants because they clean the air."})}}]}

    monkeypatch.setattr(main, "_model_api_key", lambda: "K")
    monkeypatch.setattr(main, "_spark_post", fake_post)
    res = main.post_polish(main.PolishIn(learner_id=learner_id,
                                         draft_id=second))
    assert res["ok"] is True
    assert res["polished"].strip()
    assert seen["timeout"] == main.SPARK_TIMEOUT_SLOW == 40


def test_polish_locked_before_rewrite_and_falls_back(tmp_db, monkeypatch):
    learner_id = _learner(tmp_db)
    only = store.save_draft(learner_id, "I like plants.", "")
    res = main.post_polish(main.PolishIn(learner_id=learner_id, draft_id=only))
    assert res["ok"] is False
    assert "Rewrite your paragraph first" in res["message"]
    _, second = _two_drafts(tmp_db, learner_id)
    res = main.post_polish(main.PolishIn(learner_id=learner_id,
                                         draft_id=second))
    assert res["ok"] is False  # no key: honest fallback
    assert "unavailable right now" in res["message"]


def test_polish_rejects_wrong_sizes(tmp_db, monkeypatch):
    learner_id = _learner(tmp_db)
    _, second = _two_drafts(tmp_db, learner_id)

    def fake_post(url, body, key, timeout):
        return {"choices": [{"message": {"content": json.dumps(
            {"polished": "Plants."})}}]}

    monkeypatch.setattr(main, "_model_api_key", lambda: "K")
    monkeypatch.setattr(main, "_spark_post", fake_post)
    res = main.post_polish(main.PolishIn(learner_id=learner_id,
                                         draft_id=second))
    assert res["ok"] is False  # far too short: rejected, then fallback


# --- Growth: daily goal ----------------------------------------------------------------
def test_growth_reports_daily_goal(tmp_db):
    learner_id = _learner(tmp_db)
    assert main.get_growth(learner_id)["daily"] == {"paragraphs": 0,
                                                    "target": 3}
    store.save_draft(learner_id, "One.", "")
    store.save_draft(learner_id, "Two.", "")
    assert main.get_growth(learner_id)["daily"] == {"paragraphs": 2,
                                                    "target": 3}


# --- UI strings ---------------------------------------------------------------------------
def _src(*parts):
    return (ROOT / "frontend" / "src" / Path(*parts)).read_text(encoding="utf-8")


def test_motivation_ui_strings():
    card = _src("components", "FeedbackCard.jsx")
    for needle in ("twin_message", "What went well", "Grammar fixes",
                   "Word tips", "Think deeper", "Polished version",
                   "modelSentence", "Compare with a polished version"):
        assert needle in card
    assert card.count("✏️") == 1
    write = _src("screens", "Write.jsx")
    assert "fetchPolish" in write and "polishUnlocked" in write
    assert "This is your starting point." in write
    assert "api.polish" in write
    assert "polish" in _src("api.js") and "/polish" in _src("api.js")


def test_celebration_ui_strings():
    confetti = _src("components", "Confetti.jsx")
    assert "3000" in confetti
    css = _src("styles.css")
    assert "confetti-fall" in css and "prefers-reduced-motion" in css
    practice = _src("screens", "Practice.jsx")
    assert "Confetti" in practice
    home = _src("screens", "Home.jsx")
    assert "Confetti" in home and "Daily goal:" in home
    assert "paragraphs today" in home
    assert "Goodbye for now" in home
