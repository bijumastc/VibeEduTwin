"""Voice input: /ws/transcribe proxy to Muse Voice Transcribe + mic UI."""
import contextlib
import json
import socket
import sys
import threading
import wave
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import learner_store as store  # noqa: E402
import main  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from websockets.sync.server import serve  # noqa: E402

FIXTURE = ROOT / "tests" / "fixtures" / "voice_sample.wav"


@pytest.fixture
def tmp_db(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "DB_PATH", tmp_path / "voice_learners.db")
    return store


def _learner(tmp_db, language="Hindi"):
    return tmp_db.create_learner("Test", "10", "English", language)


def _fixture_pcm() -> bytes:
    with wave.open(str(FIXTURE), "rb") as wav:
        assert wav.getnchannels() == 1
        assert wav.getsampwidth() == 2
        assert wav.getframerate() == 16000
        return wav.readframes(wav.getnframes())


def _free_port() -> int:
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


@contextlib.contextmanager
def _fake_meta(monkeypatch, handler):
    """Point the proxy at a fake Meta server; yield what it received."""
    received: dict = {}
    port = _free_port()

    def wrapped(ws):
        handler(ws, received)

    server = serve(wrapped, "127.0.0.1", port)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    monkeypatch.setattr(main, "MUSE_ASR_URL",
                        f"ws://127.0.0.1:{port}/v1/asr/realtime")
    monkeypatch.setattr(main, "_meta_api_key", lambda: "test-key")
    try:
        yield received
    finally:
        server.shutdown()
        thread.join(timeout=5)


def _meta_script(ws, received, final_text="hello world"):
    received["handshake"] = json.loads(ws.recv())
    ws.send(json.dumps({"sessionId": "test-1"}))
    audio = bytearray()
    for msg in ws:
        if isinstance(msg, bytes):
            audio += msg
        else:
            received["end"] = json.loads(msg)
            break
    received["audio"] = bytes(audio)
    ws.send(json.dumps({"type": "transcript", "transcript": "hello",
                        "final": False}))
    ws.send(json.dumps({"type": "transcript", "transcript": final_text,
                        "final": True}))
    ws.close()


# --- Handshake, hints, events (per dev.meta.ai/docs) --------------------------
def test_handshake_matches_documented_format():
    assert main.muse_handshake("KEY", ["Hindi"]) == {
        "authorization": {"accessToken": "Bearer KEY"},
        "audioEncoding": "PCM_16KHZ",
        "model": "muse-voice-transcribe-1.0",
        "mode": "PUSH_TO_TALK",
        "languageBias": ["Hindi"],
    }
    hintless = main.muse_handshake("KEY", [])
    assert "languageBias" not in hintless
    assert hintless["audioEncoding"] == "PCM_16KHZ"


def test_language_hints_cover_indian_languages():
    for language in ("Hindi", "Tamil", "Telugu", "Kannada", "Bengali",
                     "Marathi", "English"):
        assert main.meta_language_hint(language) == [language]
    assert main.meta_language_hint("Malayalam") == []  # not documented: detect
    assert main.meta_language_hint("Klingon") == []


def test_browser_speech_lang_defaults_to_malayalam_india():
    assert main.browser_speech_lang("Malayalam") == "ml-IN"
    assert main.browser_speech_lang("Hindi") == "hi-IN"
    assert main.browser_speech_lang("Tamil") == "ta-IN"
    assert main.browser_speech_lang("English") == "en-IN"
    assert main.browser_speech_lang("Klingon") == "en-IN"


def test_parse_muse_event():
    assert main.parse_muse_event(
        {"type": "transcript", "transcript": "hi", "final": False}) == \
        {"kind": "transcript", "text": "hi", "final": False}
    assert main.parse_muse_event(
        {"type": "transcript", "transcript": "hi", "final": True}) == \
        {"kind": "transcript", "text": "hi", "final": True}
    assert main.parse_muse_event(
        {"type": "error", "message": "bad audio"}) == \
        {"kind": "error", "message": "bad audio"}
    assert main.parse_muse_event({"type": "speechStart"}) == {"kind": "ignore"}
    assert main.parse_muse_event({"sessionId": "x"}) == {"kind": "ignore"}


# --- Proxy relay --------------------------------------------------------------
def test_proxy_relays_sample_and_returns_transcript(tmp_db, monkeypatch):
    learner_id = _learner(tmp_db, "Hindi")
    pcm = _fixture_pcm()
    with _fake_meta(monkeypatch, _meta_script) as received:
        client = TestClient(main.app)
        with client.websocket_connect(
                f"/ws/transcribe?learner_id={learner_id}") as ws:
            ready = ws.receive_json()
            assert ready["type"] == "ready"
            assert ready["metaHint"] == ["Hindi"]
            assert ready["browserLang"] == "hi-IN"
            for i in range(0, len(pcm), 3200):
                ws.send_bytes(pcm[i:i + 3200])
            ws.send_json({"type": "stop"})
            texts = []
            while True:
                msg = ws.receive_json()
                if msg["type"] == "partial":
                    texts.append(msg["text"])
                elif msg["type"] == "final":
                    assert msg["text"] == "hello world"
                    break
                else:
                    raise AssertionError(msg)
            assert texts == ["hello"]
    assert received["handshake"]["authorization"] == {"accessToken": "Bearer test-key"}
    assert received["handshake"]["audioEncoding"] == "PCM_16KHZ"
    assert received["handshake"]["model"] == "muse-voice-transcribe-1.0"
    assert received["handshake"]["mode"] == "PUSH_TO_TALK"
    assert received["handshake"]["languageBias"] == ["Hindi"]
    assert received["audio"] == pcm
    assert received["end"] == {"type": "endStream"}
    events = store.get_events(learner_id)
    assert events[-1]["tool"] == "transcribe"
    assert events[-1]["result"] == "Transcribed by Muse Voice Transcribe"
    assert "META_API_KEY" not in json.dumps(received["handshake"])


