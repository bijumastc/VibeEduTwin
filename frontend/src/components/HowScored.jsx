import { useState } from 'react';
import { api } from '../api.js';

// "How I'm scored": the fixed 7-skill rubric, the same data the Diagnoser
// sends to Muse Spark. Shared by the learner diagnosis card and Teacher tools.
export default function HowScored() {
  const [open, setOpen] = useState(false);
  const [rubric, setRubric] = useState(null);

  const toggle = async () => {
    if (!open && !rubric) {
      try {
        setRubric(await api.rubric());
      } catch {
        return; // stay closed when the backend is unreachable
      }
    }
    setOpen(!open);
  };

  return (
    <div className="card">
      <button className="btn secondary" onClick={toggle}>How I'm scored</button>
      {open && rubric && rubric.skills.map((entry) => (
        <div key={entry.skill}>
          <div className="card-title">{entry.skill}</div>
          {entry.levels.map((line, i) => (
            <p key={i} className="muted">L{i + 1}: {line}</p>
          ))}
        </div>
      ))}
    </div>
  );
}
