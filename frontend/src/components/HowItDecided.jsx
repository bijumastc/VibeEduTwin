import { useEffect, useState } from 'react';
import { api } from '../api.js';

// How it decided: collapsible audit trail, closed by default. At most 6
// plain-text lines per submission: step, agent, tool called, result.
export default function HowItDecided({ refreshKey }) {
  const [events, setEvents] = useState(null);

  useEffect(() => {
    api.events()
      .then((res) => setEvents((res.events || []).slice(0, 6)))
      .catch(() => setEvents([]));
  }, [refreshKey]);

  return (
    <details className="card">
      <summary>How it decided</summary>
      {events === null && <p className="loading">Loading…</p>}
      {events !== null && events.length === 0 && (
        <p className="muted">Nothing logged yet.</p>
      )}
      {events !== null && events.map((e, i) => (
        <p className="muted" key={i}>{e.step} · {e.agent} · {e.tool} · {e.result}</p>
      ))}
    </details>
  );
}
