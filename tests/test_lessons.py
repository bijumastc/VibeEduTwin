"""Lesson redesign: clean retrieval, relevance, grounding, sources."""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import main  # noqa: E402


def _hit(doc, source="guide.pdf"):
    return ([doc], [{"source": source, "chapter": "Ch 1", "license": "CC BY"}])


# --- Clean retrieval ---------------------------------------------------------
def test_cleaning_strips_artifacts():
    raw = ("UNIT 8 REPORTS | 169 Conclusion. \u2022 A topic sentence opens well. "
           "9.4 SIGNAL PHRASES AND TAGS. Page 12. 25. Real readers need clarity.")
    cleaned = main.clean_excerpt_text(raw)
    assert "|" not in cleaned and "\u2022" not in cleaned
    assert "SIGNAL PHRASES" not in cleaned
    assert "Page 12" not in cleaned
    assert "A topic sentence opens well." in cleaned
    assert "Real readers need clarity." in cleaned


def test_cleaning_repairs_splits_and_quotes():
    cleaned = main.clean_excerpt_text("Readers con- clude fast. \u201cKeep it short.\u201d Done.")
    assert "conclude" in cleaned
    assert '"' in cleaned and "\u201c" not in cleaned


def test_cleaning_keeps_normal_text():
    assert main.clean_excerpt_text("First. Second. Third. Fourth.") == \
        "First. Second. Third. Fourth."


# --- Relevance -----------------------------------------------------------------
def test_discipline_books_win(monkeypatch):
    docs = ["A thesis argues one debatable claim with clear facts and proof.",
            "A thesis argues one debatable claim with clear facts and proof."]
    metas = [{"source": "Writing-About-Literature-1692383909.pdf", "license": "X"},
             {"source": "Technical-Writing-Essentials-1768928228.pdf", "license": "X"}]
    monkeypatch.setattr(main, "_query_guides", lambda query, n_results=8: (docs, metas))
    excerpt = main.verified_excerpt("thesis rule", 2, prefer_discipline="Technology")
    assert excerpt["source"] == "Technical-Writing-Essentials-1768928228.pdf"
    excerpt = main.verified_excerpt("thesis rule", 2, prefer_discipline="Arts & Humanities")
    assert excerpt["source"] == "Writing-About-Literature-1692383909.pdf"


def test_example_shows_instead_of_defining(monkeypatch):
    doc = ("A thesis statement is defined as one debatable claim. "
           "For example, zoos should be banned to protect wild animals.")
    monkeypatch.setattr(main, "_query_guides", lambda query, n_results=8: _hit(doc))
    picked = main.select_showing_example("thesis", "essay", "Arts & Humanities", "unrelated rule")
    assert "zoos should be banned" in picked["text"]


def test_example_never_repeats_rule(monkeypatch):
    rule = "A topic sentence tells the main idea of the paragraph for readers."
    doc = rule + " For example, labs open every report with the key finding."
    monkeypatch.setattr(main, "_query_guides", lambda query, n_results=8: _hit(doc))
    picked = main.select_showing_example("topic", "lab report", "Sciences", rule)
    assert "labs open every report" in picked["text"]


# --- Sources ----------------------------------------------------------------------
def test_based_on_uses_real_title_never_filename():
    book = main.resolve_book("Writing for Success (McLean).pdf", "CC BY-NC-SA 3.0")
    assert book == {"title": "Writing for Success", "publisher": None,
                    "license": "CC BY-NC-SA 3.0"}


def test_humanize_fallback_has_no_filename_bits():
    title = main.humanize_book_title("Technical-Writing-Essentials-1768928228.pdf")
    assert title == "Technical Writing Essentials"
    assert ".pdf" not in title and "1768928228" not in title


def test_lesson_based_on_entries_have_title_and_license(tmp_path, monkeypatch):
    doc = ("A topic sentence opens the paragraph. It states the main point "
           "first. Details that follow support it.")
    meta = {"source": "Writing for Success (McLean).pdf", "license": "CC BY-NC-SA 3.0"}
    monkeypatch.setattr(main, "_query_guides", lambda query, n_results=8: ([doc], [meta]))
    import learner_store as store
    monkeypatch.setattr(store, "DB_PATH", tmp_path / "lesson_books.db")
    learner_id = store.create_learner("T", "10", "English", "Malayalam")
    lesson = main.get_curriculum_module(learner_id, "Sciences", "topic-sentences")
    assert lesson["based_on"]
    for book in lesson["based_on"]:
        assert book["title"] and ".pdf" not in book["title"]
        assert book["title"] != "unknown"
        assert book["license"]


