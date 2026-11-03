import { useState } from 'react';
import { api } from '../api.js';

// Slide-over chat with the twin. Secondary helper, opened from Write/Practice.
const QUICK = ['Give me a hint', 'Check my first line'];

export default function TwinPanel({ screen, onClose }) {
  const [messages, setMessages] = useState([
    { from: 'twin', text: 'I am your future self. Ask me for a hint - I never give full answers.' },
  ]);
  const [input, setInput] = useState('');
  const [sending, setSending] = useState(false);

  const send = async (text) => {
    const message = (text || '').trim();
    if (!message || sending) return;
    setMessages((m) => [...m, { from: 'me', text: message }]);
    setInput('');
    setSending(true);
    try {
      const res = await api.askTwin(message, screen);
      setMessages((m) => [...m, { from: 'twin', text: res.reply }]);
    } catch (err) {
      setMessages((m) => [...m, { from: 'twin', text: `Hmm, something broke: ${err.message}` }]);
    }
    setSending(false);
  };

  return (
    <>
      <div className="twin-overlay" onClick={onClose} />
      <aside className="twin-panel">
        <div className="twin-head">
          <span>My Twin</span>
          <button className="twin-close" onClick={onClose} aria-label="Close">✕</button>
        </div>
        <div className="twin-messages">
          {messages.map((m, i) => (
            <div className={`msg ${m.from}`} key={i}>{m.text}</div>
          ))}
          {sending && <div className="msg twin">Thinking…</div>}
        </div>
        <div className="twin-chips">
          {QUICK.map((q) => (
            <button key={q} onClick={() => send(q)}>{q}</button>
          ))}
        </div>
        <div className="twin-input">
          <input
            type="text"
            placeholder="Ask for a hint…"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && send(input)}
          />
          <button onClick={() => send(input)} disabled={sending}>Send</button>
        </div>
      </aside>
    </>
  );
}
