'use client';

import { ArrowRight, Shuffle, Sparkles } from 'lucide-react';
import { useState } from 'react';
import { getSurprise } from '@/lib/api';
import type { SurpriseMode } from '@/lib/catalog';

const modes: Array<{ value: SurpriseMode; label: string; hint: string }> = [
  { value: 'anything', label: 'Anything', hint: 'The whole launch-era catalog' },
  { value: 'galaxies', label: 'Galaxies', hint: 'Deep fields and cosmic scale' },
  { value: 'mission', label: 'Mission journey', hint: 'Launch, cruise, and first light' },
  { value: 'engineering', label: 'Engineering', hint: 'Hardware and cleanroom teams' },
  { value: 'calm', label: 'Quiet wonder', hint: 'Stars, space, and slow exploration' },
];

export function SurprisePanel() {
  const [mode, setMode] = useState<SurpriseMode>('anything');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  async function surprise() {
    setBusy(true);
    setError('');
    try {
      const item = await getSurprise(mode);
      window.location.assign(`/images/${item.slug}?from=surprise&mode=${mode}`);
    } catch {
      setError('We could not choose a picture. Please try again.');
    } finally {
      setBusy(false);
    }
  }

  return (
    <aside className="surprise-panel">
      <div className="surprise-icon"><Sparkles aria-hidden="true" /></div>
      <div>
        <p className="kicker">Feeling curious?</p>
        <h2>Surprise me, with a little direction.</h2>
        <p>Choose a mood or subject. We’ll pull one unexpected place to begin.</p>
      </div>
      <label>
        <span>Surprise mode</span>
        <select value={mode} onChange={(event) => setMode(event.target.value as SurpriseMode)}>
          {modes.map((option) => (
            <option key={option.value} value={option.value}>{option.label} — {option.hint}</option>
          ))}
        </select>
      </label>
      <button className="button button-primary" type="button" disabled={busy} onClick={surprise}>
        <Shuffle aria-hidden="true" /> {busy ? 'Choosing…' : 'Take me somewhere'} <ArrowRight aria-hidden="true" />
      </button>
      <output className={error ? 'surprise-error' : 'sr-only'}>{error}</output>
    </aside>
  );
}
