import { useState } from 'react';
import BasedOn from './BasedOn.jsx';

// CompactLesson: the post-diagnosis card - one line connecting it to the
// learner's sentence, the idea, then the book excerpt behind Read more.
export default function CompactLesson({ title, connect, idea, example, basedOn, onPractise }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="card">
      <div className="card-title">{title}</div>
      {connect && <p>{connect}</p>}
      <p><strong>The idea:</strong> {idea.text}</p>
      {!open ? (
        <button className="btn secondary" onClick={() => setOpen(true)}>
          Read more from the book
        </button>
      ) : (
        <p><strong>Real example:</strong> <em>&ldquo;{example.text}&rdquo;</em></p>
      )}
      <BasedOn books={basedOn} />
      <button className="btn" onClick={onPractise}>Practise this</button>
    </div>
  );
}
