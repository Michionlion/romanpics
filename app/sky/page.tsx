import type { Metadata } from 'next';
import { PageIntro } from '@/components/page-intro';
import { SkySearch } from '@/components/sky-search';

export const metadata: Metadata = { title: 'Search the sky', description: 'A prepared coordinate and coverage search for future public Roman observations.' };
export default function SkyPage() {
  return (
    <main id="main-content" className="shell">
      <PageIntro kicker="Prepared for science operations" title="Find pictures by where Roman looked."><p>Search by right ascension, declination, and radius. Today this is a transparent empty-state prototype; later it can query indexed HEALPix cells and render public observation footprints.</p></PageIntro>
      <SkySearch />
    </main>
  );
}
