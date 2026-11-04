"""Reset the demo learner (id 1) so the demo can be recorded again.

Clears drafts, scores, events, practice results, and writing samples;
keeps the learner row on the Sciences discipline. Restart the backend too
(issued sets and scaffold attempts live in memory).

Usage:
  python scripts/reset_demo.py
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import learner_store as store  # noqa: E402


def main() -> None:
    learner_id = 1
    store.reset_learner(learner_id)
    learner = store.get_learner(learner_id)
    print(f"Demo learner reset: id={learner_id} "
          f"discipline={learner['discipline']} "
          f"drafts={len(store.get_drafts(learner_id))} "
          f"scores={len(store.get_skill_scores(learner_id))} "
          f"events={len(store.get_events(learner_id))}")


if __name__ == "__main__":
    main()
