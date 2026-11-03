import { useEffect, useState } from 'react';
import { api, LeveledUp } from '../api.js';
import TwinPanel from '../components/TwinPanel.jsx';

// Practice: one item at a time, tap to answer, score at the end.
export default function Practice() {
  const [set, setSet] = useState(null);
  const [index, setIndex] = useState(0);
  const [answers, setAnswers] = useState({});
  const [picked, setPicked] = useState('');
  const [result, setResult] = useState(null);
  const [error, setError] = useState('');
  const [twinOpen, setTwinOpen] = useState(false);

  const load = () => {
    setError('');
    setResult(null);
    setSet(null);
    setAnswers({});
    setIndex(0);
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

  const choose = (option) => {
    if (picked) return; // ignore double taps while advancing
    const item = set.items[index];
    // MCQ options look like "B) ..." (answer is the letter);
    // order options are full sequences like "2,1,3" (answer is the whole text).
    const letter = option.match(/^\s*([A-Za-z])\)/);
    const value = letter ? letter[1] : option.trim();
    const next = { ...answers, [item.id]: value };
    setAnswers(next);
    setPicked(option);
    setTimeout(() => {
      setPicked('');
      if (index + 1 < set.items.length) setIndex(index + 1);
      else finish(next);
    }, 350);
  };

  if (error) return <div><h2>Practice</h2><div className="error">{error}</div></div>;
  if (!set) return <div><h2>Practice</h2><p className="loading">Loading…</p></div>;

  if (result) {
    return (
      <div>
        <h2>Result</h2>
        {result.leveled_up && <div className="levelup">Level up in {result.skill}!</div>}
        <div className="card tint">
          <div className="score-big">{result.correct}/{result.total}</div>
          <p className="muted">{result.accuracy}% correct · {result.skill}</p>
        </div>
        {result.details.filter((d) => !d.correct).map((d) => (
          <div className="card warn" key={d.id}>
            <p>{d.explanation}</p>
          </div>
        ))}
        <button className="btn" onClick={load}>Practise again</button>
        <button className="twin-fab" onClick={() => setTwinOpen(true)}>Ask my Twin</button>
        {twinOpen && <TwinPanel screen="practice" onClose={() => setTwinOpen(false)} />}
      </div>
    );
  }

  const item = set.items[index];
  return (
    <div>
      <h2>Practice: {set.skill}</h2>
      <div className="progress">Question {index + 1} of {set.items.length} · Level {set.level}</div>
      <div className="card">
        <p>{item.prompt}</p>
      </div>
      {item.options.map((option) => (
        <button
          key={option}
          className={`btn secondary option-btn${picked === option ? ' picked' : ''}`}
          onClick={() => choose(option)}
        >
          {option}
        </button>
      ))}
      <button className="twin-fab" onClick={() => setTwinOpen(true)}>Ask my Twin</button>
      {twinOpen && <TwinPanel screen="practice" onClose={() => setTwinOpen(false)} />}
    </div>
  );
}
