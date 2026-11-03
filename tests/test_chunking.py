import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from ingest_knowledge import (  # noqa: E402
    clean_text,
    detect_chapter,
    infer_skill,
    split_words,
)


def test_split_400_with_50_overlap():
    words = [f"w{i}" for i in range(1000)]
    chunks = split_words(words, size=400, overlap=50)
    assert len(chunks[0]) == 400
    # Overlap: last 50 of chunk 0 == first 50 of chunk 1
    assert chunks[0][-50:] == chunks[1][:50]
    # Full coverage without gaps
    assert chunks[0][0] == "w0"
    assert chunks[-1][-1] == "w999"


def test_clean_removes_page_numbers():
    text = "Some real content\n123\nPage 4\n- 7 -\nMore content"
    cleaned = clean_text(text)
    assert "Some real content" in cleaned
    assert "More content" in cleaned
    assert "\n123\n" not in f"\n{cleaned}\n"
    assert "Page 4" not in cleaned


def test_clean_removes_index_lines():
    text = "Real paragraph here\nParagraph unity ........ 123\nAnother real line"
    cleaned = clean_text(text)
    assert "Real paragraph here" in cleaned
    assert "Paragraph unity" not in cleaned


def test_metadata_helpers():
    assert detect_chapter("Chapter 3 Writing Paragraphs\nsome text") != "unknown"
    # Chunks are single-line word joins, so headings appear mid-text.
    assert "Chapter 2" in detect_chapter("Guide words Chapter 2 Writing Paragraphs more words")
    assert detect_chapter("no heading here at all") == "unknown"
    assert infer_skill("A good topic sentence starts a paragraph") == "paragraph-writing"
    assert infer_skill("Use a thesis in your introduction") == "essay-structure"
