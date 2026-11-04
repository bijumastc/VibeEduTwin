import { useEffect, useState } from 'react';
import { api, LeveledUp } from '../api.js';
import HowItDecided from '../components/HowItDecided.jsx';
import ScanButton from '../components/ScanButton.jsx';
import SkillBars from '../components/SkillBars.jsx';
import TwinPanel from '../components/TwinPanel.jsx';
import VoiceButton from '../components/VoiceButton.jsx';

// Practice: one item at a time, tap to answer, score at the end.
// Each answer carries the twin's assessment; repeated wrongs offer Learn.
// Repair/produce/apply items are free text; recognise items are choices.
const KIND_LABELS = {
  recognise: 'Choose the best',
  repair: 'Repair this',
  produce: 'Write your own',
  apply: 'Apply it',
};

// Level-up screen: the move (Skill Level x → y) with the growth chart.
function LevelUpCard({ ups, go }) {
  const [growth, setGrowth] = useState(null);

  useEffect(() => {
    api.growth().then(setGrowth).catch(() => setGrowth({ scores: {} }));
  }, []);

  const scores = (growth && growth.scores) || {};
  const names = Object.keys(scores);
  const weakest = names.length > 0
    ? names.reduce((a, b) => (scores[a] <= scores[b] ? a : b))
    : null;

  return (
    <div className="card tint">
      {ups.map((up) => (
        <div className="card-title" key={up.skill}>
          {up.skill} Level {up.from} → {up.to}
        </div>
      ))}
      {growth && names.length > 0 && (
        <SkillBars scores={scores} weakest={weakest} levels={growth.levels} details={growth.details} />
      )}
      <button className="btn secondary" onClick={() => go('growth')}>See my growth</button>
    </div>
  );
}

export default function Practice({ go }) {
  const [set, setSet] = useState(null);
  const [index, setIndex] = useState(0);
  const [answers, setAnswers] = useState({});
  const [picked, setPicked] = useState('');
  const [draft, setDraft] = useState('');
  const [result, setResult] = useState(null);
  const [error, setError] = useState('');
  const [twinOpen, setTwinOpen] = useState(false);

  const load = () => {
    setError('');
    setResult(null);
    setSet(null);
    setAnswers({});
    setIndex(0);
    setDraft('');
    api.getPractice().then(setSet).catch((err) => setError(err.message));
  };

  useEffect(load, []);

  const finish = async (allAnswers) => {
    try {
      const res = await api.submitAnswers(set.set_id, allAnswers);
      if (res.leveled_up) LeveledUp.set();
      setResult(res);
    } catch (err) {
      setError(err.message);
    }
  };

  const advance = (next) => {
    if (index + 1 < set.items.length) setIndex(index + 1);
    else finish(next);
  };

  const choose = (option) => {
    if (picked) return; // ignore double taps while advancing
    const item = set.items[index];
    // MCQ options look like "B) ..." or "(b) ..." (answer is the letter);
    // order options are full sequences like "2,1,3" (answer is the whole text).
    const letter = option.match(/^\s*\(?([A-Za-z])\)/);
    const value = letter ? letter[1] : option.trim();
    const next = { ...answers, [item.id]: value };
    setAnswers(next);
    setPicked(option);
    setTimeout(() => {
      setPicked('');
      advance(next);
    }, 350);
  };

  const saveWrite = () => {
    const item = set.items[index];
    const next = { ...answers, [item.id]: draft.trim() };
    setAnswers(next);
    setDraft('');
    advance(next);
  };

  if (error) return <div><h2>Practice</h2><div className="error">{error}</div></div>;
  if (!set) return <div><h2>Practice</h2><p className="loading">Loading…</p></div>;

  if (result) {
    return (
      <div>
        <h2>Result</h2>
        {result.leveled_up && <div className="levelup">Level up in {result.skill}!</div>}
        {result.level_ups && result.level_ups.length > 0 && (
          <LevelUpCard ups={result.level_ups} go={go} />
        )}
        <div className="card tint">
          <div className="score-big">{result.correct} of {result.total} right</div>
          <p className="muted">{result.skill} · Level {result.level} of 5</p>
        </div>
        {result.details.filter((d) => !d.correct).map((d) => (
          <div className="card warn" key={d.id}>
            <p>{d.explanation}</p>
            {d.assessment && <p className="muted">{d.assessment.feedback}</p>}
          </div>
        ))}
        {result.details.some((d) => d.assessment && d.assessment.next_step === 'study') && (
          <div className="card">
            <p>Some answers need work. Study the idea, then try again.</p>
            <button className="btn secondary" onClick={() => go('learn')}>Study this in Learn</button>
          </div>
        )}
        <button className="btn" onClick={load}>Practise again</button>
        <HowItDecided refreshKey={result} />
        <button className="twin-fab" onClick={() => setTwinOpen(true)}>Ask my Twin</button>
        {twinOpen && <TwinPanel screen="practice" onClose={() => setTwinOpen(false)} />}
      </div>
    );
  }

  const item = set.items[index];
  return (
    <div>
      <h2>Practice: {set.skill}</h2>
      <div className="progress">Question {index + 1} of {set.items.length} · Level {set.level}{set.discipline ? ` · ${set.discipline}` : ''}{set.published ? ' · Teacher set' : ''}{set.review ? ' · Review set' : ''}</div>
      <div className="card">
        {item.kind && <p className="muted">{KIND_LABELS[item.kind] || item.kind}</p>}
        <p>{item.prompt}</p>
      </div>
      {item.type === 'write' ? (
        <>
          <textarea
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            placeholder="Write here…"
          />
          <VoiceButton
            onTranscript={(spoken) => setDraft((prev) => (prev ? `${prev} ${spoken}` : spoken))}
          />{' '}
          <ScanButton
            onTranscript={(scanned) => setDraft((prev) => (prev ? `${prev} ${scanned}` : scanned))}
            onError={setError}
          />
          <div style={{ height: 10 }} />
          <button className="btn" onClick={saveWrite}>Save & continue</button>
        </>
      ) : (
        item.options.map((option) => (
          <button
            key={option}
            className={`btn secondary option-btn${picked === option ? ' picked' : ''}`}
            onClick={() => choose(option)}
          >
            {option}
          </button>
        ))
      )}
      <button className="twin-fab" onClick={() => setTwinOpen(true)}>Ask my Twin</button>
      {twinOpen && <TwinPanel screen="practice" onClose={() => setTwinOpen(false)} />}
    </div>
  );
}
