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

### Worked models (`worked_model`)

- `has-controlling-idea`: the model must carry a clear controlling idea
  (a claim verb such as explains, shows, should, because, or why).
- `not-task-topic`: the model must not share the task's topic word, so it
  cannot be copied as the learner's answer. On failure the steps are
  served without the model.

### Spark drafts (`excerpt_grounding`)

- `grounded-in-excerpts`: every drafted item must quote an excerpt sentence
  word-for-word in its prompt or options. Ungrounded drafts are dropped and
  template-built items fill the count, so the set stays excerpt-only.

### Attempt assessments (`assessor`)

- `valid-score`: the score is 0, 1 or 2.
- `feedback-shape`: feedback runs 2-4 short sentences.
- `quotes-learner`: on-task feedback quotes the learner's own words (skipped
  for off-task, nonsense and copied tries). On failure the fixed ladder runs.
  Practice answers use the same checklist with the chosen option as the
  learner's words; rejected drafts fall back to templates.
- `grammar-quotes`: every grammar fix copies its error exactly from the
  learner's text.
- `simple-english`: no formal words, no sentence over 25 words.
- `no-generic-praise`: none of "great job", "excellent", "amazing". The
  fixed mood lines ("Outstanding work!" and friends) carry no banned
  phrase, so celebrations pass while generic praise still fails.

### Feedback cards (`feedback`)

- `quotes-in-text`: every quote (strength, problems, model before-line)
  must exist in the learner's paragraph.
- `one-rewrite`: the model rewrites at most one sentence, as one sentence,
  different from the before-line.
- `simple-english`: no formal words, no sentence over 25 words.
- `no-generic-praise`: none of "great job", "excellent", "amazing".
  Rejected Spark drafts retry (max 2 regens), then the deterministic
  template card (strength, two problems, and one rewrite when the text
  allows) is served.
  The motivation layer (twin message, grammar fixes, word tips, improve
  points, critical tip, next goal) is deterministic: every fix copies the
  learner's exact words, and the same checklist guards the served card.
  Grammar fixes include spelling: an offline checker (`spelling.py`, no
  network) corrects slips like "hakathon" to "hackathon"; names stay
  untouched and the model rewrite carries the correction.

## Rubric

The fixed 7-skill rubric, one short line per level. Mirrored exactly in
`DIAGNOSE_RUBRIC` in `main.py` (sent to Muse Spark with every diagnosis) and
served at `GET /rubric` for the "How I'm scored" link.

### Grammar

- L1: Frequent errors block meaning.
- L2: Many errors; meaning mostly clear.
- L3: Some errors; meaning clear.
- L4: Few, minor errors.
- L5: Rare, minor errors.

### Vocabulary

- L1: Everyday words only, often repeated.
- L2: Mostly everyday words; a few academic words.
- L3: Some academic words, sometimes misused.
- L4: Academic and subject terms, mostly used correctly.
- L5: Precise academic and subject terms.

### Sentence structure

- L1: Short or run-on sentences.
- L2: Mostly simple sentences; some joined correctly.
- L3: Mix of simple and compound sentences.
- L4: Varied sentences with few errors.
- L5: Varied, controlled sentences.

### Paragraphing

- L1: No clear topic sentence; ideas listed.
- L2: Topic sentence present but vague.
- L3: Clear topic sentence with some support.
- L4: Clear topic sentence, relevant support, some links.
- L5: Clear topic sentence, support, and a link to the next idea.

### Argument

- L1: Opinions without reasons.
- L2: A claim with one weak reason.
- L3: A claim with reasons but little evidence.
- L4: A claim with reasons and evidence.
- L5: Claim, evidence, and a counterpoint answered.

### Using sources

- L1: No sources.
- L2: A source mentioned vaguely, no citation.
- L3: A source cited, format inconsistent.
- L4: Correct citation, some copied wording.
- L5: Correct paraphrase and citation.

### Academic tone

- L1: Conversational.
- L2: Mostly conversational, a few formal phrases.
- L3: Mix of formal and informal.
- L4: Mostly formal and objective.
- L5: Formal, objective, and appropriately hedged.

## Demo kit

Scripted recording flow. Demo mode is on when `DEMO_MODE=true` in `.env`
(off by default); the app shows a small "Demo mode" label. In demo mode
only the exact weak and improved paragraphs use the fixed script; any
other text calls Muse Spark and Muse Voice Transcribe live (diagnosis,
feedback, scan, voice), like Teacher Studio, with the usual fallback.
The twin reply, the scaffold Assessor, and practice judging stay fixed
or deterministic. `scripts/reset_demo.py` clears the demo learner (id 1)
so the flow can be recorded several times; restart the backend too
(issued sets and scaffold attempts live in memory).

Demo learner: Sciences discipline, no history.

Weak paragraph:

> Plastic is very big problem. In my village the river is full of plastic.
> People throw the waste in river and fish is dying. Government should do
> something. Also the students also should know. So plastic is dangerous
> for nature and we must stop it.

Fixed diagnosis (level, reason, evidence quote):

- Paragraphing 1: No clear topic sentence; ideas are listed.
  "Plastic is very big problem."
