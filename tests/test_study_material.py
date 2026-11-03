import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import main  # noqa: E402
from ingest_knowledge import COLLECTION_NAME as SCRIPTS_COLLECTION  # noqa: E402


class _FakeCollection:
    def __init__(self, docs):
        self._docs = docs  # [(text, metadata), ...]

    def count(self):
        return len(self._docs)

    def query(self, query_texts, n_results):
        docs = [d for d, _ in self._docs[:n_results]]
        metas = [m for _, m in self._docs[:n_results]]
        return {"documents": [docs], "metadatas": [metas]}


class _FakeClient:
    def __init__(self, collections):
        self._collections = collections

    def get_collection(self, name, embedding_function=None):
        if name not in self._collections:
            raise ValueError(f"no collection {name}")
        return self._collections[name]


def _install_fake_kb(monkeypatch, collections):
    fake = types.ModuleType("knowledge_base")
    fake.DEFAULT_DB_DIR = "unused"
    fake.COLLECTION_NAME = "knowledge_base"
    fake.get_chroma_client = lambda db_dir: _FakeClient(collections)
    fake.get_embedding_function = lambda: None
    monkeypatch.setitem(sys.modules, "knowledge_base", fake)


def test_study_material_matches_scripts_collection_name():
    assert main.SCRIPTS_KB_COLLECTION == SCRIPTS_COLLECTION


def test_study_material_falls_back_to_scripts_collection(monkeypatch):
    docs = [("first chunk", {"source": "guide.pdf", "skill": "paragraphing",
                             "license": "CC BY 4.0"})]
    _install_fake_kb(monkeypatch, {"vibeedutwin_knowledge": _FakeCollection(docs)})
    assert main.study_material("Paragraphing") == [
        {"source": "guide.pdf", "skill": "paragraphing", "license": "CC BY 4.0",
         "text": "first chunk"}
    ]


def test_study_material_prefers_primary_collection(monkeypatch):
    primary = [("primary chunk", {"source": "a.pdf", "skill": "grammar",
                                  "license": "CC BY-NC 4.0"})]
    scripts = [("scripts chunk", {"source": "b.pdf", "skill": "grammar",
                                  "license": "CC BY 4.0"})]
    _install_fake_kb(monkeypatch, {
        "knowledge_base": _FakeCollection(primary),
        "vibeedutwin_knowledge": _FakeCollection(scripts),
    })
    got = main.study_material("Grammar")
    assert [g["text"] for g in got] == ["primary chunk"]


def test_study_material_empty_when_no_guides(monkeypatch):
    _install_fake_kb(monkeypatch, {})
    assert main.study_material("Grammar") == []
