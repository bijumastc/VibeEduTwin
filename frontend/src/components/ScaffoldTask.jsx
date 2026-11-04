import { useEffect, useState } from 'react';
import { api } from '../api.js';
import BasedOn from './BasedOn.jsx';
import ScanButton from './ScanButton.jsx';
import VoiceButton from './VoiceButton.jsx';

// ScaffoldTask: the productive-struggle ladder for one module task.
// (a) try with no help -> (b) guiding question -> (c) hint ->
// (d) book excerpt -> (e) rewrite. "Show me now" jumps to (d);
// "Just show me the steps" gives the worked answer for impatient learners.
export default function ScaffoldTask({ discipline, moduleId, moduleTitle, onBack }) {
  const [view, setView] = useState(null);
  const [feed, setFeed] = useState([]);
  const [draft, setDraft] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    api.scaffoldStart(discipline, moduleId)
      .then((res) => setView(res))
      .catch((err) => setError(err.message));
  }, [discipline, moduleId]);

  const push = (entry) => setFeed((f) => [...f, entry]);

  const apply = (res) => {
    setView(res);
    if (res.assessment) {
      push({
        kind: 'assess',
        label: "Twin's feedback",
        a: res.assessment,
      });
    }
    if (res.question) push({ kind: 'twin', label: 'Guiding question', text: res.question });
    if (res.hint) push({ kind: 'twin', label: 'Hint', text: res.hint });
    if (res.excerpt) {
      push({
        kind: 'twin',
        label: res.excerpt.label || 'From the books',
        text: res.excerpt.text,
        books: res.excerpt.book ? [res.excerpt.book] : [],
        cite: res.try ? `Your sentence: “${res.try}”` : null,
      });
    }
    if (res.comparison) push({ kind: 'twin', label: 'Compare', text: res.comparison });
    if (res.rule && res.rule.source) {
      push({
        kind: 'twin',
        label: 'The rule from the books',
        text: res.rule.text,
        books: res.rule.book ? [res.rule.book] : [],
      });
    }
    if (res.steps) push({ kind: 'steps', label: 'Follow these steps', steps: res.steps });
    if (res.model) push({ kind: 'model', label: 'Study this model — a different point', text: res.model });
    if (res.self_explanation) push({ kind: 'twin', label: 'Think', text: res.self_explanation });
    if (res.prompt) push({ kind: 'twin', label: 'Rewrite', text: res.prompt });
    if (res.message) push({ kind: 'twin', label: 'Done', text: res.message });
  };

  const call = async (fn, userText) => {
    if (busy) return;
    setBusy(true);
    setError('');
    if (userText && userText.trim()) push({ kind: 'me', text: userText.trim() });
    try {
      apply(await fn());
    } catch (err) {
      setError(err.message);
    }
    setBusy(false);
  };

  const help = () => {
    const text = draft;
    setDraft('');
    call(() => api.scaffoldHelp(view.attempt_id, text), text);
  };
  const show = () => call(() => api.scaffoldShow(view.attempt_id));
  const steps = () => call(() => api.scaffoldSteps(view.attempt_id));
  const rewrite = () => {
    const text = draft;
    call(() => api.scaffoldRewrite(view.attempt_id, text), text);
    setDraft('');
  };

  if (error) {
    return (
      <div>
        <h2>{moduleTitle}</h2>
        <div className="error">{error}</div>
        <button className="btn secondary" onClick={onBack}>Back to modules</button>
      </div>
    );
  }
  if (!view) return <div><h2>{moduleTitle}</h2><p className="loading">Loading…</p></div>;

  const step = view.step;
  const done = step === 'done';

  return (
    <div>
      <h2>{moduleTitle}</h2>
      {busy && <p className="loading">Your twin is reading your writing...</p>}
      <div className="card tint">
        <div className="card-title">Your task</div>
        <p>{view.task}</p>
      </div>

      {feed.map((e, i) => (
        e.kind === 'me'
          ? <div className="card" key={i}><p>{e.text}</p></div>
          : e.kind === 'assess'
            ? (
              <div className="card" key={i}>
                <div className="card-title">{e.label}</div>
                {e.a.strength && <p>{e.a.strength}</p>}
                {e.a.problem && <p>{e.a.problem}</p>}
                {!e.a.strength && !e.a.problem && <p>{e.a.feedback}</p>}
                {e.a.status === 'ok' && e.a.model && (
                  <p><strong>✏️ Let me show you one:</strong> {e.a.model}</p>
                )}
                {e.a.status === 'ok' && e.a.your_turn && <p>{e.a.your_turn}</p>}
                <p className="muted"><em>Score {e.a.score} of 2</em></p>
              </div>
            )
          : e.kind === 'steps'
              ? (
                <div className="card" key={i}>
                  <div className="card-title">{e.label}</div>
                  <ol>
                    {e.steps.map((s, j) => <li key={j}>{s}</li>)}
                  </ol>
                </div>
              )
              : e.kind === 'model'
                ? (
                  <div className="card tint" key={i}>
                    <div className="card-title">{e.label}</div>
                    <p>{e.text}</p>
                  </div>
                )
                : (
              <div className="card" key={i}>
                <div className="card-title">{e.label}</div>
                <p>{e.text}</p>
                {e.cite && <p className="muted"><em>{e.cite}</em></p>}
                {e.books && e.books.length > 0 && <BasedOn books={e.books} />}
              </div>
            )
      ))}

      {!done && step !== 'rewrite' && step !== 'excerpt' && step !== 'steps' && (
        <>
          <textarea
            placeholder="Try the task first, in your own words…"
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
          />
          <VoiceButton
            disabled={busy}
            onTranscript={(spoken) => setDraft((prev) => (prev ? `${prev} ${spoken}` : spoken))}
          />{' '}
          <ScanButton
            disabled={busy}
            onTranscript={(scanned) => setDraft((prev) => (prev ? `${prev} ${scanned}` : scanned))}
            onError={setError}
          />
          <div style={{ height: 10 }} />
          <button className="btn" onClick={help} disabled={busy}>
            {step === 'try' ? 'I tried — help me' : 'Still stuck — help me'}
          </button>
          <div style={{ height: 10 }} />
          <button className="btn secondary" onClick={show} disabled={busy}>Show me now</button>
          <div style={{ height: 10 }} />
          <button className="btn secondary" onClick={steps} disabled={busy}>Just show me the steps</button>
        </>
      )}

      {!done && step === 'excerpt' && (
        <button className="btn" onClick={help} disabled={busy}>Rewrite now</button>
      )}

      {!done && step === 'steps' && (
        <button className="btn" onClick={help} disabled={busy}>Write my version</button>
      )}

      {!done && step === 'rewrite' && (
        <>
          <textarea
            placeholder="Rewrite using the pattern…"
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
          />
          <VoiceButton
            disabled={busy}
            onTranscript={(spoken) => setDraft((prev) => (prev ? `${prev} ${spoken}` : spoken))}
          />{' '}
          <ScanButton
            disabled={busy}
            onTranscript={(scanned) => setDraft((prev) => (prev ? `${prev} ${scanned}` : scanned))}
            onError={setError}
          />
          <div style={{ height: 10 }} />
          <button className="btn" onClick={rewrite} disabled={busy || !draft.trim()}>
            Submit rewrite
          </button>
        </>
      )}

      <div style={{ height: 10 }} />
      <button className="btn secondary" onClick={onBack}>Back to modules</button>
    </div>
  );
}
