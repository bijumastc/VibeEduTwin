"""VibeEduTwin knowledge base: PDF guides -> ChromaDB chunks -> search test.

Pipeline:
  1. Read every *.pdf from data/knowledge/ (ignore .json, .md, ...).
  2. Extract text and remove headers, footers, page numbers, repeated lines.
  3. Split into ~400-word chunks with 50-word overlap.
  4. Tag each chunk with source, license, subject, skill.
  5. Store chunks in the local ChromaDB collection "knowledge_base".
  6. Run a small search test: 5 student questions, top 3 hits each.

Usage:
  python knowledge_base.py
  python knowledge_base.py --reset            # wipe collection first
  python knowledge_base.py --knowledge-dir <dir> --db-dir <dir>   # custom paths
"""

import argparse
import re
import sys
from pathlib import Path

# --- Settings ---------------------------------------------------------------
ROOT = Path(__file__).resolve().parent
KNOWLEDGE_DIR = ROOT / "data" / "knowledge"  # where the guide PDFs live
DEFAULT_DB_DIR = ROOT / "chroma_db"           # local ChromaDB storage
COLLECTION_NAME = "knowledge_base"
CHUNK_WORDS = 400
OVERLAP_WORDS = 50

EMBED_BATCH_SIZE = 100  # embedding-model batch (pure compute, always safe)
UPSERT_BATCH_SIZE = 5   # ChromaDB write batch: bigger batches silently lose
UPSERT_RETRIES = 5      # records on this machine, so each batch is read back
                        # and retried (see upsert_verified)

# Skill labels are detected by keyword: first match wins, else "general".
SKILL_KEYWORDS = [
    ("citation", ["citation", "cite", "reference", "plagiarism", "bibliography"]),
    ("academic tone", ["academic tone", "formal", "hedging", "objective", "passive voice"]),
    ("sentence structure", ["sentence structure", "clause", "fragment", "run-on", "complex sentence"]),
    ("paragraphing", ["paragraph", "topic sentence", "coherence", "unity"]),
    ("grammar", ["grammar", "tense", "subject-verb", "article", "punctuation", "preposition"]),
    ("vocabulary", ["vocabulary", "word choice", "synonym", "lexical"]),
    ("argument", ["argument", "thesis", "claim", "evidence", "counterargument"]),
]

# Lines that look like page numbers, e.g. "12", "Page 4", "- 7 -".
PAGE_NUMBER_PATTERNS = [
    re.compile(r"^\s*\d{1,4}\s*$"),
    re.compile(r"(?i)^\s*page\s+\d{1,4}(\s+of\s+\d{1,4})?\s*$"),
    re.compile(r"^\s*[-\u2013]\s*\d{1,4}\s*[-\u2013]\s*$"),
]

# Lines that look like index entries, e.g. "Paragraph unity ........ 123".
INDEX_PATTERNS = [
    re.compile(r"\.{3,}\s*\d{1,4}\s*$"),
    re.compile(r"^.{4,}?\s+\d{1,4}(,\s*\d{1,4}){2,}\s*$"),
]

SAMPLE_QUESTIONS = [
    "How to write a good topic sentence",
    "What is academic tone",
    "How to use citations",
    "How to structure a paragraph",
    "Common grammar mistakes in academic writing",
]


# --- Step 1+2: find PDFs ----------------------------------------------------
def find_pdf_files(knowledge_dir: Path) -> list[Path]:
    """Return sorted *.pdf files; every other file (.json, .md, ...) is ignored."""
    if not knowledge_dir.is_dir():
        return []
    return sorted(
        p for p in knowledge_dir.iterdir()
        if p.is_file() and p.suffix.lower() == ".pdf"  # skip .json, .md, etc.
    )


# --- Step 3: extract text ---------------------------------------------------
def extract_text_from_pdf(pdf_path: Path) -> list[str]:
    """Extract raw text of one PDF, page by page (needs pypdf)."""
    from pypdf import PdfReader

    reader = PdfReader(str(pdf_path))
    return [page.extract_text() or "" for page in reader.pages]


# --- Step 4: clean text -----------------------------------------------------
def strip_page_number_and_index_lines(lines: list[str]) -> list[str]:
    """Drop lines that are just a page number or an index entry."""
    kept = []
    for ln in lines:
        stripped = ln.strip()
        if any(p.match(stripped) for p in PAGE_NUMBER_PATTERNS):
            continue
        if any(p.search(stripped) for p in INDEX_PATTERNS):
            continue
        kept.append(ln)
    return kept


