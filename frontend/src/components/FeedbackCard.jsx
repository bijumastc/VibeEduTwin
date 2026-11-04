// Feedback on your paragraph: one strength, two problems, one model
// rewrite (before → after), then your turn with a Rewrite button.
export default function FeedbackCard({ feedback, onRewrite }) {
  if (!feedback) return null;
  const { strength, problems, model, your_turn } = feedback;
  return (
    <div className="card">
      <div className="card-title">Feedback on your paragraph</div>
      {strength && (
        <div>
          <p><strong>What works:</strong> &ldquo;{strength.quote}&rdquo;</p>
          <p>{strength.line}</p>
        </div>
      )}
      {(problems || []).map((problem, i) => (
        <div key={i}>
          <p><strong>Problem {i + 1}:</strong> &ldquo;{problem.quote}&rdquo;</p>
          <p>{problem.wrong}</p>
          <p className="muted">{problem.why}</p>
          <p>Fix it like this: {problem.fix}</p>
        </div>
      ))}
      {model && (
        <div>
          <p><strong>✏️ Let me show you one</strong></p>
          <p className="muted">Before: &ldquo;{model.before}&rdquo;</p>
          <p>After: &ldquo;{model.after}&rdquo;</p>
          <p className="muted">{model.changed}</p>
        </div>
      )}
      {your_turn && <p>{your_turn}</p>}
      <button className="btn" onClick={onRewrite}>Rewrite my paragraph</button>
    </div>
  );
}
