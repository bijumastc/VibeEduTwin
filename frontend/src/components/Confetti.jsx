import { useEffect, useState } from 'react';

// Short confetti burst for level-ups: falls once, then clears itself.
const COLORS = ['#e0635a', '#e8a13d', '#4d9b6b', '#4d7dc9', '#9b59c9'];
const COUNT = 28;

export default function Confetti() {
  const [gone, setGone] = useState(false);
  useEffect(() => {
    const timer = setTimeout(() => setGone(true), 3000);
    return () => clearTimeout(timer);
  }, []);
  if (gone) return null;
  return (
    <div className="confetti" aria-hidden="true">
      {Array.from({ length: COUNT }, (_, i) => (
        <i
          key={i}
          style={{
            left: `${(i * 37) % 100}%`,
            background: COLORS[i % COLORS.length],
            animationDelay: `${(i % 12) / 12}s`,
            borderRadius: i % 3 === 0 ? '50%' : '2px',
          }}
        />
      ))}
    </div>
  );
}