def remove_repeated_headers_and_footers(pages: list[list[str]]) -> list[list[str]]:
    """Drop short lines repeated at the top/bottom of many pages (headers/footers).

    A line counts as a header/footer when it is short (<= 8 words), sits in the
    first or last 4 lines of a page, and appears on >= 30% of pages. Needs at
    least 3 pages to avoid deleting real content from tiny documents.
    """
    if len(pages) < 3:
        return pages
    counts: dict[str, int] = {}
    for page in pages:
        edge_lines = page[:4] + page[-4:]  # top 4 + bottom 4 lines
        for line in set(ln.strip() for ln in edge_lines if ln.strip()):
            if len(line.split()) <= 8:
                counts[line] = counts.get(line, 0) + 1
    repeated = {ln for ln, n in counts.items() if n / len(pages) >= 0.3}
    if not repeated:
        return pages
    return [[ln for ln in page if ln.strip() not in repeated] for page in pages]


def clean_pages(pages: list[str]) -> list[str]:
    """Clean every page: page numbers, then repeated headers/footers, then whitespace."""
    split = [strip_page_number_and_index_lines(p.splitlines()) for p in pages]
    split = remove_repeated_headers_and_footers(split)
    cleaned = []
    for page in split:
        text = "\n".join(page)
        text = re.sub(r"[ \t]+", " ", text)  # collapse spaces/tabs
        text = re.sub(r"\n{3,}", "\n\n", text)  # collapse blank lines
        cleaned.append(text.strip())
    return cleaned


# --- Step 5: chunking -------------------------------------------------------
def split_into_chunks(
    words: list[str],
    chunk_size: int = CHUNK_WORDS,
    overlap: int = OVERLAP_WORDS,
) -> list[list[str]]:
    """Slide a `chunk_size`-word window over the words, stepping back `overlap` words."""
    if not words:
        return []
    if overlap >= chunk_size:
        raise ValueError("overlap must be smaller than chunk_size")
    chunks: list[list[str]] = []
    start = 0
    while start < len(words):
        end = min(start + chunk_size, len(words))
        chunks.append(words[start:end])
        if end == len(words):
            break
        start = end - overlap  # step back so chunks share `overlap` words
    return chunks


# --- Step 6: tagging --------------------------------------------------------
def detect_skill(text: str) -> str:
    """Guess the writing skill of a chunk from keywords, else "general"."""
    lowered = text.lower()
    for skill, keywords in SKILL_KEYWORDS:
        if any(keyword in lowered for keyword in keywords):
            return skill
    return "general"


def make_chunk_metadata(source: str, text: str) -> dict:
    """Build the metadata tags stored alongside each chunk."""
    return {
        "source": source,              # PDF file name
        "license": "CC BY",            # all guides here are openly licensed
        "subject": "academic writing",
        "skill": detect_skill(text),
    }


# --- Step 7: ChromaDB storage ----------------------------------------------
def get_chroma_client(db_dir: str | Path):
    """Open a persistent local ChromaDB client.

    Uses the pure-Python segment backend because the default Rust backend
    fails to open its database file on this machine (sqlite code 14).
    """
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
    """Default ONNX embeddings, but cached inside the repo (.chroma_cache/).

    The model (~83MB) downloads once on first use; the redirect keeps it
    out of the home directory, which may not be writable.
    """
    from chromadb.utils.embedding_functions import ONNXMiniLM_L6_V2

    ef = ONNXMiniLM_L6_V2()
    ef.DOWNLOAD_PATH = ROOT / ".chroma_cache" / "onnx_models" / ef.MODEL_NAME
    return ef


def upsert_verified(collection, ef, ids: list, docs: list, metas: list) -> list[str]:
    """Upsert one PDF's chunks; return ids that failed to persist.

    Embeddings are computed in big batches (fast); writes go in small batches
    and each batch is read back. A batch that does not read back fully is
    retried, because ChromaDB's sqlite consumer can drop records without
    raising (it only logs 'unable to open database file').
    """
    failed: list[str] = []
    embeddings: list = []
    for j in range(0, len(docs), EMBED_BATCH_SIZE):
        vectors = ef(docs[j:j + EMBED_BATCH_SIZE])
        embeddings.extend([v.tolist() for v in vectors])
    for j in range(0, len(docs), UPSERT_BATCH_SIZE):
        end = j + UPSERT_BATCH_SIZE
        batch_ids = ids[j:end]
        for _attempt in range(UPSERT_RETRIES):
            collection.upsert(
                ids=batch_ids,
                embeddings=embeddings[j:end],
                documents=docs[j:end],
                metadatas=metas[j:end],
            )
            got = collection.get(ids=batch_ids, include=["metadatas"])
            have = dict(zip(got.get("ids", []), got.get("metadatas", [])))
            if all(have.get(i) is not None for i in batch_ids):
                break
        else:
            failed.extend(i for i in batch_ids if have.get(i) is None)
    return failed


