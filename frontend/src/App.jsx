import { useState } from 'react';
import Home from './screens/Home.jsx';
import Write from './screens/Write.jsx';
import Learn from './screens/Learn.jsx';
import Practice from './screens/Practice.jsx';
import MyGrowth from './screens/MyGrowth.jsx';
import BottomNav from './components/BottomNav.jsx';

// Five tabs, no router needed: simple state switch.
export default function App() {
  const [tab, setTab] = useState('home');

  const go = (next) => {
    setTab(next);
    window.scrollTo(0, 0);
  };

  return (
    <div className="app">
      <header className="topbar">
        <span className="brand">VibeEduTwin</span>
      </header>
      <main className="screen">
        {tab === 'home' && <Home go={go} />}
        {tab === 'write' && <Write go={go} />}
        {tab === 'learn' && <Learn go={go} />}
        {tab === 'practice' && <Practice />}
        {tab === 'growth' && <MyGrowth go={go} />}
      </main>
      <BottomNav tab={tab} go={go} />
    </div>
  );
}