- Academic tone 1: Conversational. "Government should do something."
- Using sources 1: No sources. "In my village the river is full of plastic."
- Grammar 2: Missing articles; repeated "also".
  "People throw the waste in river"
- Argument 2: A claim with one weak reason.
  "So plastic is dangerous for nature"
- Sentence structure 2: Mostly short simple sentences.
  "Also the students also should know."
- Vocabulary 2: Mostly everyday words. "very big problem"

Weakest skill: Paragraphing. Any other paragraph in demo mode is
diagnosed and given feedback by live Muse Spark (heuristic + template
fallback without a key). Fixed feedback cards are served for the weak
paragraph (first sentence as the main problem, one model rewrite) and
the improved paragraph (sources and long lines as the two problems).
Both scripted cards use the motivation layout: twin message with the
learner's first name, three grammar fixes for the weak paragraph (none
for the clean improved one), word tips, improve points with a
critical-thinking tip, and a next goal.

Fixed twin response (simple English only), served when the demo
learner's latest draft is the weak paragraph (the fixed script bypasses
the twin Verifier, which only accepts quotes from the chat message):

> You are saying plastic in your village river is killing fish, and
> people must act. Your main problem: the first sentence, 'Plastic is
> very big problem', does not say what this paragraph will prove. Try
> starting like this: 'Plastic waste is harming ______ in ______.'

Scripted Assessor response for this exact Topic sentences try (fixed
script, no Spark, no verifier; any other try keeps the fixed ladder):
"Freedom struggle ensured the peace and calm that we enjoy today".
Score 1 of 2: "You named a topic and said what it achieved - that is
the right shape." / "'the peace and calm that we enjoy today' is too
broad for one paragraph to prove. Which struggle, and which result?
Also start with 'The'." / model "Public libraries helped many village
students prepare for college." / "Your turn: 'The Indian freedom
struggle gave ordinary people ______.'"

Practice set (Paragraphing, Level 1), served for every Paragraphing L1
request in demo mode (it wins over published sets so recordings stay
identical):

1. Recognise: Which is the best topic sentence for a paragraph about
   phones in college? (a) I like phones. (b) Mobile phones can support
   learning in college when clear rules are followed. (c) Phones are
   there. (d) Many students have phones. Answer: b.
2. Repair: Put these in order to make a paragraph: [A] For example,
   students can look up difficult terms during a lecture. [B] Mobile
   phones can support learning in college when clear rules are followed.
   [C] Therefore, colleges should allow phones with clear limits.
   [D] They give instant access to reference material.
   Answer: B, D, A, C. (Tap options need distractors, not in the kit:
   A, B, C, D and D, C, B, A.)
3. Produce: Complete the topic sentence for your own paragraph:
   "Plastic waste in rivers ______." Pass if it states one main idea in
   formal English: exactly one sentence, at least 6 words, starts with a
   capital, ends with punctuation, no chatty words.

Two sets at 80% or more show the level-up screen: Paragraphing
Level 1 → 2, with the growth chart. Demo practice shows the level-up
without saving the bump, so the improved paragraph still compares 1 → 2.

Improved paragraph (for the comparison step):

> Plastic waste is seriously harming the river in my village. People
> throw bottles and bags into the water, and the fish are dying. The
> panchayat should set up waste bins near the river, and students can
> help by spreading awareness.

Expected comparison: "In your last paragraph you had no clear topic
sentence; this time your first sentence names the problem and the
place." Other skills keep their heuristic levels; Paragraphing is
pinned to 2. Paragraphing 1 → 2.

## Daily structure

Named levels, shown everywhere a level appears (chips, bars, Practice,
Write, Teacher): L1 Starter, L2 Elementary, L3 Intermediate,
L4 Upper-Intermediate, L5 Advanced. The learner's overall level is the
weakest skill's level.

"Today's session" on My Level is one unit at the learner's level:
(1) write a paragraph on their discipline topic with a word target by
level (50 / 80 / 120 / 160 / 200); (2) read the feedback and fix it;
(3) one short practice set on their next win. Then "Session complete!"
with the goodbye summary. The daily goal is 3 sessions, shown as 3
dots. Leaving mid-session shows "Continue today's session" on return.
Learn and Practice stay open for anyone who wants more.

## Guided and challenge modes

Each skill starts in guided mode until the learner completes 6
activities in it (a Write submission, Learn task, or practice set
counts as one): the idea and one worked example (different topic) come
first, then the task, then full feedback with "Compare with a polished
version" after the rewrite. After 6 activities, or from Level 3,
the skill switches to challenge mode: the productive-struggle ladder
with "Show me now" available. The task card shows progress toward
challenge mode ("Guided · 4 of 6 activities").

## Topic-sentence Check

Under the submit button of the Topic sentences Learn task, a Check
section asks the learner to rate their own line ("My sentence is good"
/ "It needs work") before any verdict is shown. The twin replies with
an inspiring message tuned to the self-rating, the verdict, where the
line fails (one sentence, names the topic, states a point, mechanics),
how to improve each point, the book rule, and an improved version:
the learner's own line cleaned up when it states a point, otherwise a
same-topic model. Check changes no score or activity; each attempt is
logged for How it decided.
