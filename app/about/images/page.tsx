import type { Metadata } from 'next';
import { ArrowUpRight, Eye, FileCheck2, Layers3, Palette, ShieldCheck } from 'lucide-react';
import Link from 'next/link';
import { PageIntro } from '@/components/page-intro';

export const metadata: Metadata = { title: 'About the images', description: 'Understand Roman imagery, simulations, infrared color, provenance, and rights.' };
const classes = [
  ['Flight science', 'Light captured by Roman in space and released through an authoritative public archive.'],
  ['Simulation', 'A calculated preview of possible observations or physical scenarios—not captured by Roman.'],
  ['Ground test', 'The telescope, instruments, teams, or test data created before or during commissioning.'],
  ['Mission photo', 'Documentary photography of the people, launch, spacecraft, and mission activities.'],
  ['Visualization', 'An artist concept, trajectory, scale comparison, animation, or other explanatory media.'],
];
export default function AboutImagesPage() {
  return (
    <main id="main-content" className="shell">
      <PageIntro kicker="Read every picture honestly" title="Beauty is better with context."><p>RomanPics is a discovery layer, not an archive. We make public imagery welcoming while preserving what it is, who made it, how it was processed, and where the authoritative original lives.</p></PageIntro>
      <section className="about-principles"><article><FileCheck2 aria-hidden="true" /><h2>Authoritative originals</h2><p>Every card links outward. RomanPics indexes metadata and official renditions; it does not quietly become the source of record.</p></article><article><ShieldCheck aria-hidden="true" /><h2>Visible provenance</h2><p>Credit, rights, classification, dates, upstream identity, and technical products stay attached through search and sharing.</p></article><article><Eye aria-hidden="true" /><h2>Accessible meaning</h2><p>Alt text, semantic controls, plain language, and non-color labels make the catalog useful beyond a purely visual browse.</p></article></section>
      <section className="class-guide"><div><p className="kicker">A label on every card</p><h2>Observed, simulated, photographed, or illustrated?</h2><p>Launch-era galleries naturally contain all four. Clear classification prevents a spectacular simulation from being mistaken for a science result.</p></div><dl>{classes.map(([term, definition]) => <div key={term}><dt>{term}</dt><dd>{definition}</dd></div>)}</dl></section>
      <section className="infrared-explainer"><div><Palette aria-hidden="true" /><p className="kicker">Infrared color</p><h2>The camera measures light; people design a translation.</h2><p>Infrared wavelengths are outside human vision. Processors assign filters to visible channels and stretch brightness so structure becomes legible. That color can be scientifically meaningful without pretending it is what unaided eyes would see.</p><Link className="button button-primary" href="/tools/color">Try the color composer</Link></div><div className="wavelength"><span>Shorter wavelength</span><div><i /><i /><i /><i /><i /></div><span>Longer wavelength</span></div></section>
      <section className="about-similarity"><Layers3 aria-hidden="true" /><div><p className="kicker">Similarity, without mystery</p><h2>Why is this picture in that group?</h2><p>RomanPics first uses trusted relationships—same observation, target, sky cell, visit, or filter stack—then duplicate checks and versioned visual or semantic embeddings. Every group exposes a plain-language reason, and votes never silently move when a cluster changes.</p><Link className="text-link" href="/groups">Explore similarity groups</Link></div></section>
      <section className="source-links"><h2>Go deeper at the source</h2><a href="https://images.nasa.gov" target="_blank" rel="noreferrer">NASA Image and Video Library <ArrowUpRight aria-hidden="true" /></a><a href="https://svs.gsfc.nasa.gov" target="_blank" rel="noreferrer">NASA Scientific Visualization Studio <ArrowUpRight aria-hidden="true" /></a><a href="https://archive.stsci.edu/missions-and-data/roman" target="_blank" rel="noreferrer">MAST Roman archive <ArrowUpRight aria-hidden="true" /></a><a href="https://irsa.ipac.caltech.edu/Missions/roman.html" target="_blank" rel="noreferrer">IPAC / IRSA Roman resources <ArrowUpRight aria-hidden="true" /></a></section>
    </main>
  );
}
