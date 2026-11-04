"""Scan my paper: vision transcription, retries, fallback, draft source."""
import json
import sqlite3
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import learner_store as store  # noqa: E402
import main  # noqa: E402
from fastapi import HTTPException  # noqa: E402

FAKE_IMAGE = "data:image/jpeg;base64,/9j/fakebytes"


@pytest.fixture
def tmp_db(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "DB_PATH", tmp_path / "scan_learners.db")
    return store


def _learner(tmp_db):
    return tmp_db.create_learner("Test", "10", "English", "Malayalam")


def _scan_reply(text, unclear):
    return json.dumps({"text": text, "unclear": unclear})


def test_scan_instruction_is_fixed_text():
    assert main.SCAN_INSTRUCTION == (
        "Transcribe this handwritten paragraph exactly as written, keeping "
        "the learner's own spelling and grammar. Do not correct anything. "
        "Mark any word you cannot read as [unclear].")


def test_scan_returns_text_and_unclear(tmp_db, monkeypatch):
    calls = []

    def fake_chat(messages):
        calls.append(messages)
        return _scan_reply("Plastic is [unclear] problem.", ["Plastic is"])

    monkeypatch.setattr(main, "_model_api_key", lambda: "K")
    monkeypatch.setattr(main, "_spark_chat", fake_chat)
    learner_id = _learner(tmp_db)
    res = main.post_draft_scan(main.DraftScanIn(learner_id=learner_id,
                                                image=FAKE_IMAGE))
    assert res == {"ok": True, "text": "Plastic is [unclear] problem.",
                   "unclear": ["Plastic is"]}
    assert len(calls) == 1
    user = calls[0][1]
    assert user["role"] == "user"
    assert user["content"][0] == {"type": "text",
                                  "text": main.SCAN_INSTRUCTION}
    assert user["content"][1] == {"type": "image_url",
                                  "image_url": {"url": FAKE_IMAGE}}
    logged = [r for r in store.get_events(learner_id) if r["tool"] == "scan"]
    assert len(logged) == 1
    assert "Read by Muse Spark (vision)" in logged[0]["result"]


def test_scan_raw_base64_gets_data_url(tmp_db, monkeypatch):
    calls = []
    monkeypatch.setattr(main, "_model_api_key", lambda: "K")
    monkeypatch.setattr(
        main, "_spark_chat",
        lambda messages: calls.append(messages) or _scan_reply("Nice.", []))
    learner_id = _learner(tmp_db)
    res = main.post_draft_scan(main.DraftScanIn(learner_id=learner_id,
                                                image="abc123"))
    assert res["ok"] is True
    block = calls[0][1]["content"][1]
    assert block["image_url"]["url"] == "data:image/jpeg;base64,abc123"


def test_scan_rejects_bad_shape_and_retries(tmp_db, monkeypatch):
    replies = [json.dumps({"text": ""}),
               _scan_reply("One [unclear] two.", ["One"])]
    calls = []

    def fake_chat(messages):
        calls.append(messages)
        return replies[len(calls) - 1]

    monkeypatch.setattr(main, "_model_api_key", lambda: "K")
    monkeypatch.setattr(main, "_spark_chat", fake_chat)
    learner_id = _learner(tmp_db)
    res = main.post_draft_scan(main.DraftScanIn(learner_id=learner_id,
                                                image=FAKE_IMAGE))
    assert len(calls) == 2
    assert res["ok"] is True and res["text"] == "One [unclear] two."


def test_validate_scan_rejects_bad_shapes():
    assert main._validate_scan([]) is None
    assert main._validate_scan({}) is None
    assert main._validate_scan({"text": "", "unclear": []}) is None
    assert main._validate_scan({"text": "Nice.", "unclear": "x"}) is None
    assert main._validate_scan({"text": "Nice.", "unclear": [1]}) is None
    good = main._validate_scan({"text": "A [unclear] b.", "unclear": ["A"]})
    assert good == {"text": "A [unclear] b.", "unclear": ["A"]}
    assert main._validate_scan({"text": "A b.", "unclear": []}) == \
        {"text": "A b.", "unclear": []}


