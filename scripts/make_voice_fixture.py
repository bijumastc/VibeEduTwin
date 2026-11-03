"""Generate tests/fixtures/voice_sample.wav: a short synthetic voice-like sample.

1.2 s of mono 16-bit PCM at 16 kHz: a 300 -> 900 Hz sine sweep (vowel-like
glide) with 100 ms silence at each end. Synthetic, not a real recording: it
exercises framing, relay and the audit trail, not recognition accuracy
(recognition is Meta's side, mocked in tests).

Run:  .venv\\Scripts\\python.exe scripts/make_voice_fixture.py
"""

import math
import struct
import wave
from pathlib import Path

RATE = 16000
DURATION_S = 1.2
SWEEP_FROM = 300.0
SWEEP_TO = 900.0
SILENCE_S = 0.1
AMPLITUDE = 12000


def main() -> Path:
    out = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "voice_sample.wav"
    out.parent.mkdir(parents=True, exist_ok=True)
    n = int(RATE * DURATION_S)
    silence = int(RATE * SILENCE_S)
    frames = bytearray()
    for i in range(n):
        if i < silence or i >= n - silence:
            sample = 0
        else:
            t = (i - silence) / (n - 2 * silence)
            freq = SWEEP_FROM + (SWEEP_TO - SWEEP_FROM) * t
            phase = 2 * math.pi * freq * (i - silence) / RATE
            sample = int(AMPLITUDE * math.sin(phase))
        frames += struct.pack("<h", sample)
    # Binary PCM frames: no text encoding applies (keeps utf8-open lint quiet).
    with wave.open(str(out), "wb") as wav:  # encoding: n/a for binary wave
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(RATE)
        wav.writeframes(bytes(frames))
    print(f"wrote {out} ({len(frames)} bytes of PCM)")
    return out


if __name__ == "__main__":
    main()
