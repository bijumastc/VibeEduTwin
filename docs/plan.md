# VibeEduTwin plan

## Verifier checklist

The Verifier (`verify()` in `main.py`) is the single gate before the learner
sees anything. It replies only in JSON:

```json
{"pass": true, "failed": [], "fix": ""}
```

- `pass`: true when every applicable rule passes.
- `failed`: rule ids (for sets: `"item N: <rule>"`) that failed.
- `fix`: one-line fix for the first failure ("" when passing).

Every twin reply and every practice item is checked before the learner sees
it. A failed twin reply is never served: the endpoint falls back to a
compliant safe reply. A failed teacher set is never published. Bank items are
structurally checked at serve time and failures are excluded.

### Twin replies (`twin_reply`)

- `not-empty`: the reply must not be empty.
- `no-generic-praise`: none of "great job", "excellent", "amazing".
- `no-invented-examples`: No invented examples: every example must come from
  the knowledge base. A reply may only quote the learner's own words,
  sentence starters with `___`, or passages marked with `...`. Any other
  quoted complete sentence fails: book examples must be served as excerpts
  with their source.

### Practice items (`practice_item`)

- `not-empty`: the prompt must be non-empty.
- `valid-type`: type must be `mcq` or `order`.
- `min-options`: at least 2 options.
- `has-answer`: answer must be non-empty.
- `answer-matches-option`: for `mcq`, the answer must match an option.
- `has-explanation`: explanation must be non-empty (learners need feedback).
- `no-invented-examples`: No invented examples: every example must come from
  the knowledge base. Generated items must cite their book source.
  The hand-curated practice
  bank (`PRACTICE_BANK`) predates this rule, is reviewed by hand, and is
  exempt; it is still checked against every structural rule above.

### Practice sets (`practice_set`)

- `non-empty`: the set must contain at least one item.
- `unique-id`: every item needs a non-empty, unique id.
- Every item must pass the full `practice_item` checklist.

### Lesson ideas (`lesson_idea`)

- `grounded-in-excerpt`: every claim in the idea text must be supported by
  the retrieved excerpt (keyword overlap per claim). On failure the builder
  re-retrieves: it tries the next excerpt until one grounds every claim.
