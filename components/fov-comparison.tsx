'use client';

import { Check, Maximize2 } from 'lucide-react';
import { useState } from 'react';

const instruments = [
  { id: 'hubble', name: 'Hubble WFC3/UVIS', width: '9%', height: '9%', area: 'about 7.3 arcmin²', color: '#8ca1ff' },
  { id: 'webb', name: 'Webb NIRCam', width: '15%', height: '24%', area: 'about 9.7 arcmin² across two modules', color: '#f0a88a' },
  { id: 'roman', name: 'Roman WFI', width: '78%', height: '73%', area: 'about 0.28 deg²', color: '#f5d68a' },
];

export function FovComparison() {
  const [visible, setVisible] = useState(() => new Set(instruments.map((item) => item.id)));
  function toggle(id: string) { setVisible((current) => { const next = new Set(current); if (next.has(id)) next.delete(id); else next.add(id); return next; }); }
  return (
    <div className="fov-tool">
      <figure className="fov-stage">
        <figcaption className="sr-only">Illustrative nested field sizes. {instruments.filter((item) => visible.has(item.id)).map((item) => `${item.name}: ${item.area}`).join('. ')}</figcaption>
        <span className="fov-stars" aria-hidden="true" />
        {instruments.map((item) => visible.has(item.id) && <div key={item.id} className={`fov-box ${item.id}`} style={{ width: item.width, height: item.height, borderColor: item.color, color: item.color }}><span>{item.name}</span></div>)}
        <span className="not-to-scale"><Maximize2 aria-hidden="true" /> Area-normalized teaching diagram</span>
      </figure>
      <div className="fov-legend">
        {instruments.map((item) => <button key={item.id} type="button" aria-pressed={visible.has(item.id)} onClick={() => toggle(item.id)}><span className="legend-check" style={{ borderColor: item.color, background: visible.has(item.id) ? item.color : 'transparent' }}>{visible.has(item.id) && <Check aria-hidden="true" />}</span><span><strong>{item.name}</strong><small>{item.area}</small></span></button>)}
      </div>
    </div>
  );
}
