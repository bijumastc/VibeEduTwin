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
    monkeypatch.setattr(main, "_model_api_key", lambda: None)  # heuristic path
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


# --- Spark Diagnoser (fixed rubric; heuristic fallback + sanity check) ---------
def _diagnose_reply(levels, evidence):
    import json
    return json.dumps({
        skill: {"level": levels.get(skill, 3),
                "reason": f"{skill} checked.",
                "evidence": evidence}
        for skill in main.SKILLS})


def _spark_events(learner_id, tool):
    return [r for r in store.get_events(learner_id) if r["tool"] == tool]


def test_diagnose_rubric_is_fixed_in_code():
    assert set(main.DIAGNOSE_RUBRIC) == set(main.SKILLS)
    for skill, levels in main.DIAGNOSE_RUBRIC.items():
        assert len(levels) == 5, skill
        assert all(isinstance(d, str) and d.strip() for d in levels), skill
    for level, score in main.DIAGNOSE_LEVEL_SCORES.items():
        assert main.level_for_score(score) == level


def test_diagnose_rubric_matches_fixed_plan_text():
    assert main.DIAGNOSE_RUBRIC == {
        "Grammar": [
            "Frequent errors block meaning.",
            "Many errors; meaning mostly clear.",
            "Some errors; meaning clear.",
            "Few, minor errors.",
            "Rare, minor errors.",
        ],
        "Vocabulary": [
            "Everyday words only, often repeated.",
            "Mostly everyday words; a few academic words.",
            "Some academic words, sometimes misused.",
            "Academic and subject terms, mostly used correctly.",
            "Precise academic and subject terms.",
        ],
        "Sentence structure": [
            "Short or run-on sentences.",
            "Mostly simple sentences; some joined correctly.",
            "Mix of simple and compound sentences.",
            "Varied sentences with few errors.",
            "Varied, controlled sentences.",
        ],
        "Paragraphing": [
            "No clear topic sentence; ideas listed.",
            "Topic sentence present but vague.",
            "Clear topic sentence with some support.",
            "Clear topic sentence, relevant support, some links.",
            "Clear topic sentence, support, and a link to the next idea.",
        ],
        "Argument": [
            "Opinions without reasons.",
            "A claim with one weak reason.",
            "A claim with reasons but little evidence.",
            "A claim with reasons and evidence.",
            "Claim, evidence, and a counterpoint answered.",
        ],
        "Using sources": [
            "No sources.",
            "A source mentioned vaguely, no citation.",
            "A source cited, format inconsistent.",
            "Correct citation, some copied wording.",
            "Correct paraphrase and citation.",
        ],
        "Academic tone": [
            "Conversational.",
            "Mostly conversational, a few formal phrases.",
            "Mix of formal and informal.",
            "Mostly formal and objective.",
            "Formal, objective, and appropriately hedged.",
        ],
    }


def test_rubric_endpoint_serves_fixed_rubric():
    res = main.get_rubric()
    assert [s["skill"] for s in res["skills"]] == main.SKILLS
    for entry in res["skills"]:
        assert entry["levels"] == main.DIAGNOSE_RUBRIC[entry["skill"]]


def test_how_im_scored_ui_strings():
    write = (ROOT / "frontend" / "src" / "screens" / "Write.jsx").read_text(
        encoding="utf-8")
    assert "HowScored" in write
    teacher = (ROOT / "frontend" / "src" / "screens" / "Teacher.jsx").read_text(
        encoding="utf-8")
    assert "HowScored" in teacher
    comp = (ROOT / "frontend" / "src" / "components" / "HowScored.jsx").read_text(
        encoding="utf-8")
    assert "How I'm scored" in comp and "api.rubric()" in comp
    api = (ROOT / "frontend" / "src" / "api.js").read_text(encoding="utf-8")
    assert "rubric" in api


def test_spark_diagnosis_maps_levels_and_logs_provenance(tmp_db, monkeypatch):
    text = "Onam is Kerala's harvest festival because families gather."
    calls = []

    def fake_chat(messages, temperature=None):
        calls.append((messages, temperature))
        return _diagnose_reply({"Grammar": 1, "Argument": 4}, "families gather")

    monkeypatch.setattr(main, "_model_api_key", lambda: "K")
    monkeypatch.setattr(main, "_spark_chat", fake_chat)
    learner_id = tmp_db.create_learner("T", "10", "English", "Malayalam")
    res = main.post_diagnose(main.DiagnoseIn(learner_id=learner_id, content=text))
    assert len(calls) == 1
    assert calls[0][1] == 0  # temperature 0
    prompt = calls[0][0][-1]["content"]
    assert "Discipline: Sciences" in prompt
    assert "L1:" in prompt and "L5:" in prompt and text in prompt
    assert res["scores"]["Grammar"] == 10
    assert res["scores"]["Argument"] == 70
    assert res["weakest"] == "Grammar"  # weakest chosen in code, min level
    assert res["level"] == 1
    assert res["comparison"] == "This is your starting point."
    logged = _spark_events(learner_id, "diagnose-spark")
    assert len(logged) == 1
    assert "Diagnosed by Muse Spark" in logged[0]["result"]
    assert "weakest=Grammar" in logged[0]["result"]


