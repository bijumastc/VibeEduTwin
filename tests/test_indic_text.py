"""Indic-language text must render correctly end to end.

Covers: Google Fonts loading + font-family stack (frontend), UTF-8 file
opens / JSON responses / SQLite (backend), meta charset, and the
fonts-test.html sample page (one sentence per language).
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

FONTS = [
    "Noto Sans",
    "Noto Sans Malayalam",
    "Noto Sans Tamil",
    "Noto Sans Telugu",
    "Noto Sans Kannada",
    "Noto Sans Devanagari",
    "Noto Sans Bengali",
    "Noto Sans Gujarati",
    "Noto Sans Gurmukhi",
    "Noto Sans Oriya",
]

# One Unicode range per script the test page must show.
SCRIPT_RANGES = {
    "Malayalam": ("0D00", "0D7F"),
    "Tamil": ("0B80", "0BFF"),
    "Telugu": ("0C00", "0C7F"),
    "Kannada": ("0C80", "0CFF"),
    "Devanagari": ("0900", "097F"),
    "Bengali": ("0980", "09FF"),
    "Gujarati": ("0A80", "0AFF"),
    "Gurmukhi": ("0A00", "0A7F"),
    "Oriya": ("0B00", "0B7F"),
}

TEST_PAGE = ROOT / "frontend" / "public" / "fonts-test.html"


def _has_char_in_range(text, lo_hex, hi_hex):
    lo, hi = int(lo_hex, 16), int(hi_hex, 16)
    return any(lo <= ord(ch) <= hi for ch in text)


def test_index_html_has_utf8_meta():
    html = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")
    assert re.search(r'<meta\s+charset=["\']?utf-8["\']?\s*/?>',
                     html, re.IGNORECASE), "index.html lacks <meta charset=\"UTF-8\">"


def test_index_html_loads_all_noto_fonts():
    html = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")
    assert "fonts.googleapis.com" in html, "no Google Fonts link in index.html"
    for font in FONTS:
        assert font.replace(" ", "+") in html, f"{font} not loaded in index.html"


def test_styles_font_family_stack_order():
    css = (ROOT / "frontend" / "src" / "styles.css").read_text(encoding="utf-8")
    match = re.search(r"body\s*\{[^}]*font-family\s*:\s*([^;]+);", css, re.DOTALL)
    assert match, "no body font-family in styles.css"
    stack = match.group(1)
    positions = []
    for font in FONTS:
        pos = stack.find(font)
        assert pos != -1, f"{font} missing from body font-family"
        positions.append(pos)
    assert positions == sorted(positions), \
        "font-family must list Noto Sans first, then each script font in order"


def test_fonts_test_page_shows_every_language():
    assert TEST_PAGE.exists(), f"missing {TEST_PAGE.relative_to(ROOT)}"
    html = TEST_PAGE.read_text(encoding="utf-8")
    assert re.search(r'<meta\s+charset=["\']?utf-8["\']?\s*/?>',
                     html, re.IGNORECASE), "test page lacks UTF-8 meta"
    for font in FONTS:
        assert font in html or font.replace(" ", "+") in html, \
            f"{font} missing from test page"
    for script, (lo, hi) in SCRIPT_RANGES.items():
        assert _has_char_in_range(html, lo, hi), \
            f"test page has no {script} sentence"


def test_json_responses_keep_unicode_unescaped():
    import main

    response_class = main.app.router.default_response_class
    assert "charset=utf-8" in response_class.media_type.lower(), \
        "JSON responses lack charset=utf-8"
    rendered = response_class({"t": "മലയാളം"}).body
    assert "മലയാളം".encode("utf-8") in rendered, \
        "JSON response escapes non-ASCII instead of emitting UTF-8"
    assert b"\\u0d" not in rendered.lower()


def test_sqlite_roundtrips_indic_text(tmp_path, monkeypatch):
    import learner_store as store

    monkeypatch.setattr(store, "DB_PATH", tmp_path / "test_learners.db")
    learner_id = store.create_learner("പരീക്ഷ", "10", "English", "Malayalam")
    sample = "ചെറിയ steps — தமிழ் తెలుగు ಕನ್ನಡ हिन्दी বাংলা ગુજરાતી ਪੰਜਾਬੀ ଓଡ଼ିଆ"
    draft_id = store.save_draft(learner_id, sample, "നന്നായി")
    drafts = [d for d in store.get_drafts(learner_id) if d["id"] == draft_id]
    assert drafts and drafts[0]["content"] == sample
    assert drafts[0]["feedback"] == "നന്നായി"


def test_sqlite_connection_uses_utf8():
    import inspect

    import learner_store as store

    source = inspect.getsource(store._connect)
    assert 'PRAGMA encoding' in source and 'UTF-8' in source, \
        "_connect must set PRAGMA encoding UTF-8"
    assert "text_factory" in source, "_connect must set text_factory for str"


def test_all_file_opens_use_utf8():
    offenders = []
    for path in list(ROOT.glob("*.py")) + list((ROOT / "scripts").glob("*.py")):
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            if re.search(r"(?<!\w)(open|read_text|write_text)\s*\(", line):
                if "encoding" not in line and "PdfReader" not in line:
                    offenders.append(f"{path.name}:{lineno}: {stripped}")
    assert not offenders, "file opens without encoding=\"utf-8\": " + "; ".join(offenders)
