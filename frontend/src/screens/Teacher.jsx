import { useState } from 'react';
import { api } from '../api.js';

// Teacher: one text box. Generate items built only from library excerpts,
// see the Verifier result, then Publish or Regenerate. No editor.
export default function Teacher({ go }) {
  const [request, setRequest] = useState('');
  const [note, setNote] = useState('');
  const [result, setResult] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [published, setPublished] = useState(null);

  const generate = async (noteText) => {
    if (!request.trim() || busy) return;
    setBusy(true);
    setError('');
    setPublished(null);
    try {
      const res = await api.teacherGenerate(request.trim(), noteText || '');
      setResult(res);
    } catch (err) {
      setError(err.message);
    }
    setBusy(false);
  };

  const publish = async () => {
    if (!result || !result.passed || busy) return;
    setBusy(true);
    setError('');
    try {
      const res = await api.teacherPublish({
        request: request.trim(),
        skill: result.skill,
        level: result.level,
        discipline: result.discipline,
        items: result.items,
      });
      setPublished(res);
    } catch (err) {
      setError(err.message);
    }
    setBusy(false);
  };

  const reset = () => {
    setRequest('');
    setNote('');
    setResult(null);
    setPublished(null);
    setError('');
  };

  return (
    <div>
      <h2>Teacher tools</h2>
      {error && <div className="error">{error}</div>}

      {published && (
        <div className="card accent-soft">
          <div className="card-title">Published</div>
          <p>Learners will see it in Practice.</p>
          <button className="btn secondary" onClick={reset}>Make another</button>
        </div>
      )}

      {!result && (
        <>
          <textarea
            placeholder='e.g. Make 5 practice items on topic sentences for first-year Science students at Level 2'
            value={request}
            onChange={(e) => setRequest(e.target.value)}
          />
          <button className="btn" onClick={() => generate('')} disabled={busy || !request.trim()}>
            {busy ? 'Generating…' : 'Generate items'}
          </button>
        </>
      )}

      {result && !published && (
        <>
          <div className={`card ${result.passed ? 'accent-soft' : 'warn'}`}>
            <div className="card-title">
              Verifier: {result.passed ? 'Passed' : 'Failed'}
            </div>
            {!result.passed && result.errors.map((e, i) => (
              <p key={i} className="muted">{e}</p>
            ))}
            {result.passed && (
              <p className="muted">
                {result.items.length} items · {result.skill} · Level {result.level}
                {result.discipline ? ` · ${result.discipline}` : ''}
              </p>
            )}
          </div>

          {result.items.map((item, i) => (
            <div className="card" key={item.id || i}>
              <div className="card-title">Item {i + 1} ({item.type})</div>
              <p>{item.prompt}</p>
              {item.options.map((option) => (
                <p key={option} className="muted">{option}</p>
              ))}
              <p><strong>Answer:</strong> {item.answer}</p>
              <p className="muted">{item.explanation}</p>
              {(item.source || item.chapter) && (
                <p className="muted">
                  <em>{[item.source, item.chapter].filter(Boolean).join(' · ')}</em>
                </p>
              )}
            </div>
          ))}

          <input
            type="text"
            placeholder="One-line note for regenerate (optional)"
            value={note}
            onChange={(e) => setNote(e.target.value)}
          />
          <div style={{ height: 10 }} />
          <button className="btn" onClick={publish} disabled={busy || !result.passed}>
            Publish
          </button>
          <div style={{ height: 10 }} />
          <button className="btn secondary" onClick={() => generate(note)} disabled={busy}>
            Regenerate
          </button>
        </>
      )}

      <div style={{ height: 10 }} />
      <button className="btn secondary" onClick={() => go('home')}>Back to Home</button>
    </div>
  );
}
