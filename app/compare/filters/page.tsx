import type { Metadata } from 'next';
import { Info } from 'lucide-react';
import { ImageComparison } from '@/components/image-comparison';
import { PageIntro } from '@/components/page-intro';

export const metadata: Metadata = { title: 'Compare filters', description: 'An accessible prototype for comparing the same Roman sky region in different filters.' };
export default function FilterComparisonPage() {
  return (
    <main id="main-content" className="shell">
      <PageIntro kicker="Same sky, different light" title="One region can tell many stories."><p>Different filters isolate different ranges of light. Slide between aligned renditions while labels, captions, and keyboard controls keep the comparison understandable.</p></PageIntro>
      <div className="teaching-note"><Info aria-hidden="true" /><p><strong>Interaction prototype:</strong> both sides derive from one official NASA simulation and use conceptual color treatments. Replace the two URLs and labels with aligned WFI cutouts when supported public products arrive.</p></div>
      <ImageComparison />
      <section className="explanation-grid"><article><span>01</span><h2>Align the sky</h2><p>Both images need the same celestial footprint, orientation, and pixel grid before a slider comparison is honest.</p></article><article><span>02</span><h2>Name every filter</h2><p>Plain-language wavelength descriptions sit beside formal filter names; color never carries meaning by itself.</p></article><article><span>03</span><h2>Keep the recipe</h2><p>Each rendition links to its upstream products and documents stretch, channel assignment, and processing.</p></article></section>
    </main>
  );
}