def test_diagnosis_rejects_bad_evidence_and_retries(tmp_db, monkeypatch):
    text = "Onam is Kerala's harvest festival because families gather."
    replies = [_diagnose_reply({}, "zebras drink lava"),
               _diagnose_reply({"Grammar": 2}, "families gather")]
    calls = []

    def fake_chat(messages, temperature=None):
        calls.append(messages)
        return replies[len(calls) - 1]

    monkeypatch.setattr(main, "_model_api_key", lambda: "K")
    monkeypatch.setattr(main, "_spark_chat", fake_chat)
    learner_id = tmp_db.create_learner("T", "10", "English", "Malayalam")
    res = main.post_diagnose(main.DiagnoseIn(learner_id=learner_id, content=text))
    assert len(calls) == 2  # invented evidence rejected, second try used
    assert res["scores"]["Grammar"] == 30
    assert res["weakest"] == "Grammar"
    assert _spark_events(learner_id, "diagnose-spark")


def test_diagnosis_exhausts_retries_then_heuristic(tmp_db, monkeypatch):
    calls = []

    def bad_chat(messages, temperature=None):
        calls.append(messages)
        return "nope"

    monkeypatch.setattr(main, "_model_api_key", lambda: "K")
    monkeypatch.setattr(main, "_spark_chat", bad_chat)
    learner_id = tmp_db.create_learner("T", "10", "English", "Malayalam")
    text = "Onam is Kerala's harvest festival because families gather."
    res = main.post_diagnose(main.DiagnoseIn(learner_id=learner_id, content=text))
    assert len(calls) == 3  # 1 initial + 2 regens
    assert res["scores"] == main.diagnose_text(text)
    assert not _spark_events(learner_id, "diagnose-spark")
    assert _spark_events(learner_id, "heuristic-scorer")


def test_no_key_keeps_heuristic_diagnosis(tmp_db, monkeypatch):
    def boom(messages, temperature=None):
        raise AssertionError("no key: Spark must not run")

    monkeypatch.setattr(main, "_model_api_key", lambda: None)
    monkeypatch.setattr(main, "_spark_chat", boom)
    learner_id = tmp_db.create_learner("T", "10", "English", "Malayalam")
    text = "Onam is Kerala's harvest festival because families gather."
    res = main.post_diagnose(main.DiagnoseIn(learner_id=learner_id, content=text))
    assert res["scores"] == main.diagnose_text(text)
    assert _spark_events(learner_id, "heuristic-scorer")


def test_sanity_gap_logged_when_spark_differs(tmp_db, monkeypatch):
    text = "Nice good."
    heur = {s: main.level_for_score(v)
            for s, v in main.diagnose_text(text).items()}
    assert heur["Argument"] == 2  # premise: no claim markers
    levels = dict(heur)
    levels["Argument"] = 5  # 3 levels above the heuristic

    def fake_chat(messages, temperature=None):
        return _diagnose_reply(levels, "Nice good")

    monkeypatch.setattr(main, "_model_api_key", lambda: "K")
    monkeypatch.setattr(main, "_spark_chat", fake_chat)
    learner_id = tmp_db.create_learner("T", "10", "English", "Malayalam")
    main.post_diagnose(main.DiagnoseIn(learner_id=learner_id, content=text))
    logged = _spark_events(learner_id, "diagnose-sanity")
    assert len(logged) == 1
    assert "over 2 levels" in logged[0]["result"]
    assert "Argument" in logged[0]["result"]
    for skill in main.SKILLS:
        if skill != "Argument":
            assert skill not in logged[0]["result"]


def test_validate_diagnosis_rejects_bad_shapes():
    text = "Onam is sweet because families gather."
    good = {s: {"level": 3, "reason": "Fair.", "evidence": "families gather"}
            for s in main.SKILLS}
    assert main._validate_diagnosis(good, text) is not None
    assert main._validate_diagnosis([], text) is None
    for tweak in ({"level": 0}, {"level": 6}, {"level": "3"},
                  {"level": True}, {"reason": ""}, {"evidence": ""},
                  {"evidence": "zebras drink lava"}):
        bad = {s: dict(v) for s, v in good.items()}
        bad["Grammar"].update(tweak)
        assert main._validate_diagnosis(bad, text) is None, tweak
    missing = {s: v for s, v in good.items() if s != "Grammar"}
    assert main._validate_diagnosis(missing, text) is None


def test_diagnose_sends_temperature_zero_with_short_timeout(tmp_db, monkeypatch):
    seen = {}

    def fake_post(url, body, key, timeout):
        seen.update(body=body, key=key, timeout=timeout)
        return {"choices": [{"message": {"content": _diagnose_reply(
            {}, "Nice good")}}]}

    monkeypatch.setattr(main, "_model_api_key", lambda: "K")
    monkeypatch.setattr(main, "_spark_post", fake_post)
    learner_id = tmp_db.create_learner("T", "10", "English", "Malayalam")
    res = main.post_diagnose(main.DiagnoseIn(learner_id=learner_id,
                                             content="Nice good."))
    assert seen["body"]["temperature"] == 0
    assert seen["timeout"] == main.SPARK_TIMEOUT <= 20
    assert res["scores"]["Grammar"] == 50
    assert res["weakest"] == "Grammar"  # tie: first skill wins