# --- Grounding ----------------------------------------------------------------------
def test_grounding_verifier_pass_and_fail():
    good = "A topic sentence opens the paragraph with the main point first, and details follow."
    verdict = main.verify("lesson_idea", {"module": "topic-sentences", "excerpt": good})
    assert verdict == {"pass": True, "failed": [], "fix": ""}
    bad = main.verify("lesson_idea", {"module": "topic-sentences",
                                      "excerpt": "Cite every source you borrow."})
    assert bad["pass"] is False
    assert any("grounded-in-excerpt" in f for f in bad["failed"])
    assert bad["fix"]


def test_grounded_loop_skips_failing_excerpt(monkeypatch):
    bad = "Cite every source you borrow with care today."
    good = ("A topic sentence opens the paragraph. It states the main point "
            "first. Details that follow support it.")
    metas = [{"source": "a.pdf"}, {"source": "b.pdf"}]
    monkeypatch.setattr(main, "_query_guides",
                        lambda query, n_results=8: ([bad, good], metas))
    module = {"id": "topic-sentences", "query": "topic sentences"}
    text, meta, authored = main._select_grounded_idea(module, "Sciences")
    assert authored is True
    assert text == main.LESSON_IDEAS["topic-sentences"]
    assert meta["source"] == "b.pdf"


# --- Lesson content constraints -------------------------------------------------------
def _formatted_texts():
    for module_id in main.LESSON_HOOKS:
        yield main.LESSON_HOOKS[module_id]
        block = main.LESSON_TRY[module_id]
        yield block["prompt"]
        yield from block["options"]
        yield block["reveal"]
        yield main.LESSON_WHY[module_id]


def test_hooks_try_and_why_state_no_facts_or_stats():
    for text in _formatted_texts():
        assert not re.search(r"\d", text), text
        assert "%" not in text, text


def test_try_options_are_abstract_not_examples():
    for module_id, block in main.LESSON_TRY.items():
        assert len(block["options"]) == 3
        assert 0 <= block["answer"] < 3
        for option in block["options"]:
            assert not re.search(r"[.!?]", option), (module_id, option)


def test_why_lines_pass_twin_verifier():
    for module_id, line in main.LESSON_WHY.items():
        text = line.format(topic="evaporation", genre="lab report")
        assert main.verify_twin_reply(text) == [], (module_id, text)
        assert text.startswith("You will"), text  # future-self voice only
        assert "hard too" not in text.lower(), text


def test_ideas_are_two_to_three_short_sentences():
    for module_id, idea in main.LESSON_IDEAS.items():
        sents = [s for s in re.split(r"[.!?]+", idea) if s.strip()]
        assert 2 <= len(sents) <= 3, module_id
        for sent in sents:
            assert len(sent.split()) <= 14, (module_id, sent)


# --- Lesson UI (static) ------------------------------------------------------------------
def test_lesson_stepper_and_info_icon():
    view = (ROOT / "frontend" / "src" / "components" / "LessonView.jsx").read_text(
        encoding="utf-8")
    for step in ("Hook", "Try first", "The idea", "Real example", "Your turn", "Why it matters"):
        assert step in view, step
    assert "Step {step + 1} of" in view
    assert "ScaffoldTask" in view
    based = (ROOT / "frontend" / "src" / "components" / "BasedOn.jsx").read_text(
        encoding="utf-8")
    assert "ⓘ" in based and "Based on:" in based
    compact = (ROOT / "frontend" / "src" / "components" / "CompactLesson.jsx").read_text(
        encoding="utf-8")
    assert "The idea:" in compact and "Real example:" in compact
    assert "BasedOn" in compact and "Practise this" in compact
    assert "license unknown" not in compact and "license unknown" not in view


def test_learn_cards_use_no_spark(tmp_path, monkeypatch):
    doc = ("A topic sentence opens the paragraph. It states the main point "
           "first. Details that follow support it.")
    meta = {"source": "Writing for Success (McLean).pdf", "license": "CC BY-NC-SA 3.0"}
    monkeypatch.setattr(main, "_query_guides",
                        lambda query, n_results=8: ([doc], [meta]))

    def boom(messages):
        raise AssertionError("Learn cards are excerpt-only; Spark must not run")

    monkeypatch.setattr(main, "_spark_chat", boom)
    import learner_store as store
    monkeypatch.setattr(store, "DB_PATH", tmp_path / "learn_nospark.db")
    learner_id = store.create_learner("T", "10", "English", "Malayalam")
    lesson = main.get_curriculum_module(learner_id, "Sciences", "topic-sentences")
    assert lesson["hook"] and lesson["idea"]["text"] and lesson["example"]["text"]
