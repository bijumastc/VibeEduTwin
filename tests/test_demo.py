"""Demo mode: fixed script; other text calls Muse live like Teacher Studio."""
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import learner_store as store  # noqa: E402
import main  # noqa: E402

PASS_SENTENCE = "Plastic waste in rivers harms fish and village life."


@pytest.fixture
def tmp_db(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "DB_PATH", tmp_path / "demo_learners.db")
    monkeypatch.setattr(main, "study_material", lambda skill, n_results=2: [])
    monkeypatch.setattr(main, "_query_guide_chunks",
                        lambda skill, n_results=1: ([], []))
    return store


@pytest.fixture
def demo_on(tmp_db, monkeypatch):
    monkeypatch.setenv("DEMO_MODE", "true")
    monkeypatch.setattr(main, "_model_api_key", lambda: "K")  # key on, still off
    return tmp_db


def _learner(tmp_db):
    return tmp_db.create_learner("Demo", "10", "English", "Malayalam",
                                 discipline="Sciences")


def _save_weak(learner_id):
    return store.save_draft(learner_id, main.DEMO_WEAK_PARAGRAPH, "")


def _perfect_answers():
    return {"d1": "b", "d2": "B, D, A, C", "d3": PASS_SENTENCE}


# --- Flag --------------------------------------------------------------------
def test_demo_mode_defaults_off(monkeypatch):
    monkeypatch.delenv("DEMO_MODE", raising=False)
    assert main._demo_mode() is False
    assert main.get_config() == {"demo_mode": False}


def test_demo_mode_reads_env_flag(monkeypatch):
    monkeypatch.setenv("DEMO_MODE", "true")
    assert main._demo_mode() is True
    assert main.get_config() == {"demo_mode": True}


# --- Fixed diagnosis ----------------------------------------------------------
def test_demo_weak_paragraph_gets_fixed_diagnosis(demo_on, monkeypatch):
    def boom(messages, temperature=None):
        raise AssertionError("demo diagnosis must not call Spark")

    monkeypatch.setattr(main, "_spark_chat", boom)
    learner_id = _learner(demo_on)
    draft_id = _save_weak(learner_id)
    res = main.post_diagnose(main.DiagnoseIn(learner_id=learner_id,
                                             draft_id=draft_id))
    for skill, entry in main.DEMO_DIAGNOSIS.items():
        assert res["scores"][skill] == \
            main.DIAGNOSE_LEVEL_SCORES[entry["level"]], skill
    assert res["weakest"] == "Paragraphing"
    assert res["level"] == 1
    assert res["notice"] is None  # scripted path: no estimate note
    assert res["comparison"] == "This is your starting point."
    logged = [r for r in store.get_events(learner_id)
              if r["tool"] == "diagnose-demo"]
    assert len(logged) == 1
    assert "Demo diagnosis (fixed)" in logged[0]["result"]
    assert "No clear topic sentence; ideas are listed." in logged[0]["result"]
    assert "Plastic is very big problem." in logged[0]["result"]


def test_demo_evidence_quotes_come_from_weak_paragraph():
    for skill, entry in main.DEMO_DIAGNOSIS.items():
        assert 1 <= entry["level"] <= 5, skill
        assert entry["reason"].strip(), skill
        assert entry["evidence"] in main.DEMO_WEAK_PARAGRAPH, skill


def test_demo_improved_paragraph_compares_one_to_two(demo_on):
    learner_id = _learner(demo_on)
    weak_id = _save_weak(learner_id)
    main.post_diagnose(main.DiagnoseIn(learner_id=learner_id, draft_id=weak_id))
    better_id = store.save_draft(learner_id, main.DEMO_IMPROVED_PARAGRAPH, "")
    res = main.post_diagnose(main.DiagnoseIn(learner_id=learner_id,
                                             draft_id=better_id))
    assert res["comparison"] == main.DEMO_COMPARISON
    assert res["level_changes"]["Paragraphing"] == {"previous": 1,
                                                    "current": 2}
    assert res["scores"]["Paragraphing"] == 30  # Level 2 band


