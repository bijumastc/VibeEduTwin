// Skill rows: Level X of 5 with the Diagnoser's reason and evidence quote.
// Weakest skill gets a "focus" tag; level changes add previous → current.
import { levelName } from '../api.js';

const ORDER = ['Grammar', 'Vocabulary', 'Sentence structure', 'Paragraphing',
  'Argument', 'Using sources', 'Academic tone'];

// Same bands as the backend level_for_score; used only when no level given.
const levelFor = (score) => {
  if (score < 20) return 1;
  if (score < 40) return 2;
  if (score < 60) return 3;
  if (score < 80) return 4;
  return 5;
};

export default function SkillBars({ scores, weakest, levels, details }) {
  return (
    <div>
      {ORDER.filter((s) => scores[s] !== undefined).map((skill) => {
        const entry = levels?.[skill];
        const current = typeof entry === 'number' ? entry : (entry?.current ?? levelFor(scores[skill]));
        const previous = typeof entry === 'number' ? null : entry?.previous ?? null;
        const detail = details?.[skill];
        return (
          <div className="skill-row" key={skill}>
            <div className="skill-top">
              <span>
                <span className="skill-name">{skill}</span>
                {skill === weakest && <span className="focus-tag">focus</span>}
              </span>
              <span>
                {previous != null && previous !== current
                  ? `Level ${previous} → ${current} of 5 · ${levelName(current)}`
                  : `Level ${current} of 5 · ${levelName(current)}`}
              </span>
            </div>
            <div className="bar">
              <div style={{ width: `${(current / 5) * 100}%` }} />
            </div>
            {detail?.reason && (
              <p className="muted skill-why">
                {detail.reason} <em>&ldquo;{detail.evidence}&rdquo;</em>
              </p>
            )}
          </div>
        );
      })}
    </div>
  );
}
