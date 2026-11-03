import { useState } from 'react';
import BasedOn from './BasedOn.jsx';
import ScaffoldTask from './ScaffoldTask.jsx';

// LessonView: one idea per screen - Hook, Try first, The idea, Real example,
// Your turn, Why it matters. Stepper with Back/Next; Your turn opens the task.
const STEPS = ['Hook', 'Try first', 'The idea', 'Real example', 'Your turn', 'Why it matters'];

export default function LessonView({ lesson, go, onBack }) {
  const [step, setStep] = useState(0);
  const [picked, setPicked] = useState(null);
  const [taskOpen, setTaskOpen] = useState(false);

  if (taskOpen) {
    return (
      <ScaffoldTask
        discipline={lesson.discipline}
        moduleId={lesson.module}
        moduleTitle={lesson.title}
        onBack={() => setTaskOpen(false)}
      />
    );
  }

  const last = STEPS.length - 1;
  const tryBlock = lesson.try_first;

  return (
    <div>
      <h2>{lesson.title}</h2>
      <p className="muted step-progress">Step {step + 1} of {STEPS.length} · {STEPS[step]}</p>

      {step === 0 && (
        <div className="card">
          <p>{lesson.hook}</p>
        </div>
      )}

      {step === 1 && (
        <div className="card">
          <p>{tryBlock.prompt}</p>
          {tryBlock.options.map((option, i) => (
            <button
              key={option}
              className="btn secondary option-btn"
              onClick={() => picked === null && setPicked(i)}
              disabled={picked !== null}
            >
              {option}
            </button>
          ))}
          {picked !== null && (
            <>
              <p className="muted">Best answer: {tryBlock.options[tryBlock.answer]}</p>
              <p>{tryBlock.reveal}</p>
            </>
          )}
        </div>
      )}

      {step === 2 && (
        <div className="card">
          <p>{lesson.idea.text}</p>
          <BasedOn books={lesson.based_on} />
        </div>
      )}

      {step === 3 && (
        <div className="card">
          <p><em>&ldquo;{lesson.example.text}&rdquo;</em></p>
          <BasedOn books={lesson.based_on} />
        </div>
      )}

      {step === 4 && (
        <div className="card">
          <p>{lesson.task}</p>
          <button className="btn" onClick={() => setTaskOpen(true)}>Start task</button>
        </div>
      )}

      {step === 5 && (
        <div className="card accent-soft">
          <div className="card-title">Why it matters to you</div>
          <p>{lesson.why}</p>
        </div>
      )}

      <div className="step-nav">
        <button
          className="btn secondary"
          onClick={() => setStep((s) => Math.max(0, s - 1))}
          disabled={step === 0}
        >
          Back
        </button>
        {step < last && (
          <button className="btn" onClick={() => setStep((s) => s + 1)}>Next</button>
        )}
        {step === last && (
          <button className="btn" onClick={() => go('practice')}>Practise this</button>
        )}
      </div>
      <div style={{ height: 10 }} />
      <button className="btn secondary" onClick={onBack}>All modules</button>
    </div>
  );
}
