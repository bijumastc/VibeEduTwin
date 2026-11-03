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
