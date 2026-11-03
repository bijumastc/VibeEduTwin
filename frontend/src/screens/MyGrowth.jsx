import { useEffect, useState } from 'react';
import { api, LeveledUp } from '../api.js';
import SkillBars from '../components/SkillBars.jsx';

// My Growth: skill chart on top, drafts with feedback below. The full chart
// unlocks only after the first level-up; drafts always show.
export default function MyGrowth({ go }) {
  const [state, setState] = useState({ loading: true });

  useEffect(() => {
    Promise.all([api.growth(), api.levelCheck(), api.drafts(), api.independence()])
      .then(([growth, levels, draftsRes, independence]) => {
        if ((levels.leveled_up || []).length > 0) LeveledUp.set();
        setState({
          loading: false,
          growth,
          levels,
          drafts: [...draftsRes.drafts].reverse(),
          independence,
        });
      })
      .catch((err) => setState({ loading: false, error: err.message }));
  }, []);

  if (state.loading) return <p className="loading">Loading…</p>;
  if (state.error) return <div className="error">{state.error}</div>;

  const scores = state.growth.scores || {};
  const names = Object.keys(scores);
  const weakest = names.length > 0
    ? names.reduce((a, b) => (scores[a] <= scores[b] ? a : b))
    : null;
  const levels = state.levels.levels || {};

  return (
    <div>
      <h2>My Growth</h2>
      {names.length === 0 && (
        <div className="card tint">
          <div className="card-title">No scores yet</div>
          <p className="muted">Write a paragraph to get your first diagnosis.</p>
        </div>
      )}
      {names.length > 0 && !LeveledUp.get() && (
        <div className="card tint">
          <div className="card-title">Your chart unlocks at level 2</div>
          <p className="muted">
            Current focus is {weakest} ({Math.round(scores[weakest])}/100).
            Score {80}%+ in practice to level up.
          </p>
        </div>
      )}
      {names.length > 0 && LeveledUp.get() && (
        <>
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
        </>
      )}
      {(names.length === 0 || !LeveledUp.get()) && (
        <button className="btn" onClick={() => go(names.length === 0 ? 'write' : 'practice')}>
          {names.length === 0 ? 'Write now' : 'Practise now'}
        </button>
      )}

      <div className="card">
        <div className="card-title">Working more independently</div>
        <p className="muted">{state.independence.message}</p>
      </div>

      <h2>My drafts</h2>
      {state.drafts.length === 0 && (
        <div className="card tint">
          <div className="card-title">Nothing here yet</div>
          <p className="muted">Your paragraphs will appear here.</p>
        </div>
      )}
      {state.drafts.map((d) => (
        <div className="card" key={d.id}>
          <div className="draft-date">{String(d.created_at).slice(0, 10)}</div>
          <p>{d.content}</p>
          <p className="muted">{d.feedback || 'No feedback yet.'}</p>
        </div>
      ))}
    </div>
  );
}