def test_demo_other_text_uses_live_spark(demo_on, monkeypatch):
    import json
    text = "My favourite festival is Onam. People wear new clothes."
    seen = []

    def fake_chat(messages, temperature=None, timeout=None):
        seen.append(messages)
        if "give feedback" in messages[0]["content"]:
            return json.dumps({
                "strength": None,
                "problems": [
                    {"quote": "My favourite festival is Onam.",
                     "wrong": "No reason is given.",
                     "why": "Readers ask why it matters.",
                     "fix": "Add because and one reason."},
                    {"quote": "People wear new clothes.",
                     "wrong": "No source is named.",
                     "why": "Readers trust named sources.",
                     "fix": "Say who told you this."}],
                "model": None,
                "your_turn": "Fix these two lines, then rewrite."})
        return json.dumps({
            skill: {"level": 3, "reason": f"{skill} checked.",
                    "evidence": "People wear new clothes."}
            for skill in main.SKILLS})

    monkeypatch.setattr(main, "_model_api_key", lambda: "K")
    monkeypatch.setattr(main, "_spark_chat", fake_chat)
    learner_id = _learner(demo_on)
    res = main.post_diagnose(main.DiagnoseIn(learner_id=learner_id,
                                             content=text))
    assert len(seen) == 2  # diagnosis + feedback, live in demo mode
    assert res["feedback"]["problems"][0]["quote"] == \
        "My favourite festival is Onam."


def test_demo_other_text_falls_back_without_key(demo_on, monkeypatch):
    def boom(messages, temperature=None):
        raise AssertionError("no key: must not call Spark")

    monkeypatch.setattr(main, "_model_api_key", lambda: None)
    monkeypatch.setattr(main, "_spark_chat", boom)
    learner_id = _learner(demo_on)
    text = "My favourite festival is Onam. People wear new clothes."
    res = main.post_diagnose(main.DiagnoseIn(learner_id=learner_id,
                                             content=text))
    assert res["scores"] == main._cap_fallback_scores(
        text, main.diagnose_text(text))
    assert len(res["feedback"]["problems"]) == 2
    assert res["feedback"]["model"] is None  # template has no rewrite


# --- Fixed twin reply ----------------------------------------------------------
def test_demo_twin_serves_fixed_reply(demo_on):
    learner_id = _learner(demo_on)
    _save_weak(learner_id)
    res = main.post_twin_ask(main.TwinAskIn(
        learner_id=learner_id, message="What is wrong with my first line?"))
    assert res["reply"] == main.DEMO_TWIN_RESPONSE


def test_demo_twin_falls_back_for_other_drafts(demo_on):
    learner_id = _learner(demo_on)
    store.save_draft(learner_id, main.DEMO_IMPROVED_PARAGRAPH, "")
    res = main.post_twin_ask(main.TwinAskIn(
        learner_id=learner_id, message="What is wrong with my first line?"))
    assert res["reply"] != main.DEMO_TWIN_RESPONSE
    assert res["reply"].strip()


# --- Fixed practice set ---------------------------------------------------------
def test_demo_serves_fixed_practice_set(demo_on):
    learner_id = _learner(demo_on)
    res = main.get_practice(learner_id)
    assert res["skill"] == "Paragraphing" and res["level"] == 1
    assert [i["id"] for i in res["items"]] == ["d1", "d2", "d3"]
    assert "answer" not in res["items"][0]  # answers stay server-side
    issued = main.ISSUED_SETS[res["set_id"]]
    assert issued["demo"] is True
    assert issued["answers"] == {"d1": "b", "d2": "B, D, A, C", "d3": ""}
    for item in issued["items"][:2]:
        assert main.verify("practice_item", item,
                           rules=main.PRACTICE_STRUCTURAL_RULES)["pass"]


def test_demo_set_wins_over_published(demo_on):
    store.save_teacher_set("Paragraphing", 1, None, [{
        "id": "t1", "type": "mcq", "prompt": "Pick one.",
        "options": ["A) first", "B) second"], "answer": "A",
        "explanation": "Because.", "source": "b.pdf"}], "req")
    learner_id = _learner(demo_on)
    res = main.get_practice(learner_id)
    assert [i["id"] for i in res["items"]] == ["d1", "d2", "d3"]


