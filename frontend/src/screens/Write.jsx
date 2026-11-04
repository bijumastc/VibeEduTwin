import { useRef, useState } from 'react';
import { api, levelName } from '../api.js';
import CompactLesson from '../components/CompactLesson.jsx';
import FeedbackCard from '../components/FeedbackCard.jsx';
import HowItDecided from '../components/HowItDecided.jsx';
import HowScored from '../components/HowScored.jsx';
import SkillBars from '../components/SkillBars.jsx';
import TwinPanel from '../components/TwinPanel.jsx';
import VoiceButton from '../components/VoiceButton.jsx';

// Shrink a photo under 1 MB in the browser (the photo itself is never stored).
const shrinkImage = (file) => new Promise((resolve, reject) => {
  const url = URL.createObjectURL(file);
  const img = new Image();
  img.onload = () => {
    URL.revokeObjectURL(url);
    const scale = Math.min(1, 1600 / Math.max(img.width, img.height));
    const canvas = document.createElement('canvas');
    canvas.width = Math.round(img.width * scale);
    canvas.height = Math.round(img.height * scale);
    canvas.getContext('2d').drawImage(img, 0, 0, canvas.width, canvas.height);
    let quality = 0.9;
    const attempt = () => {
      canvas.toBlob((blob) => {
        if (!blob) {
          reject(new Error('unreadable'));
          return;
        }
        if (blob.size <= 1000000 || quality <= 0.4) {
          const reader = new FileReader();
          reader.onload = () => resolve(reader.result);
          reader.onerror = () => reject(new Error('unreadable'));
          reader.readAsDataURL(blob);
        } else {
          quality -= 0.15;
          attempt();
        }
      }, 'image/jpeg', quality);
    };
    attempt();
  };
  img.onerror = () => {
    URL.revokeObjectURL(url);
    reject(new Error('unreadable'));
  };
  img.src = url;
});

const highlightUnclear = (value) => value.split('[unclear]').map((part, i, arr) => (
  <span key={i}>
    {part}
    {i < arr.length - 1 && <mark>[unclear]</mark>}
  </span>
));

// Write: big text box, submit, then 7-skill diagnosis + twin note + Learn card.
export default function Write({ go }) {
  const [text, setText] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [result, setResult] = useState(null);
  const [twinOpen, setTwinOpen] = useState(false);
  const [scanBusy, setScanBusy] = useState(false);
  const [scanned, setScanned] = useState(false);
  const [draftId, setDraftId] = useState(null);
  const [polish, setPolish] = useState(null);
  const fileRef = useRef(null);

  const submit = async () => {
    if (!text.trim() || busy) return;
    setBusy(true);
    setError('');
    setPolish(null);
    try {
      const draft = await api.saveDraft(text.trim(), scanned ? 'scan' : 'typed');
      setDraftId(draft.draft_id);
      const diagnosis = await api.diagnose(draft.draft_id);
      setResult(diagnosis);
    } catch (err) {
      setError(err.message);
    }
    setBusy(false);
  };

  // Polished compare: unlocked once their own rewrite has been diagnosed.
  const fetchPolish = async () => {
    if (!draftId || (polish && polish.loading)) return;
    setPolish({ loading: true });
    try {
      const res = await api.polish(draftId);
      if (res.ok) {
        setPolish({ text: res.polished, original: res.original });
      } else {
        setPolish({ error: res.message });
      }
    } catch (err) {
      setPolish({ error: err.message });
    }
  };

  const polishUnlocked = !!result && !!result.comparison
    && result.comparison !== 'This is your starting point.';

  const scan = async (file) => {
    if (!file || scanBusy) return;
    setScanBusy(true);
    setError('');
    try {
      const dataUrl = await shrinkImage(file);
      const res = await api.scanPaper(dataUrl);
      if (!res.ok) {
        setError(res.message);
      } else {
        setText(res.text);
        setScanned(true);
      }
    } catch {
      setError('Please type your paragraph.');
    }
    setScanBusy(false);
    if (fileRef.current) fileRef.current.value = '';
  };

  const reset = () => {
    setText('');
    setResult(null);
    setError('');
    setScanned(false);
    setDraftId(null);
    setPolish(null);
  };

  // Rewrite flow: back to the text box with the paragraph kept, so the
  // next submit compares the new version with this one.
  const rewrite = () => {
    setResult(null);
    setError('');
    setScanned(false);
    setPolish(null);
  };

  const skillDetails = {};
  (result?.skills_details || []).forEach((entry) => {
    skillDetails[entry.skill] = entry;
  });

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
          {scanned && (
            <div className="card tint">
              <p className="muted">
                Check that this matches your paper. Fix any word the app read wrongly.
              </p>
              <p>{highlightUnclear(text)}</p>
            </div>
          )}
          <button className="btn" onClick={submit} disabled={busy || !text.trim()}>
            {scanned ? 'This is what I wrote' : (busy ? 'Checking…' : 'Submit')}
          </button>{' '}
          {busy && <p className="loading">Your twin is reading your writing...</p>}
          <VoiceButton
            disabled={busy}
            onTranscript={(spoken) => setText((prev) => (prev ? `${prev} ${spoken}` : spoken))}
          />{' '}
          <button
            className="btn secondary"
            onClick={() => fileRef.current && fileRef.current.click()}
            disabled={busy || scanBusy}
          >
            {scanBusy ? 'Reading…' : 'Scan my paper'}
          </button>
          {scanBusy && <p className="loading">Reading your paper...</p>}
          <input
            ref={fileRef}
            type="file"
            accept="image/jpeg,image/png"
            style={{ display: 'none' }}
            onChange={(e) => scan(e.target.files[0])}
          />
        </>
      )}

      {result && (
        <>
          <div className="card tint">
            <div className="card-title">Weakest skill: {result.weakest}</div>
            <p className="muted">Level {result.level} of 5 · {levelName(result.level)}</p>
            {result.notice && <p className="muted">{result.notice}</p>}
          </div>
          <div className="card">
            <SkillBars scores={result.scores} weakest={result.weakest} levels={result.level_changes} details={skillDetails} />
          </div>
          <FeedbackCard
            feedback={result.feedback}
            onRewrite={rewrite}
            polish={{ unlocked: polishUnlocked, ...(polish || {}) }}
            onPolish={fetchPolish}
          />
          <HowScored />
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
              connect={result.learn.connect}
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
