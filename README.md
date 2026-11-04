# VibeEduTwin

**An adaptive academic-writing practice loop for undergraduates from Malayalam and other vernacular-medium backgrounds.**

Built for the Meta Global AI Developer Hackathon 2026 · Indie Developer Track · Theme: Build for Your World

Demo video: [ADD LINK] · Architecture: [ARCHITECTURE.md](ARCHITECTURE.md)

---

## The problem

Many students in Kerala and across India study at school in Malayalam or another Indian language, then meet English-medium academic writing at college. They often have strong ideas but weak control of topic sentences, paragraph development, citation and academic tone. Personal feedback on writing is scarce: one teacher may have a hundred students. Generic AI tools make it worse, because they write the essay for the student and the student learns nothing.

## What VibeEduTwin does

VibeEduTwin is a writing twin that coaches through a structured practice loop, not a chat box.

1. **Write:** the learner types, speaks or photographs a handwritten paragraph. They can also ask questions in Malayalam, Manglish or another Indian language.
2. **Diagnose:** Muse Spark scores the paragraph on a fixed 7-skill rubric (grammar, vocabulary, sentence structure, paragraphing, argument, using sources, academic tone). Every score quotes the learner's own words as evidence.
3. **Feedback:** the learner gets one real strength, the main problems with what is wrong and why, one model sentence (before → after), and a "your turn" prompt to fix the rest themselves.
4. **Learn:** a curriculum of 6 disciplines × 9 modules, from topic sentences to the discipline's own genre (lab report, technical report, case report, essay, business report, research report). Mechanics of writing, APA/MLA referencing and academic vocabulary are included. Every rule and example comes from open-licensed textbooks.
5. **Practise:** productive-struggle scaffolding. The learner tries first, then gets a guiding question, a hint, a real book example, and finally rewrites. Practice moves from recognise to repair to produce to apply. Every answer is assessed.
6. **Grow:** levels per skill, a draft-by-draft comparison ("In your last paragraph you had no topic sentence; this time…"), and a hint-use trend that shows growing independence.

**Teachers** type one plain-language request, such as "5 practice items on thesis statements for first-year Commerce students at Level 2". The app generates items from real excerpts, the Verifier checks them, and the teacher publishes them to their class.

## Design principles

- **Coach, never ghost-writer.** The app rewrites at most one sentence as a model. The learner always writes the rest.
- **Grounded, not invented.** Teaching content comes from open-licensed books. Sources come from the database, not the model. If no suitable excerpt exists, the app says so.
- **Mother tongue as a bridge.** Learners can think and ask in their own language. Replies are in simple English, because model-written Malayalam had spelling errors in testing.
- **Honest feedback.** No generic praise. Praise only names a specific improvement.
- **Visible reasoning.** A collapsible "How it decided" panel shows each step, agent and tool used.

## Meta AI tools used

| Tool | Where |
|---|---|
| **Muse Spark** (Meta Model API) | Diagnoser, Write feedback card, Learn and Practice Assessor, practice judging, Teacher Studio generation, and handwritten-paper scanning (vision) |
| **Muse Voice Transcribe** | Voice input (realtime WebSocket), with the browser's built-in speech recognition as fallback, including for Malayalam |
| **Muse Code** | Built the app, with a separate read-only Muse Code session acting as reviewer (builder and verifier pattern) |

Twin replies, Learn cards and practice banks use templates and real book excerpts on purpose, so that nothing a learner reads as teaching content is invented by a model.

## Safety and quality

- A **Verifier** checks every model output before the learner sees it: quotes must exist in the learner's text, no complete answers, at most one sentence rewritten, right level, simple English, no generic praise, model examples on a different topic from the task.
- Every model call has a **timeout, at most 2 retries, and a safe fallback**, so the app never hangs.
- **License gate:** books with No-Derivatives (ND) licenses are excluded from the knowledge base.
- **Privacy:** minimal profile data, no photos stored after scanning, and a working **Delete my data** button.
- **[NUMBER] automated tests** (pytest).

## Evaluation

[ADD AFTER TESTING]

- Diagnoser vs teacher: [N] paragraphs scored by a teacher on the 7-skill rubric; [X]% of Diagnoser scores were within one level of the teacher's.
- Verifier: blocked [N] of [M] generated outputs; the most common reason was [REASON].
- Student trial: [N] students. Example before and after: [ADD, with consent, names removed].

## Tech stack

React (Vite) frontend · FastAPI backend · ChromaDB knowledge base with local embeddings · SQLite learner store · Meta Model API

## Run it locally

Requirements: Python 3.12+, Node.js LTS, a Meta Model API key.

```bash
git clone https://github.com/bijumastc/VibeEduTwin.git
cd VibeEduTwin

# Backend
python -m venv .venv
.venv\Scripts\activate          # Windows (macOS/Linux: source .venv/bin/activate)
pip install -r requirements.txt
```

Create a `.env` file in the project folder:

```
MODEL_API_KEY=your-meta-model-api-key
DEMO_MODE=false
```

Download the open-licensed books listed in `manifest.json` into `data/knowledge/` (see the note in that folder), then:

```bash
python scripts/ingest_knowledge.py --reset
python learner_store.py
uvicorn main:app --reload
```

Frontend, in a second terminal:

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:5173

**Demo mode:** set `DEMO_MODE=true` for a scripted, reliable demo path. Run `python scripts/reset_demo.py` and restart the backend before each run.

## Honest limits

- Some PDF text extraction still contains damaged words.
- Retrieval uses semantic search with metadata filters and keyword scoring, not full hybrid search.
- Malayalam is accepted as input but not generated in replies.
- Malayalam voice uses the browser's speech recognition, because Malayalam is not on Muse Voice Transcribe's documented language list.
- When Muse Spark is slow, some features fall back to simpler template feedback.

## Roadmap

- A full 90-hour, 5-credit semester course (18 weeks, 5 modules, weekly checks and proficiency tests)
- Hybrid keyword and vector retrieval with reranking
- Deterministic cleanup of PDF text artifacts
- A teacher-reviewed bank of curated excerpts
- Llama Guard safety screening
- Class views for teachers
- WhatsApp delivery and a public demo link

## Licenses

Code: [ADD YOUR CHOICE, e.g. MIT]. The knowledge base uses openly licensed textbooks; each lesson credits its source behind the ⓘ icon. Some sources are CC BY-NC-SA, so lessons adapted from them are shared under the same terms and for non-commercial use. Books are not included in this repository.
