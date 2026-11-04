import { useEffect, useState } from 'react';
import { api, OpenModule, levelName } from '../api.js';
import Confetti from '../components/Confetti.jsx';

// My Level: hero for new learners, writing-profile card after diagnosis.
// Skill chips reuse the Learn module look; the next-win button deep-links
// into the matching Learn module. Daily goal and goodbye wrap up the day.
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

  const daily = state.growth?.daily || { sessions: 0, target: 3, paragraphs: 0 };
  const dailyLine = (
    <div className="card">
      <p className="muted">Daily goal: {Math.min(daily.sessions, daily.target)} of {daily.target} sessions today</p>
      <div className="dots" aria-label={`${daily.sessions} of ${daily.target} sessions done`}>
        {[0, 1, 2].map((i) => (
          <span key={i}>{i < daily.sessions ? '●' : '○'}</span>
        ))}
      </div>
    </div>
  );

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
        {dailyLine}
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
  const { strongest, next_win, session } = state.growth;
  const leveled = state.levels.leveled_up || [];
  const openModule = (moduleId) => {
    OpenModule.set(moduleId);
    go('learn');
  };
  const sessionDone = session && session.sessions_done >= session.sessions_target;
  const sessionSteps = ['Write your paragraph', 'Read feedback and fix it', 'One short practice set'];

  return (
    <div>
      <h2>My Level</h2>
      {leveled.length > 0 && (
        <>
          <Confetti key={leveled.join(',')} />
          <div className="levelup">Level up in {leveled.join(', ')}! See My Growth.</div>
        </>
      )}
      {session && (
        <div className="card tint">
          <div className="card-title">Today&apos;s session</div>
          <p className="muted">
            Level {session.level} {session.level_name} · write about {session.topic} · {session.target} words
          </p>
          {sessionSteps.map((label, i) => (
            <p className="muted" key={label}>
              {session.steps_done[i] ? '✓' : (session.step === i + 1 && !sessionDone ? '→' : '·')} {label}
            </p>
          ))}
          {sessionDone ? (
            <p><strong>Session complete! 🎉</strong> {daily.paragraphs} paragraph{daily.paragraphs === 1 ? '' : 's'} today. Next time: {next_win.action}.</p>
          ) : (
            <button className="btn" onClick={() => go('write')}>
              {session.started ? "Continue today's session" : "Start today's session"}
            </button>
          )}
        </div>
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
            <span className="level-chip">Level {levels[skill]} of 5 · {levelName(levels[skill])}</span>
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
      {dailyLine}
      {daily.paragraphs > 0 && (
        <div className="card">
          <div className="card-title">Goodbye for now 👋</div>
          <p className="muted">
            Today you wrote {daily.paragraphs} paragraph{daily.paragraphs === 1 ? '' : 's'}.
            Next time: {next_win.action}. See you soon!
          </p>
        </div>
      )}
      <button className="linklike" onClick={() => go('teacher')}>Teacher tools</button>
    </div>
  );
}
