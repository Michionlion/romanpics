'use client';

import { Columns2, Eye, FlipHorizontal2 } from 'lucide-react';
import { useState } from 'react';

const sourceImage = 'https://svs.gsfc.nasa.gov/vis/a010000/a013900/a013921/DREaM_Roman_15_Percent_print.jpg';

export function ImageComparison() {
  const [position, setPosition] = useState(50);
  const [swapped, setSwapped] = useState(false);
  const left = swapped ? 'Longer wavelength assignment' : 'Shorter wavelength assignment';
  const right = swapped ? 'Shorter wavelength assignment' : 'Longer wavelength assignment';
  return (
    <div className="comparison-tool">
      <div className={`comparison-frame ${swapped ? 'swapped' : ''}`}>
        <img className="comparison-base" src={sourceImage} alt={`${left}: a conceptual filtered rendition of the same simulated deep field.`} />
        <div className="comparison-reveal" style={{ width: `${position}%` }}><img src={sourceImage} alt={`${right}: a conceptual filtered rendition of the same simulated deep field.`} /></div>
        <div className="comparison-line" style={{ left: `${position}%` }} aria-hidden="true"><Columns2 /></div>
        <span className="comparison-label left">{left}</span><span className="comparison-label right">{right}</span>
      </div>
      <label className="range-control"><span>Show {right}</span><input type="range" min="0" max="100" value={position} onChange={(event) => setPosition(Number(event.target.value))} aria-valuetext={`${position}% ${right}`} /><output>{position}%</output></label>
      <div className="comparison-actions"><button className="button button-secondary" type="button" onClick={() => setSwapped((value) => !value)}><FlipHorizontal2 aria-hidden="true" /> Swap sides</button><p><Eye aria-hidden="true" /> The slider, labels, and text convey the comparison without relying on color alone.</p></div>
    </div>
  );
}
