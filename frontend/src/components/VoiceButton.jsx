import { useEffect, useRef, useState } from 'react';
import { api } from '../api.js';

// VoiceButton: push-to-talk mic. Hold "Speak" to stream PCM16 mono 16 kHz
// audio to the backend (/ws/transcribe -> Muse Voice Transcribe); release
// to stop. The final transcript goes to the parent text box for checking.
// If Meta fails, or the learner taps "Wrong transcript?", fall back to the
// browser's built-in speech recognition.
const TARGET_RATE = 16000;

// Downsamples mic float32 to 16-bit PCM at 16 kHz and posts ArrayBuffers.
const WORKLET_SOURCE = `
class MicTap extends AudioWorkletProcessor {
  process(inputs) {
    const channel = inputs[0] && inputs[0][0];
    if (channel) {
      const ratio = sampleRate / ${TARGET_RATE};
      const length = Math.floor(channel.length / ratio);
      const pcm = new Int16Array(length);
      for (let i = 0; i < length; i++) {
        const s = channel[Math.floor(i * ratio)] || 0;
        pcm[i] = s < 0 ? Math.max(-32768, s * 32768) : Math.min(32767, s * 32767);
      }
      this.port.postMessage(pcm.buffer, [pcm.buffer]);
    }
    return true;
  }
}
registerProcessor('mic-tap', MicTap);
`;