def test_validate_scan_accepts_missing_unclear_list():
    # Live models omit the key on confident transcriptions; the marks in
    # the text still drive highlighting, so this must pass, not fall back.
    assert main._validate_scan({"text": "Plastic is bad."}) == \
        {"text": "Plastic is bad.", "unclear": []}
    assert main._validate_scan({"text": "Plastic is bad.",
                                "unclear": None}) == \
        {"text": "Plastic is bad.", "unclear": []}
    assert main._validate_scan(
        {"text": "A [unclear] b.", "unclear": []}) == \
        {"text": "A [unclear] b.", "unclear": []}


def test_scan_failure_logs_real_error(tmp_db, monkeypatch):
    def bad_chat(messages):
        raise main.SparkError("HTTP 400: bad image")

    monkeypatch.setattr(main, "_model_api_key", lambda: "K")
    monkeypatch.setattr(main, "_spark_chat", bad_chat)
    learner_id = _learner(tmp_db)
    res = main.post_draft_scan(main.DraftScanIn(learner_id=learner_id,
                                                image=FAKE_IMAGE))
    assert res == {"ok": False, "message": "Please type your paragraph."}
    logged = [r for r in store.get_events(learner_id) if r["tool"] == "scan"]
    assert len(logged) == 1
    assert "HTTP 400: bad image" in logged[0]["result"]


def test_spark_post_keeps_api_error_body(monkeypatch):
    import io
    import urllib.error

    def raising(req, timeout=None):
        raise urllib.error.HTTPError(
            req.full_url, 400, "Bad Request", {},
            io.BytesIO(b'{"error": "bad image"}'))

    monkeypatch.setattr(main.urllib.request, "urlopen", raising)
    with pytest.raises(main.SparkError) as exc:
        main._spark_post("http://x", {}, "K", 20)
    assert "HTTP 400" in str(exc.value)
    assert "bad image" in str(exc.value)


def test_spark_post_names_timeouts(monkeypatch):
    def hanging(req, timeout=None):
        raise TimeoutError("timed out")

    monkeypatch.setattr(main.urllib.request, "urlopen", hanging)
    with pytest.raises(main.SparkError) as exc:
        main._spark_post("http://x", {}, "K", 20)
    assert "timed out after 20s" in str(exc.value)


def test_scan_exhausts_retries_then_fallback(tmp_db, monkeypatch):
    calls = []
    monkeypatch.setattr(main, "_model_api_key", lambda: "K")
    monkeypatch.setattr(
        main, "_spark_chat",
        lambda messages: calls.append(messages) or "nope")
    learner_id = _learner(tmp_db)
    res = main.post_draft_scan(main.DraftScanIn(learner_id=learner_id,
                                                image=FAKE_IMAGE))
    assert len(calls) == 3  # 1 initial + 2 regens
    assert res == {"ok": False, "message": "Please type your paragraph."}


def test_scan_no_key_falls_back(tmp_db, monkeypatch):
    monkeypatch.setattr(main, "_model_api_key", lambda: None)
    learner_id = _learner(tmp_db)
    res = main.post_draft_scan(main.DraftScanIn(learner_id=learner_id,
                                                image=FAKE_IMAGE))
    assert res == {"ok": False, "message": "Please type your paragraph."}


def test_scan_rejects_empty_and_oversize(tmp_db, monkeypatch):
    def boom(messages):
        raise AssertionError("invalid image must not reach Spark")

    monkeypatch.setattr(main, "_model_api_key", lambda: "K")
    monkeypatch.setattr(main, "_spark_chat", boom)
    learner_id = _learner(tmp_db)
    for bad in ("", "x" * (main.SCAN_MAX_CHARS + 1)):
        res = main.post_draft_scan(main.DraftScanIn(learner_id=learner_id,
                                                    image=bad))
        assert res == {"ok": False, "message": "Please type your paragraph."}


def test_scan_uses_short_timeout(tmp_db, monkeypatch):
    seen = {}

    def fake_post(url, body, key, timeout):
        seen.update(body=body, timeout=timeout)
        return {"choices": [{"message": {"content": _scan_reply(
            "Nice.", [])}}]}

    monkeypatch.setattr(main, "_model_api_key", lambda: "K")
    monkeypatch.setattr(main, "_spark_post", fake_post)
    learner_id = _learner(tmp_db)
    res = main.post_draft_scan(main.DraftScanIn(learner_id=learner_id,
                                                image=FAKE_IMAGE))
    assert res["ok"] is True
    assert seen["timeout"] == main.SPARK_TIMEOUT <= 20
    assert seen["body"]["model"] == "muse-spark-1.3"
    assert seen["body"]["messages"][1]["content"][1]["type"] == "image_url"