def build_knowledge_base(
    knowledge_dir: Path = KNOWLEDGE_DIR,
    db_dir: Path = DEFAULT_DB_DIR,
    reset: bool = False,
) -> dict:
    """Run steps 1-7: PDFs -> cleaned chunks -> ChromaDB collection."""
    pdfs = find_pdf_files(knowledge_dir)
    if not pdfs:
        print(f"No PDFs found in {knowledge_dir}. See data/knowledge/README.md.")
        return {"pdfs": 0, "chunks": 0}

    client = get_chroma_client(db_dir)
    if reset:
        try:
            client.delete_collection(COLLECTION_NAME)
        except Exception:
            pass  # collection did not exist yet
    ef = get_embedding_function()
    collection = client.get_or_create_collection(
        COLLECTION_NAME, embedding_function=ef
    )

    total_chunks = 0
    failed_all: list[str] = []
    for pdf in pdfs:
        pages = clean_pages(extract_text_from_pdf(pdf))
        words = "\n\n".join(p for p in pages if p.strip()).split()
        word_chunks = split_into_chunks(words)
        print(f"{pdf.name}: {len(words)} words -> {len(word_chunks)} chunks")
        ids, docs, metas = [], [], []
        for i, word_chunk in enumerate(word_chunks):
            text = " ".join(word_chunk)
            ids.append(f"{pdf.stem}-c{i:04d}")
            docs.append(text)
            metas.append(make_chunk_metadata(pdf.name, text))
        failed_ids = upsert_verified(collection, ef, ids, docs, metas)
        if failed_ids:
            print(f"FAILED {pdf.name}: {len(failed_ids)} chunks did not persist.")
        failed_all.extend(failed_ids)
        total_chunks += len(docs) - len(failed_ids)

    print(f"Done: {total_chunks} chunks from {len(pdfs)} PDFs.")
    if failed_all:
        print(f"{len(failed_all)} chunks FAILED to persist: {failed_all[:20]}")
    return {"pdfs": len(pdfs), "chunks": total_chunks, "failed": failed_all}


# --- Step 8: search test ----------------------------------------------------
def test_knowledge_base(db_dir: Path = DEFAULT_DB_DIR, n_results: int = 3) -> int:
    """Ask the 5 sample questions and print the top hits for each."""
    client = get_chroma_client(db_dir)
    try:
        collection = client.get_collection(
            COLLECTION_NAME, embedding_function=get_embedding_function()
        )
    except Exception:
        print(f"No collection '{COLLECTION_NAME}' in {db_dir}. Run the build first.")
        return 1

    count = collection.count()
    print(f"Collection '{COLLECTION_NAME}': {count} chunks\n")
    if count == 0:
        print("Collection is empty. Add PDFs and run the build first.")
        return 1

    for i, question in enumerate(SAMPLE_QUESTIONS, 1):
        print(f"Q{i}: {question}")
        result = collection.query(query_texts=[question], n_results=n_results)
        docs = result.get("documents", [[]])[0]
        metas = result.get("metadatas", [[]])[0]
        distances = result.get("distances", [[]])[0]
        for rank, (doc, meta, dist) in enumerate(zip(docs, metas, distances), 1):
            snippet = (doc or "")[:300].replace("\n", " ")
            print(f"  [{rank}] dist={dist:.3f} source={meta.get('source')} "
                  f"skill={meta.get('skill')} license={meta.get('license')}")
            print(f"       {snippet}...")
        print()
    return 0


# --- Entry point ------------------------------------------------------------
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build and test the knowledge base.")
    parser.add_argument("--knowledge-dir", default=str(KNOWLEDGE_DIR))
    parser.add_argument("--db-dir", default=str(DEFAULT_DB_DIR))
    parser.add_argument("--reset", action="store_true", help="Wipe the collection first.")
    parser.add_argument("--skip-test", action="store_true", help="Build only, no search test.")
    args = parser.parse_args(argv)

    build_knowledge_base(Path(args.knowledge_dir), Path(args.db_dir), reset=args.reset)
    if args.skip_test:
        return 0
    return test_knowledge_base(Path(args.db_dir))


if __name__ == "__main__":
    sys.exit(main())
