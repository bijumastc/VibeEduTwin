"""Ingest openly licensed writing-guide PDFs into ChromaDB.

Reads PDFs from data/knowledge/, cleans headers/page numbers/indexes,
splits into ~400-word chunks with 50-word overlap, tags each chunk with
source, chapter, license, subject, skill, and stores in ChromaDB.
"""

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
KNOWLEDGE_DIR = ROOT / "data" / "knowledge"
MANIFEST_PATH = KNOWLEDGE_DIR / "manifest.json"
DEFAULT_DB_DIR = ROOT / "chroma_db"
COLLECTION_NAME = "vibeedutwin_knowledge"

CHUNK_WORDS = 400
OVERLAP_WORDS = 50

EMBED_BATCH_SIZE = 100  # embedding-model batch (pure compute, always safe)
UPSERT_BATCH_SIZE = 5   # ChromaDB write batch: bigger batches silently lose
UPSERT_RETRIES = 5      # records on this machine, so each batch is read back
                        # and retried (see upsert_verified)

PAGE_NUMBER_PATTERNS = [
    re.compile(r"^\s*\d{1,4}\s*$"),
    re.compile(r"(?i)^\s*page\s+\d{1,4}(\s+of\s+\d{1,4})?\s*$"),
    re.compile(r"^\s*[-\u2013]\s*\d{1,4}\s*[-\u2013]\s*$"),
]

INDEX_PATTERNS = [
    re.compile(r"\.{3,}\s*\d{1,4}\s*$"),  # term ........ 123
    re.compile(r"^.{4,}?\s+\d{1,4}(,\s*\d{1,4}){2,}\s*$"),  # term 12, 45, 78
]

CHAPTER_PATTERN = re.compile(
    r"(?i)\b(chapter|unit|module|part)\s+\d+[^\n.]{0,80}"
)

SKILL_KEYWORDS = [
    ("paragraph-writing", ["topic sentence", "paragraph", "coherence", "unity"]),
    ("grammar", ["tense", "subject-verb", "article", "preposition", "punctuation"]),
    ("essay-structure", ["thesis", "introduction", "conclusion", "essay", "outline"]),
    ("referencing", ["citation", "reference", "plagiarism", "bibliography"]),
    ("vocabulary", ["vocabulary", "word choice", "linker", "connector", "transition"]),
]


def clean_page_lines(lines: list[str]) -> list[str]:
    cleaned: list[str] = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        if any(p.match(stripped) for p in PAGE_NUMBER_PATTERNS):
            continue
        if any(p.search(stripped) for p in INDEX_PATTERNS):
            continue
        cleaned.append(line.rstrip())
    return cleaned


def remove_repeated_headers(pages: list[list[str]], min_ratio: float = 0.3) -> list[list[str]]:
    if len(pages) < 3:
        return pages
    counts: dict[str, int] = {}
    for page in pages:
        for line in set(l.strip() for l in page[:4] if l.strip()):
            if len(line.split()) <= 8:
                counts[line] = counts.get(line, 0) + 1
    headers = {h for h, c in counts.items() if c / len(pages) >= min_ratio}
    if not headers:
        return pages
    return [[l for l in page if l.strip() not in headers] for page in pages]


def clean_text(text: str) -> str:
    lines = text.splitlines()
    lines = clean_page_lines(lines)
    text = "\n".join(lines)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def clean_pages(pages: list[str]) -> list[str]:
    split = [p.splitlines() for p in pages]
    split = [clean_page_lines(p) for p in split]
    split = remove_repeated_headers(split)
    return [clean_text("\n".join(p)) for p in split]


def split_words(words: list[str], size: int = CHUNK_WORDS, overlap: int = OVERLAP_WORDS) -> list[list[str]]:
    if not words:
        return []
    if overlap >= size:
        raise ValueError("overlap must be smaller than size")
    chunks: list[list[str]] = []
    start = 0
    while start < len(words):
        end = min(start + size, len(words))
        chunks.append(words[start:end])
        if end == len(words):
            break
        start = end - overlap
    return chunks


def detect_chapter(text: str) -> str:
    all_matches = [m.group(0).strip() for m in CHAPTER_PATTERN.finditer(text)]
    if all_matches:
        return " ".join(all_matches[-1].split())[:120]
    return "unknown"


def infer_skill(text: str) -> str:
    lowered = text.lower()
    for skill, keywords in SKILL_KEYWORDS:
        if any(k in lowered for k in keywords):
            return skill
    return "general-writing"


def load_manifest(manifest_path: Path = MANIFEST_PATH) -> dict:
    if not manifest_path.exists():
        return {"books": [], "allowed_license_prefixes": ["CC BY", "CC-BY", "CC0"]}
    return json.loads(manifest_path.read_text(encoding="utf-8"))


