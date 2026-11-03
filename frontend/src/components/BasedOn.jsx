import { useState } from 'react';

// BasedOn: small info icon. Opens "Based on: [book title], [publisher], [license]".
// Publisher shows only when the manifest records it.
export default function BasedOn({ books }) {
  const [open, setOpen] = useState(false);
  if (!books || books.length === 0) return null;
  return (
    <div>
      <button
        className="info-btn"
        onClick={() => setOpen((o) => !o)}
        aria-label="Where this lesson comes from"
      >
        ⓘ
      </button>
      {open && books.map((b, i) => (
        <p className="muted based-on" key={i}>
          Based on: {[b.title, b.publisher, b.license].filter(Boolean).join(', ')}
        </p>
      ))}
    </div>
  );
}
