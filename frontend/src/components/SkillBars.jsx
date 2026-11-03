// Horizontal bars for the 7 skills. Weakest skill gets a "focus" tag.
// With levels, each row also shows the previous draft's level next to the new one.
const ORDER = ['Grammar', 'Vocabulary', 'Sentence structure', 'Paragraphing',
  'Argument', 'Using sources', 'Academic tone'];

export default function SkillBars({ scores, weakest, levels }) {
  return (
    <div>
      {ORDER.filter((s) => scores[s] !== undefined).map((skill) => (
        <div className="skill-row" key={skill}>
          <div className="skill-top">
            <span>
              <span className="skill-name">{skill}</span>
              {skill === weakest && <span className="focus-tag">focus</span>}
            </span>
            <span>
              {Math.round(scores[skill])}
              {levels?.[skill] && (
                <span className="muted">
                  {' '}· {levels[skill].previous != null
                    ? `Level ${levels[skill].previous} → ${levels[skill].current}`
                    : `Level ${levels[skill].current}`}
                </span>
              )}
            </span>
          </div>
          <div className="bar">
            <div style={{ width: `${Math.max(0, Math.min(100, scores[skill]))}%` }} />
          </div>
        </div>
      ))}
    </div>
  );
}
