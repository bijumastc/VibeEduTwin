import { useEffect, useState } from 'react';
import { api } from '../api.js';
import LearnCard from '../components/LearnCard.jsx';

// Learn: the 7 skills with current levels; tapping one shows its Learn card.
const SKILLS = [
  'Grammar',
  'Vocabulary',
  'Sentence structure',
  'Paragraphing',
  'Argument',
  'Using sources',
  'Academic tone',
];

export default function Learn({ go }) {
  const [levels, setLevels] = useState(null);
  const [card, setCard] = useState(null);
  const [loadingCard, setLoadingCard] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    api.levelCheck()
      .then((res) => setLevels(res.levels || {}))
      .catch((err) => setError(err.message));
  }, []);

  const openSkill = (skill) => {
    setError('');
    setLoadingCard(true);
    setCard(null);
    api.learn(skill)
      .then((res) => setCard(res))
      .catch((err) => setError(err.message))
      .finally(() => setLoadingCard(false));
  };

  if (error) return <div><h2>Learn</h2><div className="error">{error}</div></div>;
  if (!levels) return <div><h2>Learn</h2><p className="loading">Loading…</p></div>;

  if (card || loadingCard) {
    return (
      <div>
        <h2>Learn</h2>
        {loadingCard && <p className="loading">Loading…</p>}
        {card && <LearnCard card={card} onPractise={() => go('practice')} />}
        <button className="btn secondary" onClick={() => setCard(null)}>
          All skills
        </button>
      </div>
    );
  }

  return (
    <div>
      <h2>Learn</h2>
      {SKILLS.map((skill) => (
        <button
          key={skill}
          className="btn secondary option-btn"
          onClick={() => openSkill(skill)}
        >
          {skill}
          <span className="level-chip">Level {levels[skill]?.level || 1}</span>
        </button>
      ))}
    </div>
  );
}
