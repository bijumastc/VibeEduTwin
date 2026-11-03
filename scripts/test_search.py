"""Search the ingested knowledge base with 5 sample student questions."""

import argparse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB_DIR = ROOT / "chroma_db"
COLLECTION_NAME = "vibeedutwin_knowledge"

SAMPLE_QUESTIONS = [
    "How do I write a good topic sentence for a paragraph?",
    "When do I use 'a', 'an' and 'the' in English sentences?",
    "How do I structure an essay introduction with a thesis statement?",
    "How do I join two small sentences using because, but and so?",
    "How do I write a conclusion that summarises my main points?",
]


def main(argv=None) -> int:
    from chroma_setup import get_client, get_embedding_function

    parser = argparse.ArgumentParser(description="Test search over ChromaDB knowledge.")
    parser.add_argument("--db-dir", default=str(DEFAULT_DB_DIR))
    parser.add_argument("--n-results", type=int, default=3)
    args = parser.parse_args(argv)

    client = get_client(args.db_dir)
    try:
        collection = client.get_collection(
            COLLECTION_NAME, embedding_function=get_embedding_function()
        )
    except Exception:
        print(f"No collection '{COLLECTION_NAME}' in {args.db_dir}. Run ingest first.")
        return 1

    count = collection.count()
    print(f"Collection '{COLLECTION_NAME}': {count} chunks\n")
    if count == 0:
        print("Collection is empty. Add PDFs and run ingest first.")
        return 1

    for i, q in enumerate(SAMPLE_QUESTIONS, 1):
        print(f"Q{i}: {q}")
        res = collection.query(query_texts=[q], n_results=args.n_results)
        docs = res.get("documents", [[]])[0]
        metas = res.get("metadatas", [[]])[0]
        distances = res.get("distances", [[]])[0]
        for rank, (doc, meta, dist) in enumerate(zip(docs, metas, distances), 1):
            snippet = (doc or "")[:300].replace("\n", " ")
            print(f"  [{rank}] dist={dist:.3f} source={meta.get('source')} "
                  f"chapter={meta.get('chapter')} skill={meta.get('skill')} "
                  f"license={meta.get('license')}")
            print(f"       {snippet}...")
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
