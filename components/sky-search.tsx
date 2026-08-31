'use client';

import { Crosshair, Search, Stars } from 'lucide-react';
import { useState } from 'react';

export function SkySearch() {
  const [ra, setRa] = useState('150.1163');
  const [dec, setDec] = useState('2.2058');
  const [radius, setRadius] = useState('0.2');
  const [searched, setSearched] = useState(false);
  function submit(event: React.SubmitEvent<HTMLFormElement>) { event.preventDefault(); const params = new URLSearchParams({ ra, dec, radius }); window.history.replaceState({}, '', `/sky?${params}`); setSearched(true); }
  return (
    <div className="sky-tool">
      <form className="cone-form" onSubmit={submit}>
        <div><p className="kicker">Cone search</p><h2>Search around a sky coordinate.</h2><p>Prepared for public Roman footprints. Coordinates use decimal degrees in the ICRS reference frame.</p></div>
        <label><span>Right ascension <small>0–360°</small></span><input type="number" min="0" max="360" step="any" required value={ra} onChange={(event) => setRa(event.target.value)} /></label>
        <label><span>Declination <small>−90–90°</small></span><input type="number" min="-90" max="90" step="any" required value={dec} onChange={(event) => setDec(event.target.value)} /></label>
        <label><span>Radius <small>0–10°</small></span><input type="number" min="0.001" max="10" step="any" required value={radius} onChange={(event) => setRadius(event.target.value)} /></label>
        <button className="button button-primary" type="submit"><Search aria-hidden="true" /> Search this region</button>
      </form>
      <figure className="sky-map-placeholder"><figcaption className="sr-only">Prepared sky coverage map with no Roman science footprints loaded yet.</figcaption><span className="sky-grid" /><Crosshair aria-hidden="true" /><div><Stars aria-hidden="true" /><strong>{searched ? 'No fixture footprints in this region' : 'Roman footprints will appear here'}</strong><p>{searched ? `Searched RA ${ra}°, Dec ${dec}°, radius ${radius}°.` : 'The map and API query are ready for public observation coordinates.'}</p></div></figure>
    </div>
  );
}
