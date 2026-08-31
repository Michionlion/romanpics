import type { Metadata } from 'next';
import { ArrowRight, Palette } from 'lucide-react';
import Link from 'next/link';
import { ColorComposer } from '@/components/color-composer';
import { PageIntro } from '@/components/page-intro';

export const metadata: Metadata = { title: 'Infrared color composer', description: 'Learn how invisible infrared filters can be assigned to visible red, green, and blue channels.' };
export default function ColorComposerPage() {
  return (
    <main id="main-content" className="shell">
      <PageIntro kicker="Interactive explainer" title="Infrared color is a translation."><p>Roman sees wavelengths our eyes cannot. Try a simple channel mix, then learn why a documented “false-color” image can still communicate real structure.</p></PageIntro>
      <ColorComposer />
      <section className="tool-next"><Palette aria-hidden="true" /><div><h2>Color is assigned; structure is measured.</h2><p>A responsible caption explains which filters became which colors, how brightness was stretched, and whether the view is observed, simulated, or composited.</p></div><Link className="text-link" href="/about/images">Learn how Roman images work <ArrowRight aria-hidden="true" /></Link></section>
    </main>
  );
}