def test_demo_other_skills_use_normal_sets(demo_on):
    learner_id = _learner(demo_on)
    demo_on.save_skill_scores(learner_id, {s: 90 for s in main.SKILLS
                                           if s != "Grammar"})
    demo_on.save_skill_scores(learner_id, {"Grammar": 10})
    res = main.get_practice(learner_id)
    assert res["skill"] == "Grammar"
    assert main.ISSUED_SETS[res["set_id"]]["demo"] is False


def test_demo_perfect_set_scores_hundred(demo_on, monkeypatch):
    def boom(messages, temperature=None):
        raise AssertionError("demo judging must not call Spark")

    monkeypatch.setattr(main, "_spark_chat", boom)
    learner_id = _learner(demo_on)
    set_id = main.get_practice(learner_id)["set_id"]
    res = main.post_answers(main.PracticeAnswersIn(
        learner_id=learner_id, set_id=set_id, answers=_perfect_answers()))
    assert (res["correct"], res["total"], res["accuracy"]) == (3, 3, 100)
    by_id = {d["id"]: d for d in res["details"]}
    assert all(d["correct"] for d in by_id.values())
    assert by_id["d1"]["assessment"]["score"] == 2
    assert by_id["d2"]["assessment"]["score"] == 2
    assert by_id["d3"]["assessment"]["score"] == 2
    assert "Good topic sentence" in by_id["d3"]["assessment"]["feedback"]


def test_demo_produce_rule_rejects_weak_lines():
    assert main._demo_produce_fields(PASS_SENTENCE)["score"] == 2
    assert main._demo_produce_fields("harms fish")["score"] == 0
    assert main._demo_produce_fields(
        "Plastic waste in rivers is very bad and ugly.")["score"] == 0
    assert main._demo_produce_fields(
        "Plastic waste harms fish. It harms birds too.")["score"] == 0
    assert main._demo_produce_fields(
        "plastic waste in rivers harms fish daily")["score"] == 0
    assert main._demo_produce_fields("")["score"] == 0


# --- Level-up without saving ----------------------------------------------------
def test_demo_two_perfect_sets_level_up_without_saving(demo_on):
    learner_id = _learner(demo_on)
    weak_id = _save_weak(learner_id)
    main.post_diagnose(main.DiagnoseIn(learner_id=learner_id, draft_id=weak_id))
    first = main.post_answers(main.PracticeAnswersIn(
        learner_id=learner_id,
        set_id=main.get_practice(learner_id)["set_id"],
        answers=_perfect_answers()))
    assert first["leveled_up"] is False
    second = main.post_answers(main.PracticeAnswersIn(
        learner_id=learner_id,
        set_id=main.get_practice(learner_id)["set_id"],
        answers=_perfect_answers()))
    assert second["leveled_up"] is True
    assert second["level_ups"] == [{"skill": "Paragraphing",
                                    "from": 1, "to": 2}]
    assert second["new_score"] is None  # shown, not saved
    assert main.latest_scores(learner_id)["Paragraphing"] == 10


def test_demo_full_recording_flow(demo_on):
    learner_id = _learner(demo_on)
    weak = main.post_diagnose(main.DiagnoseIn(
        learner_id=learner_id, draft_id=_save_weak(learner_id)))
    assert weak["weakest"] == "Paragraphing"
    twin = main.post_twin_ask(main.TwinAskIn(
        learner_id=learner_id, message="What is wrong with my first line?"))
    assert twin["reply"] == main.DEMO_TWIN_RESPONSE
    main.post_answers(main.PracticeAnswersIn(
        learner_id=learner_id,
        set_id=main.get_practice(learner_id)["set_id"],
        answers=_perfect_answers()))
    leveled = main.post_answers(main.PracticeAnswersIn(
        learner_id=learner_id,
        set_id=main.get_practice(learner_id)["set_id"],
        answers=_perfect_answers()))
    assert leveled["level_ups"] == [{"skill": "Paragraphing",
                                     "from": 1, "to": 2}]
    better_id = store.save_draft(learner_id, main.DEMO_IMPROVED_PARAGRAPH, "")
    better = main.post_diagnose(main.DiagnoseIn(learner_id=learner_id,
                                                draft_id=better_id))
    assert better["comparison"] == main.DEMO_COMPARISON
    assert better["level_changes"]["Paragraphing"] == {"previous": 1,
                                                       "current": 2}


