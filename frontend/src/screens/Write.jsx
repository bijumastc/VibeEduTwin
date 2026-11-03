import { useState } from 'react';
import { api } from '../api.js';
import CompactLesson from '../components/CompactLesson.jsx';
import HowItDecided from '../components/HowItDecided.jsx';
import SkillBars from '../components/SkillBars.jsx';
import TwinPanel from '../components/TwinPanel.jsx';
import VoiceButton from '../components/VoiceButton.jsx';

// Write: big text box, submit, then 7-skill diagnosis + twin note + Learn card.
export default function Write({ go }) {
  const [text, setText] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [result, setResult] = useState(null);
  const [twinOpen, setTwinOpen] = useState(false);

  const submit = async () => {
    if (!text.trim() || busy) return;
    setBusy(true);
    setError('');
    try {
      const draft = await api.saveDraft(text.trim());
      const diagnosis = await api.diagnose(draft.draft_id);
      setResult(diagnosis);
    } catch (err) {
      setError(err.message);
    }
    setBusy(false);
  };

  const reset = () => {
    setText('');
    setResult(null);
    setError('');
  };

  return (
    <div>
      <h2>Write</h2>
      {error && <div className="error">{error}</div>}

      {!result && (
        <>
          <textarea
            placeholder="Type or paste your paragraph here…"
            value={text}
            onChange={(e) => setText(e.target.value)}
          />
          <button className="btn" onClick={submit} disabled={busy || !text.trim()}>
            {busy ? 'Checking…' : 'Submit'}
          </button>{' '}
          <VoiceButton
            disabled={busy}
            onTranscript={(spoken) => setText((prev) => (prev ? `${prev} ${spoken}` : spoken))}
          />
        </>
      )}

      {result && (
        <>
          <div className="card tint">
            <div className="card-title">Weakest skill: {result.weakest}</div>
            <p className="muted">Level {result.level}</p>
          </div>
          <div className="card">
            <SkillBars scores={result.scores} weakest={result.weakest} levels={result.level_changes} />
          </div>
          <div className="card accent-soft">
            <div className="card-title">Your twin says</div>
            <p>{result.twin_note}</p>
          </div>
          {result.comparison && (
            <div className="card">
              <div className="card-title">Your twin compares</div>
              <p>{result.comparison}</p>
            </div>
          )}
          {result.learn && (
            <CompactLesson
              title={`Learn: ${result.learn.skill}`}
              idea={result.learn.idea}
              example={result.learn.example}
              basedOn={result.learn.based_on}
              onPractise={() => go('practice')}
            />
          )}
          {result.study_material && result.study_material.length > 0 && (
            <div className="card">
              <div className="card-title">From the guides</div>
              {result.study_material.map((m, i) => (
                <p key={i} className="muted"><em>{m.source}</em> ({m.license || 'license unknown'}): {m.text}</p>
              ))}
            </div>
          )}
          <button className="btn secondary" onClick={reset}>Write another</button>
          <HowItDecided refreshKey={result} />
        </>
      )}

      <button className="twin-fab" onClick={() => setTwinOpen(true)}>Ask my Twin</button>
      {twinOpen && <TwinPanel screen="write" onClose={() => setTwinOpen(false)} />}
    </div>
  );
}