def test_malayalam_omits_hint_but_still_tries_meta(tmp_db, monkeypatch):
    learner_id = _learner(tmp_db, "Malayalam")
    with _fake_meta(monkeypatch, _meta_script) as received:
        client = TestClient(main.app)
        with client.websocket_connect(
                f"/ws/transcribe?learner_id={learner_id}") as ws:
            ready = ws.receive_json()
            assert ready["metaHint"] == []
            assert ready["browserLang"] == "ml-IN"
            ws.send_bytes(b"\x00\x00" * 800)
            ws.send_json({"type": "stop"})
            while True:
                msg = ws.receive_json()
                if msg["type"] == "final":
                    break
    assert "languageBias" not in received["handshake"]


def test_meta_failure_signals_browser_fallback(tmp_db, monkeypatch):
    def failing(ws, received):
        received["handshake"] = json.loads(ws.recv())
        ws.send(json.dumps({"sessionId": "test-1"}))
        for msg in ws:  # drain until endStream, then fail
            if not isinstance(msg, bytes):
                break
        ws.send(json.dumps({"type": "error", "message": "rate limited"}))
        ws.close()

    learner_id = _learner(tmp_db)
    with _fake_meta(monkeypatch, failing):
        client = TestClient(main.app)
        with client.websocket_connect(
                f"/ws/transcribe?learner_id={learner_id}") as ws:
            assert ws.receive_json()["type"] == "ready"
            ws.send_bytes(b"\x00\x00" * 800)
            ws.send_json({"type": "stop"})
            while True:
                msg = ws.receive_json()
                if msg["type"] == "meta_error":
                    assert "rate limited" in msg["message"]
                    break
                assert msg["type"] == "partial"


def test_voice_timeout_answers_instead_of_hanging(tmp_db, monkeypatch):
    def silent(ws, received):
        received["handshake"] = json.loads(ws.recv())
        try:
            ws.recv()  # then never ack: block until the client gives up
        except Exception:
            pass

    monkeypatch.setattr(main, "VOICE_TIMEOUT", 0.5)
    learner_id = _learner(tmp_db)
    with _fake_meta(monkeypatch, silent) as received:
        client = TestClient(main.app)
        with client.websocket_connect(
                f"/ws/transcribe?learner_id={learner_id}") as ws:
            assert ws.receive_json()["type"] == "ready"
            msg = ws.receive_json()
            assert msg["type"] == "meta_error"
            assert msg["reason"] == "timeout"
            assert "timed out" in msg["message"]
    assert received["handshake"]["audioEncoding"] == "PCM_16KHZ"


def test_missing_key_signals_browser_fallback(tmp_db, monkeypatch):
    monkeypatch.setattr(main, "_meta_api_key", lambda: None)
    learner_id = _learner(tmp_db)
    client = TestClient(main.app)
    with client.websocket_connect(
            f"/ws/transcribe?learner_id={learner_id}") as ws:
        ready = ws.receive_json()
        assert ready["type"] == "ready"
        assert ready["browserLang"] == "hi-IN"
        assert ws.receive_json()["type"] == "meta_error"


def test_unknown_learner_rejected(tmp_db):
    client = TestClient(main.app)
    with client.websocket_connect("/ws/transcribe?learner_id=999") as ws:
        msg = ws.receive_json()
        assert msg["type"] == "error"


# --- Mic UI (static) ----------------------------------------------------------
def test_mic_button_on_write_and_twin():
    voice = (ROOT / "frontend" / "src" / "components" / "VoiceButton.jsx").read_text(
        encoding="utf-8")
    assert "Speak" in voice
    assert "16000" in voice and "PCM" in voice
    assert "voiceSocketUrl" in voice
    assert "webkitSpeechRecognition" in voice
    assert "ml-IN" in voice
    assert "Wrong transcript" in voice
    assert "Use browser mic instead" in voice
    assert "msg.message" in voice
    write = (ROOT / "frontend" / "src" / "screens" / "Write.jsx").read_text(
        encoding="utf-8")
    assert "VoiceButton" in write
    twin = (ROOT / "frontend" / "src" / "components" / "TwinPanel.jsx").read_text(
        encoding="utf-8")
    assert "VoiceButton" in twin
    api = (ROOT / "frontend" / "src" / "api.js").read_text(encoding="utf-8")
    assert "voiceSocketUrl" in api
