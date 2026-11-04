// Feedback on your paragraph: twin message, what went well, problems,
// grammar fixes, word tips, improve points, one model rewrite, your turn.
// Shared by Write (model is a rewrite) and the Assessor (modelSentence is
// a different-topic line); polish unlocks after their own rewrite.
const PENCIL = '✏️';

export default function FeedbackCard({ feedback, onRewrite, modelSentence, fallback, polish, onPolish, title }) {
  if (!feedback) return null;
  const { strength, problems, model, your_turn, motivation } = feedback;
  const showQuote = (quote, line) => quote && line && !line.includes(quote);
  return (
    <div className="card">
      <div className="card-title">{title || 'Feedback on your paragraph'}</div>
      {motivation?.twin_message && <p>{motivation.twin_message}</p>}
      {strength && (
        <div>
          <p><strong>What went well:</strong> {showQuote(strength.quote, strength.line) && <span>&ldquo;{strength.quote}&rdquo; </span>}{strength.line}</p>
        </div>
      )}
      {(problems || []).map((problem, i) => (
        <div key={i}>
          <p><strong>Problem {i + 1}:</strong> {showQuote(problem.quote, problem.wrong) && <span>&ldquo;{problem.quote}&rdquo; </span>}{problem.wrong}</p>
          {problem.why && <p className="muted">{problem.why}</p>}
          <p>Fix it like this: {problem.fix}</p>
        </div>
      ))}
      {fallback && !strength && (problems || []).length === 0 && <p>{fallback}</p>}
      {(motivation?.grammar_fixes || []).length > 0 && (
        <div>
          <p><strong>Grammar fixes:</strong></p>
          {motivation.grammar_fixes.map((fix, i) => (
            <p key={i}>&ldquo;{fix.wrong}&rdquo; &rarr; &ldquo;{fix.right}&rdquo; <span className="muted">({fix.rule})</span></p>
          ))}
        </div>
      )}
      {(motivation?.vocab_tips || []).length > 0 && (
        <div>
          <p><strong>Word tips:</strong></p>
          {motivation.vocab_tips.map((tip, i) => <p key={i}>{tip.tip}</p>)}
        </div>
      )}
      {(motivation?.improve || []).length > 0 && (
        <div>
          <p><strong>Improve:</strong></p>
          {motivation.improve.map((point, i) => <p key={i}>{i + 1}. {point}</p>)}
          {motivation.critical_tip && <p><strong>Think deeper:</strong> {motivation.critical_tip}</p>}
        </div>
      )}
      {motivation?.next_goal && <p><strong>{motivation.next_goal}</strong></p>}
      {model && (
        <div>
          <p><strong>{PENCIL} Let me show you one</strong></p>
          <p className="muted">Before: &ldquo;{model.before}&rdquo;</p>
          <p>After: &ldquo;{model.after}&rdquo;</p>
          <p className="muted">{model.changed}</p>
        </div>
      )}
      {!model && modelSentence && (
        <p><strong>{PENCIL} Let me show you one:</strong> {modelSentence}</p>
      )}
      {your_turn && <p>{your_turn}</p>}
      {onRewrite && <button className="btn" onClick={onRewrite}>Rewrite my paragraph</button>}
      {polish?.unlocked && !polish?.text && (
        <div>
          <button className="btn secondary" onClick={onPolish} disabled={polish?.loading}>
            {polish?.loading ? 'Polishing…' : 'Compare with a polished version'}
          </button>
          {polish?.error && <p className="error">{polish.error}</p>}
        </div>
      )}
      {polish?.text && (
        <div className="card tint">
          <div className="card-title">Polished version</div>
          <p className="muted">Yours: &ldquo;{polish.original}&rdquo;</p>
          <p>Polished: &ldquo;{polish.text}&rdquo;</p>
        </div>
      )}
    </div>
  );
}
