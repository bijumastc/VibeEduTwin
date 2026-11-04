import { useEffect, useState } from 'react';
import { api, OpenModule } from '../api.js';
import LessonView from '../components/LessonView.jsx';

// Learn: curriculum of 6 disciplines x 9 ordered modules. The learner's own
// discipline opens by default; others are browsable. All modules are open;
// the weakest skill's module carries "Recommended for you".
export default function Learn({ go }) {
  const [data, setData] = useState(null);
  const [discipline, setDiscipline] = useState('');
  const [content, setContent] = useState(null);
  const [loadingContent, setLoadingContent] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    api.curriculum()
      .then((res) => {
        setData(res);
        setDiscipline(res.discipline);
        const pending = OpenModule.consume();
        const modules = (res.disciplines.find((d) => d.name === res.discipline)
          || {}).modules || [];
        if (pending && modules.some((m) => m.id === pending)) {
          openModuleFor(res.discipline, pending);
        }
      })
      .catch((err) => setError(err.message));
  }, []);

  const openModuleFor = (disc, moduleId) => {
    setError('');
    setLoadingContent(true);
    setContent(null);
    api.moduleContent(disc, moduleId)
      .then((res) => setContent(res))
      .catch((err) => setError(err.message))
      .finally(() => setLoadingContent(false));
  };

  const openModule = (moduleId) => openModuleFor(discipline, moduleId);

  const pickDiscipline = (name) => {
    setDiscipline(name);
    setContent(null);
    setError('');
  };

  if (error) return <div><h2>Learn</h2><div className="error">{error}</div></div>;
  if (!data) return <div><h2>Learn</h2><p className="loading">Loading…</p></div>;

  if (content || loadingContent) {
    if (loadingContent || !content) {
      return <div><h2>Learn</h2><p className="loading">Loading…</p></div>;
    }
    return (
      <LessonView lesson={content} go={go} onBack={() => setContent(null)} />
    );
  }

  const current = data.disciplines.find((d) => d.name === discipline) || data.disciplines[0];

  return (
    <div>
      <h2>Learn</h2>
      <p className="muted">Your discipline: {data.discipline}</p>
      <div className="chip-row">
        {data.disciplines.map((d) => (
          <button
            key={d.name}
            className={d.name === current.name ? 'active' : ''}
            onClick={() => pickDiscipline(d.name)}
          >
            {d.name}
          </button>
        ))}
      </div>
      {current.modules.map((m) => (
        <div key={m.id}>
          <button
            className="btn secondary option-btn"
            onClick={() => openModule(m.id)}
          >
            {m.title}
            {m.recommended && <span className="focus-tag">Recommended for you</span>}
            <span className="level-chip">Level {m.learner_level}</span>
          </button>
        </div>
      ))}
    </div>
  );
}