export default function VoiceButton({ onTranscript, disabled }) {
  const [mode, setMode] = useState('idle'); // idle | listening | waiting | browser
  const [status, setStatus] = useState('');
  const [metaText, setMetaText] = useState('');
  const [fallback, setFallback] = useState(false);
  const ctl = useRef({
    ws: null, ctx: null, stream: null, node: null, rec: null,
    phase: 'idle', ready: false, released: false, done: false,
    browserLang: 'ml-IN',
  });

  const stopAudio = () => {
    const c = ctl.current;
    try { c.node && c.node.disconnect(); } catch { /* already gone */ }
    try { c.ctx && c.ctx.close(); } catch { /* already gone */ }
    if (c.stream) c.stream.getTracks().forEach((t) => t.stop());
    try { c.ws && c.ws.close(); } catch { /* already gone */ }
    c.ws = null;
    c.ctx = null;
    c.stream = null;
    c.node = null;
    c.ready = false;
  };

  const stopAll = () => {
    const c = ctl.current;
    c.done = true;
    try { c.rec && c.rec.abort(); } catch { /* already gone */ }
    c.rec = null;
    stopAudio();
  };

  useEffect(() => stopAll, []);

  const startBrowser = (lang) => {
    const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
    const c = ctl.current;
    if (!SR) {
      c.phase = 'idle';
      setMode('idle');
      setStatus('Voice input is not available in this browser.');
      return;
    }
    c.phase = 'browser';
    setMode('browser');
    setStatus('Listening with the browser mic…');
    setMetaText('');
    const rec = new SR();
    c.rec = rec;
    rec.lang = lang || 'ml-IN';
    rec.interimResults = false;
    rec.onresult = (e) => {
      const text = (e.results[0][0].transcript || '').trim();
      c.phase = 'idle';
      setMode('idle');
      setStatus('');
      if (text) onTranscript(text, 'browser');
    };
    rec.onerror = () => {
      c.phase = 'idle';
      setMode('idle');
      setStatus('Could not hear that. Try again.');
    };
    try {
      rec.start();
    } catch {
      c.phase = 'idle';
      setMode('idle');
      setStatus('Could not start the mic.');
    }
  };

  const startMeta = async () => {
    const c = ctl.current;
    if (disabled || c.ws || c.phase !== 'idle') return;
    c.done = false;
    c.released = false;
    c.phase = 'listening';
    setMetaText('');
    setFallback(false);
    setMode('listening');
    setStatus('Listening… release to stop.');

    const toBrowser = () => {
      if (c.done) return;
      c.done = true;
      c.phase = 'idle';
      stopAudio();
      startBrowser(c.browserLang);
    };
    const toIdle = (text) => {
      if (c.done) return;
      c.done = true;
      c.phase = 'idle';
      stopAudio();
      setMode('idle');
      setStatus('');
      setFallback(false);
      if (text) {
        setMetaText(text);
        onTranscript(text, 'meta');
      }
    };
    // Meta failed: show the real error and offer the browser mic in one tap.
    const showVoiceError = (text) => {
      if (c.done) return;
      c.done = true;
      c.phase = 'idle';
      stopAudio();
      setMode('idle');
      setStatus(text);
      setMetaText('');
      setFallback(true);
    };

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      if (c.done || c.released) {
        stream.getTracks().forEach((t) => t.stop());
        return;
      }
      c.stream = stream;
      const Ctx = window.AudioContext || window.webkitAudioContext;
      const ctx = new Ctx();
      c.ctx = ctx;
      if (!ctx.audioWorklet) {
        toBrowser();
        return;
      }
      const url = URL.createObjectURL(
        new Blob([WORKLET_SOURCE], { type: 'application/javascript' }));
      await ctx.audioWorklet.addModule(url);
      URL.revokeObjectURL(url);
      const src = ctx.createMediaStreamSource(stream);
      const node = new AudioWorkletNode(ctx, 'mic-tap');
      c.node = node;
      src.connect(node);
      const ws = new WebSocket(api.voiceSocketUrl());
      c.ws = ws;
      ws.binaryType = 'arraybuffer';
      node.port.onmessage = (e) => {
        if (ws.readyState === WebSocket.OPEN && c.ready) ws.send(e.data);
      };
      ws.onmessage = (e) => {
        const msg = JSON.parse(e.data);
        if (msg.type === 'ready') {
          c.browserLang = msg.browserLang || 'ml-IN';
          c.ready = true;
          if (c.released) {
            ws.send(JSON.stringify({ type: 'stop' }));
            c.phase = 'waiting';
            setMode('waiting');
          }
        } else if (msg.type === 'partial') {
          setStatus(msg.text || 'Listening…');
        } else if (msg.type === 'final') {
          toIdle((msg.text || '').trim());
        } else if (msg.type === 'meta_error' || msg.type === 'error') {
          showVoiceError(msg.message || 'Transcription failed. Try again.');
        }
      };
      ws.onerror = () => showVoiceError('Voice connection failed before any transcript.');
      ws.onclose = () => {
        if (!c.done) showVoiceError('Voice connection closed before any transcript.');
      };
    } catch {
      toBrowser();
    }
  };

  const release = () => {
    const c = ctl.current;
    if (c.phase !== 'listening') return;
    c.phase = 'waiting';
    c.released = true;
    setMode('waiting');
    setStatus('Transcribing…');
    if (c.ws && c.ws.readyState === WebSocket.OPEN && c.ready) {
      c.ws.send(JSON.stringify({ type: 'stop' }));
    }
  };

  return (
    <span className="voice">
      <button
        className="btn secondary"
        disabled={disabled || mode === 'waiting' || mode === 'browser'}
        onPointerDown={startMeta}
        onPointerUp={release}
        onPointerLeave={release}
        onPointerCancel={release}
        onContextMenu={(e) => e.preventDefault()}
        aria-label="Speak: hold to talk, release to stop"
        title="Hold to talk, release to stop"
      >
        {mode === 'listening' ? 'Listening…' : mode === 'waiting' ? 'Working…' : 'Speak'}
      </button>
      {metaText && mode === 'idle' && (
        <button className="btn secondary" onClick={() => startBrowser(ctl.current.browserLang)}>
          Wrong transcript?
        </button>
      )}
      {fallback && mode === 'idle' && (
        <button
          className="btn secondary"
          onClick={() => {
            setFallback(false);
            startBrowser(ctl.current.browserLang);
          }}
        >
          Use browser mic instead
        </button>
      )}
      {status && <span className="muted"> {status}</span>}
    </span>
  );
}