def has_no_derivatives_clause(license_str: str) -> bool:
    """True when the license forbids derivatives, in any common spelling.

    Matches the ND license element ("CC BY-NC-ND", "CC-BY-NC-ND", "CC BY-ND")
    as well as prose forms ("NoDerivatives", "No Derivative Works").
    """
    tokens = re.sub(r"[\s\-_]+", " ", (license_str or "").strip().upper()).split()
    if "ND" in tokens:
        return True
    compact = "".join(tokens)
    return "NODERIVATIVE" in compact  # also covers NODERIVATIVES


def is_license_allowed(license_str: str, allowed: list[str]) -> bool:
    """Allowed prefixes apply only to the non-ND CC BY family (plus CC0/PD).

    Any NoDerivatives license is excluded even when it matches a prefix,
    since e.g. "CC BY-NC-ND" starts with "CC BY".
    """
    if has_no_derivatives_clause(license_str):
        return False
    text = (license_str or "").strip().lower()
    return any(text.startswith(p.lower()) for p in allowed)


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


def extract_pdf_pages(pdf_path: Path) -> list[str]:
    from pypdf import PdfReader

    reader = PdfReader(str(pdf_path))
    pages: list[str] = []
    for page in reader.pages:
        pages.append(page.extract_text() or "")
    return pages


def ingest_pdfs(knowledge_dir: Path, db_dir: Path, reset: bool = False) -> dict:
    from chroma_setup import get_client, get_embedding_function

    manifest_path = knowledge_dir / "manifest.json"
    if not manifest_path.exists():
        manifest_path = MANIFEST_PATH
    manifest = load_manifest(manifest_path)
    allowed = manifest.get("allowed_license_prefixes", ["CC BY"])
    book_meta = {b["filename"]: b for b in manifest.get("books", [])}

    pdfs = sorted(knowledge_dir.glob("*.pdf"))
    if not pdfs:
        print(f"No PDFs found in {knowledge_dir}. See data/knowledge/README.md.")
        return {"pdfs": 0, "chunks": 0, "skipped": []}

    client = get_client(db_dir)
    if reset:
        try:
            client.delete_collection(COLLECTION_NAME)
        except Exception:
            pass
    ef = get_embedding_function()
    collection = client.get_or_create_collection(
        COLLECTION_NAME, embedding_function=ef
    )

    total_chunks = 0
    skipped: list[str] = []
    failed: list[str] = []
    for pdf in pdfs:
        meta = book_meta.get(pdf.name, {})
        license_str = meta.get("license", "unknown - verify")
        subject = meta.get("subject", "academic-writing")
        if license_str.startswith("unknown") or not is_license_allowed(license_str, allowed):
            print(f"SKIP {pdf.name}: license '{license_str}' not openly licensed.")
            skipped.append(pdf.name)
            continue
        pages = extract_pdf_pages(pdf)
        pages = clean_pages(pages)
        full_text = "\n\n".join(p for p in pages if p.strip())
        words = full_text.split()
        word_chunks = split_words(words)
        print(f"{pdf.name}: {len(words)} words -> {len(word_chunks)} chunks")
        ids, docs, metas = [], [], []
        for i, wc in enumerate(word_chunks):
            text = " ".join(wc)
            ids.append(f"{pdf.stem}-c{i:04d}")
            docs.append(text)
            metas.append({
                "source": pdf.name,
                "chapter": detect_chapter(text),
                "license": license_str,
                "subject": subject,
                "skill": infer_skill(text),
            })
        failed_ids = upsert_verified(collection, ef, ids, docs, metas)
        if failed_ids:
            print(f"FAILED {pdf.name}: {len(failed_ids)} chunks did not persist.")
        failed.extend(failed_ids)
        total_chunks += len(docs) - len(failed_ids)

    print(f"Done: {total_chunks} chunks from {len(pdfs) - len(skipped)} PDFs. Skipped: {skipped}")
    if failed:
        print(f"{len(failed)} chunks FAILED to persist: {failed[:20]}")
    return {"pdfs": len(pdfs) - len(skipped), "chunks": total_chunks,
            "skipped": skipped, "failed": failed}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Ingest CC-licensed PDFs into ChromaDB.")
    parser.add_argument("--knowledge-dir", default=str(KNOWLEDGE_DIR))
    parser.add_argument("--db-dir", default=str(DEFAULT_DB_DIR))
    parser.add_argument("--reset", action="store_true", help="Delete collection before ingest.")
    args = parser.parse_args(argv)
    result = ingest_pdfs(Path(args.knowledge_dir), Path(args.db_dir), reset=args.reset)
    return 1 if result["failed"] else 0


if __name__ == "__main__":
    sys.exit(main())
