import { useEffect, useState } from 'react';
import { api } from '../api.js';

// My Writing: newest-first list of drafts with their feedback.
export default function MyWriting({ go }) {
  const [state, setState] = useState({ loading: true });

  useEffect(() => {
    api.drafts()
      .then((res) => setState({ loading: false, drafts: [...res.drafts].reverse() }))
      .catch((err) => setState({ loading: false, error: err.message }));
  }, []);

  if (state.loading) return <p className="loading">Loading…</p>;
  if (state.error) return <div className="error">{state.error}</div>;

  if (state.drafts.length === 0) {
    return (
      <div>
        <h2>My Writing</h2>
        <div className="card tint">
          <div className="card-title">Nothing here yet</div>
          <p className="muted">Your paragraphs will appear here.</p>
        </div>
        <button className="btn" onClick={() => go('write')}>Write now</button>
      </div>
    );
  }

  return (
    <div>
      <h2>My Writing</h2>
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
