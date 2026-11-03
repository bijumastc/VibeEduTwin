"""Throwaway survey: build all 36 lessons, flag visible defects."""
import os
import re
import sys

sys.path.insert(0, r"C:\Users\Admin\vibeedutwin")
import main

DISCIPLINES = ["Sciences", "Technology", "Medicine", "Arts & Humanities",
               "Commerce & Management", "Social Sciences"]

CRUFT = ["\u25e6", "\u2022", "\u25aa", "\u25cf", "\u2192", "\u21d2", "|",
         "[", "__", "  "]


def flags(kind, text):
    out = []
    if text == main.NO_VERIFIED_EXAMPLE:
        return ["NO_VERIFIED"]
    if len(text) < 20:
        out.append("SHORT")
    for c in CRUFT:
        if c in text:
            out.append(f"CRUFT:{ord(c):04X}")
    if re.match(r"^\d{2,4}\s+[A-Z]", text):
        out.append("PAGE_NUM")
    m = re.search(r"[A-Za-z]", text)
    if m and m.group(0).islower() and not re.match(r"(?i)(e\.g\.|i\.e\.)", text):
        out.append("LOWER_START")
    if text.endswith("?"):
        out.append("QUESTION")
    if not re.search(r"[.!?][\"'\u201d]?$", text):
        out.append("NO_TERMINAL")
    if re.search(r"'s[a-z]", text):
        out.append("S_GLUE")
    if re.search(r"[A-Z][a-z]+\s+\d{2,3}\s+[A-Z]", text):
        out.append("RUNNING_HEAD")
    if re.search(r"\s\d{1,2}\.$", text):
        out.append("TRAIL_NUM")
    if re.search(r"(?i)\b(canvas|blackboard|moodle)\b", text):
        out.append("LMS")
    if re.search(r"(?i)except where otherwise noted|all rights reserved", text):
        out.append("BOILERPLATE")
    if re.search(r"(?i)\bchapter\s+\d+", text):
        out.append("CHAPTER_REF")
    if re.search(r"\b(\w+(?:\s+\w+){1,2})\s+\1\b", text, re.IGNORECASE):
        out.append("REPEAT_RUN")
    if main._artifact_count(text) > 0:
        out.append("DIRTY")
    if kind == "example":
        low = text.lower()
        if any(t in low for t in ("quiz", "syllabus")):
            out.append("SYLLABUS_WORD")
    return out


lines = []
bad = 0
for d in DISCIPLINES:
    for mod in main.discipline_modules(d):
        mid = mod["id"]
        try:
            les = main.build_lesson(d, mid)
        except Exception as exc:  # noqa: BLE001 - survey must continue
            lines.append(f"{d} / {mid}: BUILD_FAIL {exc!r}")
            bad += 1
            continue
        idea, example = les["idea"]["text"], les["example"]["text"]
        fl = [f"idea:{f}" for f in flags("idea", idea)]
        fl += [f"ex:{f}" for f in flags("example", example)]
        if main._overlaps_rule(example, idea):
            fl.append("EX_OVERLAPS_IDEA")
        books = [(b.get("title"), b.get("license")) for b in les["based_on"]]
        if not books and "NO_VERIFIED" not in " ".join(fl):
            fl.append("NO_BOOKS")
        for title, lic in books:
            if not title or title == "unknown" or ".pdf" in (title or ""):
                fl.append(f"BAD_TITLE:{title!r}")
            if not lic:
                fl.append("NO_LICENSE")
        status = "OK " if not fl else "BAD"
        if fl:
            bad += 1
        lines.append(f"{status} {d} / {mid} :: {' '.join(fl) or '-'}")
        lines.append(f"    IDEA: {idea[:170]}")
        lines.append(f"    EX:   {example[:170]}")
        lines.append(f"    BOOKS: {books}")

lines.append(f"--- {bad} lessons flagged ---")
out = os.path.join(r"C:\Users\Admin\vibeedutwin", "lesson36.txt")
__import__("pathlib").Path(out).write_text("\n".join(lines), encoding="utf-8")
print(f"done, {bad} flagged -> {out}")
