import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from ingest_knowledge import is_license_allowed, load_manifest  # noqa: E402

ALLOWED = ["CC BY", "CC-BY", "CC0", "Public Domain"]


def test_gate_allows_by_family_without_nd():
    for lic in ("CC BY", "CC BY 4.0", "CC BY-SA 4.0", "CC BY-NC",
                "CC BY-NC 4.0", "CC BY-NC-SA", "CC BY-NC-SA 3.0",
                "CC BY-NC-SA 4.0", "cc by-nc-sa 4.0", "CC-BY-NC-SA 4.0"):
        assert is_license_allowed(lic, ALLOWED), lic


def test_gate_still_allows_cc0_and_public_domain():
    assert is_license_allowed("CC0", ALLOWED)
    assert is_license_allowed("Public Domain", ALLOWED)


def test_gate_rejects_nd_in_any_spelling():
    for lic in ("CC BY-NC-ND 4.0", "CC BY-NC-ND 3.0", "CC BY-ND 4.0",
                "cc by-nc-nd", "CC-BY-NC-ND 4.0",
                "Creative Commons Attribution-NonCommercial-NoDerivatives 4.0",
                "Creative Commons Attribution Noncommercial No Derivative Works 3.0"):
        assert not is_license_allowed(lic, ALLOWED), lic


def test_gate_rejects_unknown_and_closed():
    for lic in ("unknown - verify", "", "All rights reserved", "Copyright 2024"):
        assert not is_license_allowed(lic, ALLOWED), lic


def test_manifest_nd_books_are_now_excluded():
    manifest = load_manifest()
    allowed = manifest.get("allowed_license_prefixes", ALLOWED)
    nd = [b for b in manifest.get("books", [])
          if not is_license_allowed(b["license"], allowed)]
    assert {b["filename"] for b in nd} == {
        "INTERNATIONAL.pdf",
        "technical writing.pdf",
        "writing-spaces-readings-on-writing-vol-1.pdf",
        "writing-spaces-readings-on-writing-vol-2.pdf",
        "writingspaces3.pdf",
        "writingspaces4.pdf",
        "writingspaces5.pdf",
    }
    assert len(nd) == 7