def test_scan_rejects_unknown_learner(tmp_db):
    with pytest.raises(HTTPException) as exc:
        main.post_draft_scan(main.DraftScanIn(learner_id=999,
                                              image=FAKE_IMAGE))
    assert exc.value.status_code == 404


def test_scan_never_stores_photo(tmp_db, monkeypatch):
    monkeypatch.setattr(main, "_model_api_key", lambda: "K")
    monkeypatch.setattr(main, "_spark_chat",
                        lambda messages: _scan_reply("Nice.", []))
    learner_id = _learner(tmp_db)
    main.post_draft_scan(main.DraftScanIn(learner_id=learner_id,
                                          image=FAKE_IMAGE))
    monkeypatch.setattr(main, "_spark_chat", lambda messages: "nope")
    main.post_draft_scan(main.DraftScanIn(learner_id=learner_id,
                                          image=FAKE_IMAGE))
    assert store.get_drafts(learner_id) == []
    for row in store.get_events(learner_id):
        assert "fakebytes" not in row["result"]
        assert "base64" not in row["result"]


def test_draft_source_roundtrip(tmp_db, monkeypatch):
    monkeypatch.setattr(store, "save_writing_sample", lambda *a: "fake")
    learner_id = _learner(tmp_db)
    typed = main.post_draft(main.DraftIn(learner_id=learner_id,
                                         content="Typed words here."))
    scanned = main.post_draft(main.DraftIn(learner_id=learner_id,
                                           content="Scanned words here.",
                                           source="scan"))
    by_id = {d["id"]: d for d in store.get_drafts(learner_id)}
    assert by_id[typed["draft_id"]]["source"] == "typed"
    assert by_id[scanned["draft_id"]]["source"] == "scan"
    with pytest.raises(HTTPException) as exc:
        main.post_draft(main.DraftIn(learner_id=learner_id, content="x",
                                     source="photo"))
    assert exc.value.status_code == 400


def test_draft_source_migration_to_old_db(tmp_path, monkeypatch):
    db_path = tmp_path / "old.db"
    conn = sqlite3.connect(db_path)
    conn.execute("""CREATE TABLE learners (
        id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL,
        year TEXT NOT NULL, subject TEXT NOT NULL,
        language_preference TEXT NOT NULL, discipline TEXT NOT NULL,
        created_at TEXT NOT NULL)""")
    conn.execute("""CREATE TABLE drafts (
        id INTEGER PRIMARY KEY AUTOINCREMENT, learner_id INTEGER NOT NULL,
        content TEXT NOT NULL, feedback TEXT NOT NULL,
        created_at TEXT NOT NULL)""")
    conn.execute("INSERT INTO learners (name, year, subject,"
                 " language_preference, discipline, created_at)"
                 " VALUES ('Old', '10', 'English', 'Malayalam', 'Sciences', 'now')")
    conn.execute("INSERT INTO drafts (learner_id, content, feedback,"
                 " created_at) VALUES (1, 'Old words.', '', 'now')")
    conn.commit()
    conn.close()
    monkeypatch.setattr(store, "DB_PATH", db_path)
    assert store.get_drafts(1)[0]["source"] == "typed"


def test_scan_ui_strings():
    write = (ROOT / "frontend" / "src" / "screens" / "Write.jsx").read_text(
        encoding="utf-8")
    assert "Scan my paper" in write
    assert "This is what I wrote" in write
    assert ("Check that this matches your paper. "
            "Fix any word the app read wrongly.") in write
    assert "[unclear]" in write and "<mark>" in write
    assert 'accept="image/jpeg,image/png"' in write
    assert "scanPaper" in write and "1000000" in write
    assert "Please type your paragraph." in write
    api = (ROOT / "frontend" / "src" / "api.js").read_text(encoding="utf-8")
    assert "scanPaper" in api and "/drafts/scan" in api