# --- Spark stays off (except Teacher Studio) --------------------------------------
def test_demo_scaffold_assessor_stays_on_fixed_ladder(demo_on, monkeypatch):
    def boom(messages, temperature=None):
        raise AssertionError("demo assessor must not call Spark")

    monkeypatch.setattr(main, "_spark_chat", boom)
    learner_id = _learner(demo_on)
    started = main.post_scaffold_start(main.ScaffoldStartIn(
        learner_id=learner_id, discipline="Sciences",
        module="topic-sentences"))
    helped = main.post_scaffold_help(main.ScaffoldHelpIn(
        learner_id=learner_id, attempt_id=started["attempt_id"],
        attempt_text="Plants need sun to grow tall."))
    assert helped["step"] == "hint"  # L1 fixed ladder
    assert "assessment" not in helped


def test_demo_scripts_assessor_for_exact_try(demo_on, monkeypatch):
    def boom(messages, temperature=None, timeout=None):
        raise AssertionError("demo script must not call Spark")

    monkeypatch.setattr(main, "_spark_chat", boom)
    learner_id = _learner(demo_on)
    started = main.post_scaffold_start(main.ScaffoldStartIn(
        learner_id=learner_id, discipline="Sciences",
        module="topic-sentences"))
    helped = main.post_scaffold_help(main.ScaffoldHelpIn(
        learner_id=learner_id, attempt_id=started["attempt_id"],
        attempt_text=main.DEMO_ASSESS_ATTEMPT))
    got = helped["assessment"]
    assert got["status"] == "ok" and got["score"] == 1
    assert got["strength"] == main.DEMO_ASSESSMENT_STRENGTH
    assert got["problem"] == main.DEMO_ASSESSMENT_PROBLEM
    assert got["quote"] in main.DEMO_ASSESS_ATTEMPT
    assert got["model"] == main.DEMO_ASSESSMENT_MODEL
    assert got["your_turn"] == main.DEMO_ASSESSMENT_YOUR_TURN
    assert helped["step"] == "question"


def test_demo_teacher_studio_still_uses_spark(demo_on, monkeypatch):
    docs = ["Alpha point 0 about grammar. Beta point 0 about grammar.",
            "Alpha point 1 about grammar. Beta point 1 about grammar."]
    metas = [{"source": "book0.pdf", "chapter": "Ch 0", "license": "CC BY"},
             {"source": "book1.pdf", "chapter": "Ch 1", "license": "CC BY"}]
    monkeypatch.setattr(main, "_query_guides",
                        lambda query, n_results=2: (docs, metas))
    calls = []

    def fake_chat(messages, temperature=None):
        calls.append(messages)
        return json.dumps([
            {"type": "mcq",
             "prompt": "Which sentence gives grammar advice?",
             "options": ["A) Alpha point 1 about grammar.",
                         "B) Beta point 1 about grammar."],
             "answer": "A", "answerExcerpt": "E2"},
            {"type": "mcq",
             "prompt": "Which sentence gives more grammar advice?",
             "options": ["A) Alpha point 0 about grammar.",
                         "B) Beta point 0 about grammar."],
             "answer": "A", "answerExcerpt": "E1"}])

    monkeypatch.setattr(main, "_spark_chat", fake_chat)
    items = main.generate_practice_set("Make 2 practice items on grammar")
    assert calls  # live Spark path runs in demo mode
    assert "Which sentence gives grammar advice?" in \
        [i["prompt"] for i in items]


# --- Letter-format answers ---------------------------------------------------------
def test_order_letters_resolve_to_sentences():
    item = main.DEMO_PRACTICE_ITEMS[1]
    text = main._practice_answer_text(item, "B, D, A, C")
    assert "Mobile phones can support learning" in text
    assert "They give instant access" in text
    assert "For example, students can look up" in text
    assert "Therefore, colleges should allow" in text


def test_order_digits_still_resolve():
    item = {"type": "order",
            "prompt": "Put the paragraph in order. Sentences: 1) 'Rivers run "
                      "fast.' 2) 'Fish swim deep.'"}
    assert main._practice_answer_text(item, "2,1") == \
        "Fish swim deep. Rivers run fast."


