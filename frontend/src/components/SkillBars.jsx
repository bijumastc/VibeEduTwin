// Horizontal bars for the 7 skills. Weakest skill gets a "focus" tag.
const ORDER = ['Grammar', 'Vocabulary', 'Sentence structure', 'Paragraphing',
  'Argument', 'Using sources', 'Academic tone'];

export default function SkillBars({ scores, weakest }) {
  return (
    <div>
      {ORDER.filter((s) => scores[s] !== undefined).map((skill) => (
        <div className="skill-row" key={skill}>
          <div className="skill-top">
            <span>
              <span className="skill-name">{skill}</span>
              {skill === weakest && <span className="focus-tag">focus</span>}
            </span>
            <span>{Math.round(scores[skill])}</span>
          </div>
          <div className="bar">
            <div style={{ width: `${Math.max(0, Math.min(100, scores[skill]))}%` }} />
          </div>
        </div>
      ))}
    </div>
  );
}
