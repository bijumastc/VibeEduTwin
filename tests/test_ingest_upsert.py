import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import knowledge_base as kb  # noqa: E402
from ingest_knowledge import (  # noqa: E402
    UPSERT_BATCH_SIZE,
    UPSERT_RETRIES,
    upsert_verified as scripts_upsert_verified,
)

FUNCS = {
    "scripts": scripts_upsert_verified,
    "single-file": kb.upsert_verified,
}


class _Vec:
    def tolist(self):
        return [0.1, 0.2]


def _ef(docs):
    return [_Vec() for _ in docs]


class _FakeCollection:
    """Records upserts; get() can flake or permanently drop ids."""

    def __init__(self):
        self.drop = set()  # ids never returned by get()
        self.flakes_left = 0  # next N get() calls each drop their last id
        self.upserts = 0

    def upsert(self, ids, embeddings, documents, metadatas):
        self.upserts += 1
        assert len(ids) == len(embeddings) == len(documents) == len(metadatas)

    def get(self, ids, include=None):
        got = [i for i in ids if i not in self.drop]
        metas = [{"s": "x"} for _ in got]
        if self.flakes_left > 0 and metas:
            self.flakes_left -= 1
            metas[-1] = None  # id present but metadata missing, as seen live
        return {"ids": got, "metadatas": metas}


def _docs(n):
    return (
        [f"c{i}" for i in range(n)],
        [f"text {i}" for i in range(n)],
        [{"s": "x"} for _ in range(n)],
    )


@pytest.mark.parametrize("fn", FUNCS.values(), ids=FUNCS.keys())
def test_upsert_verified_retries_flaky_batches(fn):
    col = _FakeCollection()
    col.flakes_left = 2  # first read-back of each batch lacks one meta
    ids, docs, metas = _docs(12)
    nbatches = -(-12 // UPSERT_BATCH_SIZE)
    assert fn(col, _ef, ids, docs, metas) == []
    assert col.upserts > nbatches  # retries happened


@pytest.mark.parametrize("fn", FUNCS.values(), ids=FUNCS.keys())
def test_upsert_verified_reports_persistent_failures(fn):
    col = _FakeCollection()
    col.drop = {"c1", "c2"}  # never persist
    ids, docs, metas = _docs(12)
    nbatches = -(-12 // UPSERT_BATCH_SIZE)
    assert fn(col, _ef, ids, docs, metas) == ["c1", "c2"]
    # batch 1 (holding c1, c2) retried out, the rest clean first try
    assert col.upserts == UPSERT_RETRIES + (nbatches - 1)
