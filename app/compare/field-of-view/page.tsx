import type { Metadata } from 'next';
import { Info } from 'lucide-react';
import Link from 'next/link';
import { FovComparison } from '@/components/fov-comparison';
import { PageIntro } from '@/components/page-intro';

export const metadata: Metadata = { title: 'Field-of-view comparison', description: 'Compare the panoramic reach of Roman WFI with Hubble and Webb instruments.' };
export default function FieldOfViewPage() {
  return (
    <main id="main-content" className="shell">
      <PageIntro kicker="See the scale" title="Roman was made for the panoramic sky."><p>Hubble and Webb reveal exquisite detail. Roman complements them with a dramatically wider view, making surveys of huge cosmic populations possible.</p></PageIntro>
      <div className="teaching-note"><Info aria-hidden="true" /><p>Instrument footprints vary by detector layout, gaps, orientation, and observing strategy. This area-normalized diagram is explanatory, not an exposure planner.</p></div>
      <FovComparison />
      <section className="comparison-takeaway"><p className="kicker">The useful idea</p><h2>Wide does not mean “better.” It means complementary.</h2><p>Roman can find broad patterns and rare objects across large areas. Hubble and Webb can then study selected targets in extraordinary detail. The observatories answer different parts of the same questions.</p><Link className="button button-secondary" href="/collections/wide-universe">Explore the wide-universe collection</Link></section>
    </main>
  );
}
