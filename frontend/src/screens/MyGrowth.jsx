import { useEffect, useState } from 'react';
import { api, LeveledUp } from '../api.js';
import SkillBars from '../components/SkillBars.jsx';

// My Growth: the full chart unlocks only after the first level-up.
export default function MyGrowth({ go }) {
  const [state, setState] = useState({ loading: true });

  useEffect(() => {
    Promise.all([api.growth(), api.levelCheck()])
      .then(([growth, levels]) => {
        if ((levels.leveled_up || []).length > 0) LeveledUp.set();
        setState({ loading: false, growth, levels });
      })
      .catch((err) => setState({ loading: false, error: err.message }));
  }, []);

  if (state.loading) return <p className="loading">Loading…</p>;
  if (state.error) return <div className="error">{state.error}</div>;

  const scores = state.growth.scores || {};
  const names = Object.keys(scores);
  if (names.length === 0) {
    return (
      <div>
        <h2>My Growth</h2>
        <div className="card tint">
          <div className="card-title">No scores yet</div>
          <p className="muted">Write a paragraph to get your first diagnosis.</p>
        </div>
        <button className="btn" onClick={() => go('write')}>Write now</button>
      </div>
    );
  }

  if (!LeveledUp.get()) {
    const weakest = names.reduce((a, b) => (scores[a] <= scores[b] ? a : b));
    return (
      <div>
        <h2>My Growth</h2>
        <div className="card tint">
          <div className="card-title">Your chart unlocks at level 2</div>
          <p className="muted">
            Current focus is {weakest} ({Math.round(scores[weakest])}/100).
            Score {80}%+ in practice to level up.
          </p>
        </div>
        <button className="btn" onClick={() => go('practice')}>Practise now</button>
      </div>
    );
  }

  const weakest = names.reduce((a, b) => (scores[a] <= scores[b] ? a : b));
  const levels = state.levels.levels || {};
  return (
    <div>
      <h2>My Growth</h2>
      <div className="card">
        <SkillBars scores={scores} weakest={weakest} />
      </div>
      <div className="card tint">
        {Object.keys(levels).map((skill) => (
          <div key={skill}>
            {skill}
            <span className="level-chip">Level {levels[skill].level}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