def test_mcq_paren_options_resolve_and_verify():
    item = main.DEMO_PRACTICE_ITEMS[0]
    assert main._practice_answer_text(item, "b") == \
        "Mobile phones can support learning in college when clear rules are followed."
    assert main._practice_answer_text(item, "B") == \
        "Mobile phones can support learning in college when clear rules are followed."
    assert main.verify("practice_item", item,
                       rules=main.PRACTICE_STRUCTURAL_RULES)["pass"] is True


# --- Reset --------------------------------------------------------------------------
def test_reset_learner_clears_history(tmp_db):
    learner_id = tmp_db.create_learner("Demo", "10", "English", "Malayalam",
                                       discipline="Medicine")
    tmp_db.save_draft(learner_id, "x", "")
    tmp_db.save_skill_scores(learner_id, {"Paragraphing": 50})
    tmp_db.log_event(learner_id, "Write", "twin", "x", "y")
    tmp_db.save_practice_result(learner_id, "Paragraphing", 100)
    store.reset_learner(learner_id, include_memory=False)
    assert tmp_db.get_learner(learner_id)["discipline"] == "Sciences"
    assert tmp_db.get_drafts(learner_id) == []
    assert tmp_db.get_skill_scores(learner_id) == []
    assert tmp_db.get_events(learner_id) == []
    assert tmp_db.get_practice_results(learner_id, "Paragraphing") == []


def test_reset_learner_recreates_missing_row(tmp_db):
    store.reset_learner(1, include_memory=False)
    assert tmp_db.get_learner(1)["discipline"] == "Sciences"


def test_reset_demo_script_clears_demo_learner(tmp_path):
    import os
    env = dict(os.environ)
    env["VIBEEDUTWIN_DB"] = str(tmp_path / "script_demo.db")
    env["VIBEEDUTWIN_CHROMA"] = str(tmp_path / "script_chroma")
    seed = ("import learner_store as s; "
            "i = s.create_learner('D', '10', 'E', 'M'); "
            "s.save_draft(i, 'x', ''); "
            "s.save_skill_scores(i, {'Paragraphing': 5}); "
            "s.log_event(i, 'W', 't', 'x', 'y'); "
            "print(s.get_learner(i))")
    first = subprocess.run([sys.executable, "-c", seed], cwd=ROOT, env=env,
                           capture_output=True, text=True, timeout=120)
    assert first.returncode == 0, first.stderr
    assert "'id': 1" in first.stdout
    run = subprocess.run([sys.executable, "scripts/reset_demo.py"], cwd=ROOT,
                         env=env, capture_output=True, text=True, timeout=120)
    assert run.returncode == 0, run.stderr
    assert "Demo learner reset" in run.stdout
    check = ("import learner_store as s; "
             "print(len(s.get_drafts(1)), len(s.get_skill_scores(1)), "
             "len(s.get_events(1)), s.get_learner(1)['discipline'])")
    after = subprocess.run([sys.executable, "-c", check], cwd=ROOT, env=env,
                           capture_output=True, text=True, timeout=120)
    assert after.returncode == 0, after.stderr
    assert after.stdout.strip() == "0 0 0 Sciences"


# --- Plan + UI strings ------------------------------------------------------------------
def test_plan_documents_rubric_and_demo_kit():
    plan = (ROOT / "docs" / "plan.md").read_text(encoding="utf-8")
    assert "## Rubric" in plan
    assert "Frequent errors block meaning." in plan
    assert "Formal, objective, and appropriately hedged." in plan
    assert "## Demo kit" in plan
    assert "DEMO_MODE=true" in plan
    assert "Plastic is very big problem." in plan
    assert "Answer: B, D, A, C." in plan


def test_demo_label_and_levelup_ui_strings():
    app = (ROOT / "frontend" / "src" / "App.jsx").read_text(encoding="utf-8")
    assert "Demo mode" in app and "demo-badge" in app
    api = (ROOT / "frontend" / "src" / "api.js").read_text(encoding="utf-8")
    assert "config" in api
    practice = (ROOT / "frontend" / "src" / "screens" / "Practice.jsx").read_text(
        encoding="utf-8")
    assert "level_ups" in practice and "LevelUpCard" in practice
    assert "See my growth" in practice and "SkillBars" in practice
    assert r"\(?([A-Za-z])" in practice  # (b) style options
    css = (ROOT / "frontend" / "src" / "styles.css").read_text(encoding="utf-8")
    assert ".demo-badge" in css
