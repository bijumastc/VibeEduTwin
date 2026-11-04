// Bottom navigation: exactly the 5 tabs, text labels, active pill.
const TABS = [
  { id: 'home', label: 'My Level' },
  { id: 'write', label: 'Write' },
  { id: 'learn', label: 'Learn' },
  { id: 'practice', label: 'Practice' },
  { id: 'growth', label: 'My Growth' },
];

export default function BottomNav({ tab, go }) {
  return (
    <nav className="bottomnav">
      {TABS.map((t) => (
        <button
          key={t.id}
          className={tab === t.id ? 'active' : ''}
          onClick={() => go(t.id)}
        >
          {t.label}
        </button>
      ))}
    </nav>
  );
}
