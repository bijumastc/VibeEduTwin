import { useEffect, useState } from 'react';
import { api } from '../api.js';
import BasedOn from './BasedOn.jsx';
import FeedbackCard from './FeedbackCard.jsx';
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
  const [lastTry, setLastTry] = useState('');
  const [polish, setPolish] = useState(null);
  const [polishBusy, setPolishBusy] = useState(false);
  const [checkRes, setCheckRes] = useState(null);
  const [checkBusy, setCheckBusy] = useState(false);

  useEffect(() => {
    api.scaffoldStart(discipline, moduleId)
      .then((res) => setView(res))
      .catch((err) => setError(err.message));
  }, [discipline, moduleId]);

  useEffect(() => {
    setCheckRes(null);
  }, [discipline, moduleId]);

  const push = (entry) => setFeed((f) => [...f, entry]);

  const apply = (res) => {
    setView(res);
    if (res.assessment) {
      const a = res.assessment;
      push({
        kind: 'assess',
        card: {
          strength: a.strength ? { quote: a.quote, line: a.strength } : null,
          problems: a.problem
            ? [{ quote: a.quote, wrong: a.problem, why: '', fix: a.next_action || '' }]
            : [],
          model: null,
          your_turn: a.status === 'ok' ? a.your_turn : '',
          motivation: a.motivation,
        },
        modelSentence: a.status === 'ok' ? a.model : null,
        fallback: a.status === 'ok' ? '' : a.feedback,
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
    if (text.trim()) setLastTry(text.trim());
    setCheckRes(null);
    call(() => api.scaffoldHelp(view.attempt_id, text), text);
  };
  const check = async (rating) => {
    const text = (draft.trim() || lastTry).trim();
    if (!text || checkBusy || busy) return;
    setCheckBusy(true);
    setError('');
    try {
      const res = await api.scaffoldCheck(view.attempt_id, text, rating);
      setCheckRes({ ...res, checked: text });
    } catch (err) {
      setError(err.message);
    }
    setCheckBusy(false);
  };
  const show = () => call(() => api.scaffoldShow(view.attempt_id));
  const steps = () => call(() => api.scaffoldSteps(view.attempt_id));
  const rewrite = () => {
    const text = draft;
    if (text.trim()) setLastTry(text.trim());
    call(() => api.scaffoldRewrite(view.attempt_id, text), text);
    setDraft('');
  };
  const compare = async () => {
    if (polishBusy || !lastTry) return;
    setPolishBusy(true);
    try {
      const res = await api.polishText(lastTry);
      setPolish(res.ok ? res : { error: res.message });
    } catch (err) {
      setPolish({ error: err.message });
    }
    setPolishBusy(false);
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
      {view.mode === 'guided' && (
        <div className="card tint">
          <div className="card-title">Guided mode</div>
          <p className="muted">Read the idea and the example first, then try the task.</p>
        </div>
      )}
      {view.mode === 'guided' && view.idea && (
        <div className="card">
          <div className="card-title">The idea</div>
          <p>{view.idea}</p>
        </div>
      )}
      {view.mode === 'guided' && view.worked_example && (
        <div className="card">
          <div className="card-title">Worked example — a different topic</div>
          <p>{view.worked_example.text}</p>
          <p className="muted">{view.worked_example.self_check}</p>
        </div>
      )}
      <div className="card tint">
        <div className="card-title">Your task</div>
        <p>{view.task}</p>
        {view.mode && (
          <p className="muted">
            {view.mode === 'guided'
              ? `Guided · ${view.activities_done} of ${view.activities_needed} activities`
              : 'Challenge mode'}
          </p>
        )}
      </div>

      {feed.map((e, i) => (
        e.kind === 'me'
          ? <div className="card" key={i}><p>{e.text}</p></div>
          : e.kind === 'assess'
            ? (
              <div key={i}>
                <FeedbackCard feedback={e.card} modelSentence={e.modelSentence} fallback={e.fallback} title="Twin's feedback" />
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
          {moduleId === 'topic-sentences' && (
            <>
              <div style={{ height: 10 }} />
              <div className="card">
                <div className="card-title">Check</div>
                {!checkRes && (
                  <>
                    <p className="muted">How do you rate your topic sentence?</p>
                    {!(draft.trim() || lastTry) && (
                      <p className="muted">Write your sentence above first.</p>
                    )}
                    <button
                      className="btn secondary"
                      onClick={() => check('good')}
                      disabled={busy || checkBusy || !(draft.trim() || lastTry)}
                    >
                      My sentence is good
                    </button>{' '}
                    <button
                      className="btn secondary"
                      onClick={() => check('bad')}
                      disabled={busy || checkBusy || !(draft.trim() || lastTry)}
                    >
                      It needs work
                    </button>
                    {checkBusy && <p className="loading">Your twin is checking your sentence...</p>}
                  </>
                )}
                {checkRes && (
                  <>
                    <p className="muted"><em>Checked: “{checkRes.checked}”</em></p>
                    <p><strong>{checkRes.verdict === 'good' ? 'Verdict: good.' : 'Verdict: needs work.'}</strong></p>
                    <p>{checkRes.message}</p>
                    {checkRes.fails.length > 0 && (
                      <>
                        <div className="card-title">Where it fails</div>
                        <ul>
                          {checkRes.fails.map((f, i) => <li key={i}>{f}</li>)}
                        </ul>
                      </>
                    )}
                    <div className="card-title">How to improve</div>
                    <ul>
                      {checkRes.fixes.map((f, i) => <li key={i}>{f}</li>)}
                    </ul>
                    <div className="card-title">Improved version</div>
                    <p className="muted">{checkRes.improved_label}</p>
                    <p>{checkRes.improved}</p>
                    <p className="muted">The rule: {checkRes.rule}</p>
                    <button className="btn secondary" onClick={() => setCheckRes(null)} disabled={busy || checkBusy}>
                      Check again
                    </button>
                  </>
                )}
              </div>
            </>
          )}
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

      {done && lastTry && !polish && (
        <>
          <div style={{ height: 10 }} />
          <button className="btn secondary" onClick={compare} disabled={polishBusy}>
            {polishBusy ? 'Polishing…' : 'Compare with a polished version'}
          </button>
        </>
      )}
      {polish && polish.polished && (
        <div className="card accent-soft">
          <div className="card-title">Polished version</div>
          <p className="muted">Yours: {polish.original}</p>
          <p>{polish.polished}</p>
        </div>
      )}
      {polish && polish.error && (
        <div className="card warn">
          <p className="muted">{polish.error}</p>
        </div>
      )}

      <div style={{ height: 10 }} />
      <button className="btn secondary" onClick={onBack}>Back to modules</button>
    </div>
  );
}
