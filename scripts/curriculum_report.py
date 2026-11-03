"""Report which curriculum disciplines/modules have verified excerpts.

Runs the same rule/example ChromaDB queries the Learn tab uses and prints a
coverage table, so gaps ("No verified example in our library yet.") are
visible at a glance.

Usage:
  python scripts/curriculum_report.py
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import main  # noqa: E402


def build_coverage(excerpt_fn):
    """Check every discipline x module with excerpt_fn(query, sentences).

    Returns rows of {discipline, module, rule_ok, rule_source, example_ok,
    example_source}. excerpt_fn is normally main.verified_excerpt; tests pass
    a stub.
    """
    rows = []
    for name, genre in main.DISCIPLINE_GENRES.items():
        for module in main.discipline_modules(name):
            rule = excerpt_fn(main.module_rule_query(module), 3)
            example = excerpt_fn(main.module_example_query(module, genre), 3)
            rows.append({
                "discipline": name,
                "module": module["title"],
                "rule_ok": rule["source"] is not None,
                "rule_source": rule["source"] or "-",
                "example_ok": example["source"] is not None,
                "example_source": example["source"] or "-",
            })
    return rows


def print_report(rows):
    print(f"{'Discipline':22} {'Module':22} {'Rule':5} {'Example':7} Source")
    print("-" * 100)
    gaps = 0
    for row in rows:
        rule = "YES" if row["rule_ok"] else "GAP"
        example = "YES" if row["example_ok"] else "GAP"
        if not row["rule_ok"] or not row["example_ok"]:
            gaps += 1
        source = row["rule_source"]
        if row["example_source"] != row["rule_source"]:
            source += f" / {row['example_source']}"
        print(f"{row['discipline']:22} {row['module']:22} {rule:5} {example:7} {source}")
    print("-" * 100)
    total = len(rows)
    print(f"{total - gaps}/{total} modules fully covered; {gaps} with gaps.")


def main_cli() -> int:
    print_report(build_coverage(main.verified_excerpt))
    return 0


if __name__ == "__main__":
    raise SystemExit(main_cli())
