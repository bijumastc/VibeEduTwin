// LearnCard: one short rule, its source, and good/weak discipline examples.
// Shared by the Write result screen and the Learn tab.
export default function LearnCard({ card, onPractise }) {
  const source = [card.source, card.chapter].filter(Boolean).join(' · ');
  return (
    <div className="card">
      <div className="card-title">Learn: {card.skill}</div>
      <p>{card.rule}</p>
      <p className="muted">
        <em>{source}</em> ({card.license || 'license unknown'})
      </p>
      <p><strong>Good:</strong> {card.good_example}</p>
      <p><strong>Weak:</strong> {card.weak_example}</p>
      <button className="btn" onClick={onPractise}>Practise this</button>
    </div>
  );
}
