import { useRef, useState } from 'react';
import { api } from '../api.js';

// Shrink a photo under 1 MB in the browser (the photo itself is never stored).
const shrinkImage = (file) => new Promise((resolve, reject) => {
  const url = URL.createObjectURL(file);
  const img = new Image();
  img.onload = () => {
    URL.revokeObjectURL(url);
    const scale = Math.min(1, 1600 / Math.max(img.width, img.height));
    const canvas = document.createElement('canvas');
    canvas.width = Math.round(img.width * scale);
    canvas.height = Math.round(img.height * scale);
    canvas.getContext('2d').drawImage(img, 0, 0, canvas.width, canvas.height);
    let quality = 0.9;
    const attempt = () => {
      canvas.toBlob((blob) => {
        if (!blob) {
          reject(new Error('unreadable'));
          return;
        }
        if (blob.size <= 1000000 || quality <= 0.4) {
          const reader = new FileReader();
          reader.onload = () => resolve(reader.result);
          reader.onerror = () => reject(new Error('unreadable'));
          reader.readAsDataURL(blob);
        } else {
          quality -= 0.15;
          attempt();
        }
      }, 'image/jpeg', quality);
    };
    attempt();
  };
  img.onerror = () => {
    URL.revokeObjectURL(url);
    reject(new Error('unreadable'));
  };
  img.src = url;
});

// ScanButton: photo/upload a handwritten page into any writing box.
// Transcript lands in the box for the learner to check before sending.
export default function ScanButton({ onTranscript, onError, disabled }) {
  const [busy, setBusy] = useState(false);
  const fileRef = useRef(null);

  const scan = async (file) => {
    if (!file || busy) return;
    setBusy(true);
    try {
      const dataUrl = await shrinkImage(file);
      const res = await api.scanPaper(dataUrl);
      if (!res.ok) {
        onError && onError(res.message);
      } else {
        onTranscript(res.text);
      }
    } catch {
      onError && onError('Please type your paragraph.');
    }
    setBusy(false);
    if (fileRef.current) fileRef.current.value = '';
  };

  return (
    <>
      <button
        className="btn secondary"
        onClick={() => fileRef.current && fileRef.current.click()}
        disabled={disabled || busy}
      >
        {busy ? 'Reading…' : 'Scan my paper'}
      </button>
      <input
        ref={fileRef}
        type="file"
        accept="image/jpeg,image/png"
        style={{ display: 'none' }}
        onChange={(e) => scan(e.target.files[0])}
      />
    </>
  );
}
