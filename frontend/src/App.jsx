import { useEffect, useState } from 'react';
import { api } from './api.js';
import Home from './screens/Home.jsx';
import Write from './screens/Write.jsx';
import Learn from './screens/Learn.jsx';
import Practice from './screens/Practice.jsx';
import MyGrowth from './screens/MyGrowth.jsx';
import Teacher from './screens/Teacher.jsx';
import BottomNav from './components/BottomNav.jsx';

// Five tabs, no router needed: simple state switch.
export default function App() {
  const [tab, setTab] = useState('home');
  const [demo, setDemo] = useState(false);

  useEffect(() => {
    api.config().then((c) => setDemo(!!c.demo_mode)).catch(() => {});
  }, []);

  const go = (next) => {
    setTab(next);
    window.scrollTo(0, 0);
  };

  return (
    <div className="app">
      <header className="topbar">
        <span className="brand">VibeEduTwin</span>
        {demo && <span className="demo-badge">Demo mode</span>}
      </header>
      <main className="screen">
        {tab === 'home' && <Home go={go} />}
        {tab === 'write' && <Write go={go} />}
        {tab === 'learn' && <Learn go={go} />}
        {tab === 'practice' && <Practice go={go} />}
        {tab === 'growth' && <MyGrowth go={go} />}
        {tab === 'teacher' && <Teacher go={go} />}
      </main>
      <BottomNav tab={tab} go={go} />
    </div>
  );
}
