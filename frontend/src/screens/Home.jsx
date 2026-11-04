import { useEffect, useState } from 'react';
import { api, OpenModule } from '../api.js';

// My Level: hero for new learners, writing-profile card after diagnosis.
// Skill chips reuse the Learn module look; the next-win button deep-links
// into the matching Learn module.
const ORDER = ['Grammar', 'Vocabulary', 'Sentence structure', 'Paragraphing',
  'Argument', 'Using sources', 'Academic tone'];

const SKILL_MODULE = {
  Grammar: 'mechanics',
  Vocabulary: 'academic-vocabulary',
  'Sentence structure': 'coherence-flow',
  Paragraphing: 'topic-sentences',
  Argument: 'thesis-statements',
  'Using sources': 'using-sources',
  'Academic tone': 'genre',
};

export default function Home({ go }) {
  const [state, setState] = useState({ loading: true });

  useEffect(() => {
    Promise.all([api.growth(), api.levelCheck(), api.drafts()])
      .then(([growth, levels, draftsRes]) => setState({
        loading: false, growth, levels, drafts: draftsRes.drafts || [],
      }))
      .catch((err) => setState({ loading: false, error: err.message }));
  }, []);

  if (state.loading) return <p className="loading">Loading…</p>;
  if (state.error) return <div className="error">{state.error}</div>;

  if (state.drafts.length === 0) {
    return (
      <div>
        <h2>My Level</h2>
        <div className="card tint">
          <div className="card-title">Discover your writing level ✍️</div>
          <p>Write 4-5 lines on any topic. In one minute, your twin shows what you already do well and your next win.</p>
        </div>
        <button className="btn" onClick={() => go('write')}>Find my level</button>
        <div>
          <button className="linklike" onClick={() => go('write')}>Speak it</button>
          {' · '}
          <button className="linklike" onClick={() => go('write')}>Scan my notebook</button>
        </div>
        <button className="linklike" onClick={() => go('teacher')}>Teacher tools</button>
      </div>
    );
  }

  const scores = state.growth.scores || {};
  const names = Object.keys(scores);
  if (names.length === 0 || !state.growth.next_win) {
    return (
      <div>
        <h2>My Level</h2>
        <div className="card tint">
          <div className="card-title">Your paragraph is waiting</div>
          <p className="muted">Submit it so your twin can diagnose it.</p>
        </div>
        <button className="btn" onClick={() => go('write')}>Find my level</button>
        <button className="linklike" onClick={() => go('teacher')}>Teacher tools</button>
      </div>
    );
  }

  const levels = state.growth.levels || {};
  const { strongest, next_win } = state.growth;
  const leveled = state.levels.leveled_up || [];
  const openModule = (moduleId) => {
    OpenModule.set(moduleId);
    go('learn');
  };

  return (
    <div>
      <h2>My Level</h2>
      {leveled.length > 0 && (
        <div className="levelup">Level up in {leveled.join(', ')}! See My Growth.</div>
      )}
      <div className="card tint">
        <div className="card-title">Your writing profile</div>
        {ORDER.filter((s) => levels[s] !== undefined).map((skill) => (
          <button
            key={skill}
            className="btn secondary option-btn"
            onClick={() => openModule(SKILL_MODULE[skill])}
          >
            {skill}
            <span className="level-chip">Level {levels[skill]} of 5</span>
          </button>
        ))}
      </div>
      <div className="card">
        <p><strong>You do well: {strongest.skill}</strong></p>
        <p className="muted">{strongest.reason}</p>
      </div>
      <div className="card">
        <p><strong>Your next win: {next_win.action}</strong></p>
        {next_win.quote && <p className="muted">&ldquo;{next_win.quote}&rdquo;</p>}
        <button className="btn" onClick={() => openModule(SKILL_MODULE[next_win.skill])}>
          Start my next win (5 min)
        </button>
        <div>
          <button className="linklike" onClick={() => go('write')}>Check my level again</button>
        </div>
      </div>
      <button className="linklike" onClick={() => go('teacher')}>Teacher tools</button>
    </div>
  );
}
