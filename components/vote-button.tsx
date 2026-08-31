'use client';

import { Heart } from 'lucide-react';
import { useCallback, useState, useSyncExternalStore } from 'react';
import { setVote } from '@/lib/api';

const voteChangeEvent = 'romanpics:vote-change';

export function VoteButton({
  id,
  kind,
  initialVotes,
  initialActive = false,
  compact = false,
}: {
  id: string;
  kind: 'items' | 'clusters';
  initialVotes: number;
  initialActive?: boolean;
  compact?: boolean;
}) {
  const storageKey = `romanpics:vote:${kind}:${id}`;
  const localMode = !process.env.NEXT_PUBLIC_API_BASE;
  const [votes, setVotes] = useState(initialVotes);
  const [apiActive, setApiActive] = useState(initialActive);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  const subscribe = useCallback((notify: () => void) => {
    window.addEventListener('storage', notify);
    window.addEventListener(voteChangeEvent, notify);
    return () => {
      window.removeEventListener('storage', notify);
      window.removeEventListener(voteChangeEvent, notify);
    };
  }, []);
  const getSnapshot = useCallback(
    () => window.localStorage.getItem(storageKey) === '1',
    [storageKey],
  );
  const localActive = useSyncExternalStore(subscribe, getSnapshot, () => initialActive);
  const active = localActive || apiActive;

  function persistActive(next: boolean) {
    if (next) window.localStorage.setItem(storageKey, '1');
    else window.localStorage.removeItem(storageKey);
    window.dispatchEvent(new Event(voteChangeEvent));
    if (!localMode) setApiActive(next);
  }

  async function toggle() {
    if (busy) return;
    const next = !active;
    const previousVotes = votes;
    setError('');
    persistActive(next);
    setVotes((count) => count + (next ? 1 : -1));
    setBusy(true);
    try {
      const result = await setVote(kind, id, next);
      persistActive(result.active);
      setVotes(result.votes);
    } catch {
      persistActive(active);
      setVotes(previousVotes);
      setError('Your vote could not be saved. Please try again.');
    } finally {
      setBusy(false);
    }
  }

  return (
    <span className="vote-control">
      <button
        className={`vote-button ${active ? 'voted' : ''} ${compact ? 'compact' : ''}`}
        type="button"
        aria-pressed={active}
        aria-label={`${active ? 'Remove' : 'Add'} ${kind === 'items' ? 'picture' : 'group'} vote. ${votes} votes${localMode ? ', local demo' : ''}.`}
        disabled={busy}
        onClick={toggle}
        title={localMode ? 'Prototype vote saved in this browser only' : 'Community vote'}
      >
        <Heart aria-hidden="true" fill={active ? 'currentColor' : 'none'} />
        <span>{votes}</span>
        {localMode && !compact && <small>local demo</small>}
      </button>
      <output className={error && !compact ? 'vote-error' : 'sr-only'}>{error}</output>
    </span>
  );
}
