import { useEffect, useState } from 'react';
import { api } from '../api.js';

// Home: exactly one next action. No chat box here.
const ACTIONS = {
  Paragraphing: 'write a topic sentence',
  Grammar: 'fix verb endings',
  Vocabulary: 'swap one weak word',
  'Sentence structure': 'join two short sentences',
  Argument: 'add one reason word',
  'Using sources': 'name one source',
  'Academic tone': 'remove one chatty word',
};

// Paragraph-family skills practise best by writing; the rest by drills.
const GOES_TO_WRITE = new Set(['Paragraphing', 'Argument', 'Academic tone']);

export default function Home({ go }) {
  const [state, setState] = useState({ loading: true });

  useEffect(() => {
    Promise.all([api.growth(), api.levelCheck()])
      .then(([growth, levels]) => setState({ loading: false, growth, levels }))
      .catch((err) => setState({ loading: false, error: err.message }));
  }, []);

  if (state.loading) return <p className="loading">Loading…</p>;
  if (state.error) return <div className="error">{state.error}</div>;

  const scores = state.growth.scores || {};
  const names = Object.keys(scores);
  if (names.length === 0) {
    return (
      <div>
        <h2>Start here</h2>
        <div className="card tint">
          <div className="card-title">Write your first paragraph</div>
          <p className="muted">Your twin will find your weakest skill.</p>
        </div>
        <button className="btn" onClick={() => go('write')}>Write now</button>
        <button className="linklike" onClick={() => go('teacher')}>Teacher tools</button>
      </div>
    );
  }

  const weakest = names.reduce((a, b) => (scores[a] <= scores[b] ? a : b));
  const leveled = state.levels.leveled_up || [];

  return (
    <div>
      <h2>Your next step</h2>
      {leveled.length > 0 && (
        <div className="levelup">Level up in {leveled.join(', ')}! See My Growth.</div>
      )}
      <div className="card tint">
        <div className="card-title">
          Fix your weakest skill: {ACTIONS[weakest] || 'practise a little'}
        </div>
        <p className="muted">{weakest} is at {Math.round(scores[weakest])}/100.</p>
      </div>
      <button className="btn" onClick={() => go(GOES_TO_WRITE.has(weakest) ? 'write' : 'practice')}>
        Start
      </button>
      <button className="linklike" onClick={() => go('teacher')}>Teacher tools</button>
    </div>
  );
}
