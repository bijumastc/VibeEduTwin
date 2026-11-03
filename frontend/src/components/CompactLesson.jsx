import BasedOn from './BasedOn.jsx';

// CompactLesson: the post-diagnosis card - idea + real example + sources
// behind the info icon, then straight to practice.
export default function CompactLesson({ title, idea, example, basedOn, onPractise }) {
  return (
    <div className="card">
      <div className="card-title">{title}</div>
      <p><strong>The idea:</strong> {idea.text}</p>
      <p><strong>Real example:</strong> <em>&ldquo;{example.text}&rdquo;</em></p>
      <BasedOn books={basedOn} />
      <button className="btn" onClick={onPractise}>Practise this</button>
    </div>
  );
}
