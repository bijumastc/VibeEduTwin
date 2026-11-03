"""Shared ChromaDB client setup for VibeEduTwin.

Two environment-specific choices live here:

1. Legacy segment backend: chromadb 1.x defaults to a Rust sqlite backend
   that fails to open its database file on this machine
   ("unable to open database file", sqlite code 14), so we pin the
   pure-Python segment implementation instead. Needs `chroma-hnswlib`.
2. Local ONNX model cache: the default embedding model downloads to
   `~/.cache/chroma`, which may not be writable. We redirect it to
   `<repo>/.chroma_cache/` (gitignored).
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODEL_CACHE_DIR = ROOT / ".chroma_cache" / "onnx_models"


def get_client(db_dir: str | Path):
    import chromadb
    from chromadb.config import Settings

    return chromadb.Client(
        Settings(
            is_persistent=True,
            persist_directory=str(db_dir),
            chroma_api_impl="chromadb.api.segment.SegmentAPI",
            anonymized_telemetry=False,
        )
    )


def get_embedding_function():
    from chromadb.utils.embedding_functions import ONNXMiniLM_L6_V2

    ef = ONNXMiniLM_L6_V2()
    ef.DOWNLOAD_PATH = MODEL_CACHE_DIR / ef.MODEL_NAME
    return ef
