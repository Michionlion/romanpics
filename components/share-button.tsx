'use client';

import { Check, Share2 } from 'lucide-react';
import { useState } from 'react';

export function ShareButton({ title, text }: { title: string; text: string }) {
  const [copied, setCopied] = useState(false);
  const [error, setError] = useState('');
  async function share() {
    setError('');
    try {
      if (navigator.share) {
        await navigator.share({ title, text, url: window.location.href });
        return;
      }
      await navigator.clipboard.writeText(window.location.href);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1800);
    } catch (caught) {
      if (caught instanceof DOMException && caught.name === 'AbortError') return;
      setError('Sharing is unavailable right now.');
    }
  }
  return (
    <span className="share-control">
      <button className="button button-quiet" type="button" onClick={share}>
        {copied ? <Check aria-hidden="true" /> : <Share2 aria-hidden="true" />}
        {copied ? 'Link copied' : 'Share'}
      </button>
      <output className="sr-only">{error}</output>
    </span>
  );
}
