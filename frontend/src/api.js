// API client for the FastAPI backend (default http://127.0.0.1:8000).
// Override with VITE_API_URL in frontend/.env for another host.

// Demo learner id. Run `python learner_store.py` once to create learner 1.
export const LEARNER_ID = 1;

const API_URL = import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000';

async function request(path, options = {}) {
  let res;
  try {
    res = await fetch(`${API_URL}${path}`, {
      headers: { 'Content-Type': 'application/json' },
      ...options,
    });
  } catch {
    throw new Error('Cannot reach the backend. Start it with: uvicorn main:app');
  }
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    if (res.status === 404 && body.detail === 'Unknown learner_id') {
      throw new Error('Demo learner not found. Run `python learner_store.py` once.');
    }
    throw new Error(body.detail || `Request failed (${res.status})`);
  }
  return res.json();
}

const post = (path, body) =>
  request(path, { method: 'POST', body: JSON.stringify({ learner_id: LEARNER_ID, ...body }) });

export const api = {
  saveDraft: (content) => post('/drafts', { content }),
  diagnose: (draft_id) => post('/diagnose', { draft_id }),
  getPractice: () => request(`/practice?learner_id=${LEARNER_ID}`),
  submitAnswers: (set_id, answers) => post('/practice/answers', { set_id, answers }),
  levelCheck: () => post('/level-check', {}),
  growth: () => request(`/growth?learner_id=${LEARNER_ID}`),
  drafts: () => request(`/drafts?learner_id=${LEARNER_ID}`),
  curriculum: () => request(`/curriculum?learner_id=${LEARNER_ID}`),
  moduleContent: (discipline, module) => request(
    `/curriculum/modules?learner_id=${LEARNER_ID}&discipline=${encodeURIComponent(discipline)}&module=${encodeURIComponent(module)}`
  ),
  scaffoldStart: (discipline, module) => post('/scaffold/start', { discipline, module }),
  scaffoldHelp: (attempt_id, attempt_text) => post('/scaffold/help', { attempt_id, attempt_text }),
  scaffoldShow: (attempt_id) => post('/scaffold/show', { attempt_id }),
  scaffoldSteps: (attempt_id) => post('/scaffold/steps', { attempt_id }),
  scaffoldRewrite: (attempt_id, text) => post('/scaffold/rewrite', { attempt_id, text }),
  independence: () => request(`/independence?learner_id=${LEARNER_ID}`),
  signup: (profile) => request('/learners', { method: 'POST', body: JSON.stringify(profile) }),
  teacherGenerate: (requestText, note) => request('/teacher/practice-sets', {
    method: 'POST', body: JSON.stringify({ request: requestText, note: note || '' }),
  }),
  teacherPublish: (payload) => request('/teacher/publish', {
    method: 'POST', body: JSON.stringify(payload),
  }),
  events: () => request(`/events?learner_id=${LEARNER_ID}`),
  askTwin: (message, screen) => post('/twin/ask', { message, screen }),
  voiceSocketUrl: (learnerId) =>
    `${API_URL.replace(/^http/, 'ws')}/ws/transcribe?learner_id=${learnerId || LEARNER_ID}`,
};

// Growth chart unlocks only after the first real level-up.
const FLAG = 'vibe_leveled_up';
export const LeveledUp = {
  get: () => localStorage.getItem(FLAG) === '1',
  set: () => localStorage.setItem(FLAG, '1'),
};
