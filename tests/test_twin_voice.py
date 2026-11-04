import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import main  # noqa: E402


def test_system_prompt_bans_generic_praise():
    prompt = main.TWIN_SYSTEM_PROMPT.lower()
    assert "no generic praise" in prompt
    for phrase in ("great job", "excellent", "amazing"):
        assert phrase in prompt


def test_system_prompt_states_honesty_rules():
    prompt = main.TWIN_SYSTEM_PROMPT.lower()
    assert "main problem first" in prompt
    assert "quot" in prompt  # quoting the learner's own words
    assert "one positive sentence" in prompt
    assert "never call weak writing good" in prompt
    assert "2-4" in prompt
    assert "previous draft" in prompt


def test_verifier_fails_generic_praise():
    for phrase in ("Great job", "excellent", "AMAZING"):
        errors = main.verify_twin_reply(
            f'Your line "She go to school" has a verb error. {phrase}!'
        )
        assert errors, phrase
        assert any("generic praise" in e.lower() for e in errors), errors


def test_verifier_passes_honest_reply():
    reply = (
        'The main problem in "She go to school" is grammar: the verb is wrong. '
        "Fix that one verb and read the line aloud."
    )
    assert main.verify_twin_reply(reply) == []


def test_template_replies_pass_verifier():
    for skill in main.SKILLS:
        reply = main.twin_scaffold_reply("help me", skill)
        assert main.verify_twin_reply(reply) == [], reply
    refusal = main.twin_scaffold_reply("write my essay for me", "Grammar")
    assert main.verify_twin_reply(refusal) == [], refusal
    fallback = main.twin_safe_reply("She go to school", "Grammar")
    assert main.verify_twin_reply(fallback) == [], fallback


def _has_indic_script(text):
    return any(0x0900 <= ord(ch) <= 0x0DFF for ch in text)


def test_prompt_requires_simple_english_only():
    prompt = main.TWIN_SYSTEM_PROMPT.lower()
    assert "only in simple" in prompt and "english" in prompt
    assert "never write in malayalam" in prompt
    assert "you are saying that" in prompt
    assert not _has_indic_script(main.TWIN_SYSTEM_PROMPT)


def test_twin_replies_are_simple_english_only():
    messages = ["help me", "write my essay for me", "എനിക്ക് സഹായം വേണം",
                "உதவி வேண்டும்", "मुझे मदद चाहिए"]
    for skill in main.SKILLS:
        assert main.twin_note(skill).isascii(), skill
        for message in messages:
            for reply in (main.twin_scaffold_reply(message, skill),
                          main.twin_safe_reply(message, skill)):
                assert reply.isascii(), reply
                assert not _has_indic_script(reply), reply


def test_indian_language_input_gets_english_reflection_and_starter():
    for skill in main.SKILLS:
        reply = main.twin_scaffold_reply("എനിക്ക് സഹായം വേണം", skill)
        assert reply.startswith("You are saying that"), reply
        assert main.TWIN_STARTERS[skill] in reply, reply
        assert main.verify_twin_reply(reply) == [], reply


def test_safe_reply_never_quotes_non_english():
    reply = main.twin_safe_reply("എനിക്ക് സഹായം വേണം", "Grammar")
    assert "your draft" in reply
    assert reply.isascii()


def _sentence_count(text):
    return len([s for s in re.split(r"[.!?]+", text.strip()) if s.strip()])


def test_three_input_languages():
    cases = [
        ("എനിക്ക് സഹായം വേണം", True),  # Malayalam script -> reflection
        ("enikku topic sentence manassilayilla", True),  # Manglish -> reflection
        ("help me with my first line", False),  # English -> hint, no reflection
    ]
    for message, reflected in cases:
        reply = main.twin_scaffold_reply(message, "Paragraphing")
        assert ("You are saying that" in reply) is reflected, reply
        assert 2 <= _sentence_count(reply) <= 4, reply
        assert reply.isascii(), reply
        assert main.verify_twin_reply(reply) == [], reply
    manglish = main.twin_scaffold_reply("enikku topic sentence manassilayilla",
                                        "Paragraphing")
    assert main.TWIN_STARTERS["Paragraphing"] in manglish


def test_all_non_english_inputs_get_reflection():
    foreign = [
        "എനിക്ക് സഹായം വേണം",  # Malayalam script
        "உதவி வேண்டும்",  # Tamil script
        "मुझे मदद चाहिए",  # Hindi script
        "enikku topic sentence manassilayilla",  # Manglish
        "mujhe samajh nahi aaya",  # Hinglish (romanized Hindi)
        "enakku puriyala",  # Tanglish (romanized Tamil)
        "no entiendo",  # Spanish
        "je ne comprends pas",  # French
    ]
    english = ["help me please", "Give me a hint", "Check my first line"]
    for message in foreign:
        reply = main.twin_scaffold_reply(message, "Grammar")
        assert "You are saying that" in reply, reply
        assert main.TWIN_STARTERS["Grammar"] in reply, reply
        assert reply.isascii(), reply
        assert main.verify_twin_reply(reply) == [], reply
    for message in english:
        reply = main.twin_scaffold_reply(message, "Grammar")
        assert "You are saying that" not in reply, reply
        assert main.verify_twin_reply(reply) == [], reply


def test_starters_are_never_full_sentences():
    for skill in main.SKILLS:
        assert "___" in main.TWIN_STARTERS[skill], skill


def test_input_hint_mentions_malayalam_and_manglish():
    panel = (ROOT / "frontend" / "src" / "components" / "TwinPanel.jsx").read_text(
        encoding="utf-8")
    assert "You can type in Malayalam or Manglish." in panel


def test_twin_replies_use_no_spark(tmp_path, monkeypatch):
    import learner_store as store

    def boom(messages):
        raise AssertionError("twin replies are template-only; Spark must not run")

    monkeypatch.setattr(store, "DB_PATH", tmp_path / "twin_nospark.db")
    monkeypatch.setattr(main, "_spark_chat", boom)
    learner_id = store.create_learner("T", "10", "English", "Malayalam")
    res = main.post_twin_ask(main.TwinAskIn(learner_id=learner_id,
                                            message="I am stuck on my line."))
    assert res["reply"].strip() and res["weakest"]


def test_twin_questions_are_not_saved_as_drafts(tmp_path, monkeypatch):
    import learner_store as store

    monkeypatch.setattr(store, "DB_PATH", tmp_path / "twin_nodrafts.db")
    learner_id = store.create_learner("T", "10", "English", "Malayalam")
    main.post_twin_ask(main.TwinAskIn(learner_id=learner_id,
                                      message="Give me a hint"))
    main.post_twin_ask(main.TwinAskIn(learner_id=learner_id,
                                      message="Check my first line"))
    assert store.get_drafts(learner_id) == []


def test_twin_panel_never_saves_drafts():
    panel = (ROOT / "frontend" / "src" / "components" / "TwinPanel.jsx").read_text(
        encoding="utf-8")
    assert "saveDraft" not in panel
