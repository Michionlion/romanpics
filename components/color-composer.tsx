'use client';

import { RotateCcw } from 'lucide-react';
import { useState } from 'react';

const source = 'https://svs.gsfc.nasa.gov/vis/a010000/a013900/a013921/DREaM_Roman_15_Percent_print.jpg';
const channels = [
  { id: 'blue', name: 'Short wavelength → blue', color: '#5c7cff' },
  { id: 'green', name: 'Middle wavelength → green', color: '#52e198' },
  { id: 'red', name: 'Long wavelength → red', color: '#ff695f' },
] as const;

export function ColorComposer() {
  const [levels, setLevels] = useState<Record<string, number>>({ blue: 80, green: 58, red: 72 });
  return (
    <div className="composer">
      <figure className="composer-preview">
        <figcaption className="sr-only">Conceptual false-color composite. Blue channel {levels.blue} percent, green {levels.green} percent, red {levels.red} percent.</figcaption>
        {channels.map((channel) => <div className={`composer-layer ${channel.id}`} key={channel.id} style={{ opacity: levels[channel.id] / 100 }}><img src={source} alt="" /></div>)}
        <span>Teaching preview · simulated source</span>
      </figure>
      <div className="composer-controls">
        <div><p className="kicker">Assign light to color</p><h2>Build a visible palette from invisible wavelengths.</h2><p>Infrared light lies beyond human vision. Image processors map different wavelength ranges into colors we can see, then document the recipe.</p></div>
        {channels.map((channel) => <label key={channel.id}><span><i style={{ background: channel.color }} />{channel.name}<output>{levels[channel.id]}%</output></span><input type="range" min="0" max="100" value={levels[channel.id]} onChange={(event) => setLevels((current) => ({ ...current, [channel.id]: Number(event.target.value) }))} /></label>)}
        <button className="button button-quiet" type="button" onClick={() => setLevels({ blue: 80, green: 58, red: 72 })}><RotateCcw aria-hidden="true" /> Reset recipe</button>
        <p className="composer-note">This prototype colorizes one published simulation to teach the interaction. It does not claim to render real WFI filter files.</p>
      </div>
    </div>
  );
}
