# Knowledge PDFs (openly licensed only)

This folder holds the curated CC-licensed writing guides (41 books).
Every file is listed in `manifest.json` with the license verified from
the book's own copyright page. Two exact-duplicate files are also present
but intentionally NOT in the manifest, so ingest skips them:
`Communication for Business Success (.pdf` and `WritingGuide-WEB (1).pdf`
(you can delete these copies to save ~130MB).

To add a book: drop the PDF here, verify its license from its copyright
page, and add a matching entry to `manifest.json`.

Only openly licensed books are ingested. The ingest script refuses
files whose license is not in `allowed_license_prefixes`.
