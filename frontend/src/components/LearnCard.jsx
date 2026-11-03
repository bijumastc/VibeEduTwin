// LearnCard: one verified rule + one verified example, each with its
// book/chapter/license underneath. Shared by the Write result screen and
// the Learn tab's module view.
function cite(part) {
  return [part.source, part.chapter].filter(Boolean).join(' · ');
}

export default function LearnCard({ title, rule, example, onPractise }) {
  return (
    <div className="card">
      <div className="card-title">{title}</div>
      <p><strong>Rule:</strong> {rule.text}</p>
      {rule.source && (
        <p className="muted"><em>{cite(rule)}</em> ({rule.license || 'license unknown'})</p>
      )}
      <p><strong>Example:</strong> {example.text}</p>
      {example.source && (
        <p className="muted"><em>{cite(example)}</em> ({example.license || 'license unknown'})</p>
      )}
      <button className="btn" onClick={onPractise}>Practise this</button>
    </div>
  );
}
