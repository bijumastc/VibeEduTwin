"""Keep tests hermetic against the developer's own backend .env.

DEMO_MODE=true in .env (used while recording demos) must not change test
outcomes: tests see demo mode only when they set the DEMO_MODE variable
themselves. Runs before test-level fixtures, so setenv there still works.
"""
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import main  # noqa: E402


@pytest.fixture(autouse=True)
def _no_ambient_demo(monkeypatch):
    monkeypatch.delenv("DEMO_MODE", raising=False)
    real_env_key = main._env_key

    def gated(*names):
        if "DEMO_MODE" in names and "DEMO_MODE" not in os.environ:
            return None
        return real_env_key(*names)

    monkeypatch.setattr(main, "_env_key", gated)
