import type { Metadata } from 'next';
import Link from 'next/link';
import { ArrowRight, Check, Circle, Orbit, Radio, Rocket, Telescope } from 'lucide-react';
import { PageIntro } from '@/components/page-intro';
import { journey } from '@/lib/catalog';

export const metadata: Metadata = { title: 'Mission journey', description: 'Follow Roman from construction and launch toward commissioning, first images, and science operations.' };

export default function JourneyPage() {
  return (
    <main id="main-content">
      <div className="shell">
        <PageIntro
          kicker="Mission journey"
          title="From a cleanroom to the wide universe."
          actions={<Link className="button button-secondary" href="/status"><Radio aria-hidden="true" /> Source readiness</Link>}
        ><p>A calm, plain-language view of what has happened, what is happening, and when the first real Roman science pictures can enter the catalog.</p></PageIntro>
      </div>
      <section className="journey-hero">
        <div className="shell journey-orbit">
          <div className="earth"><span>Earth</span></div><div className="trajectory"><Rocket aria-hidden="true" /></div><div className="l2"><Orbit aria-hidden="true" /><span>Sun–Earth L2 region</span></div>
        </div>
      </section>
      <section className="shell timeline-section">
        <ol className="timeline">
          {journey.map((milestone) => (
            <li key={milestone.id} className={milestone.state}>
              <div className="timeline-marker">{milestone.state === 'complete' ? <Check aria-hidden="true" /> : milestone.state === 'current' ? <Orbit aria-hidden="true" /> : <Circle aria-hidden="true" />}</div>
              <div className="timeline-date"><small>{milestone.label}</small><strong>{milestone.date}</strong></div>
              <div className="timeline-copy"><h2>{milestone.title}</h2><p>{milestone.description}</p>{milestone.href && <Link className="text-link" href={milestone.href}>Explore this chapter <ArrowRight aria-hidden="true" /></Link>}</div>
            </li>
          ))}
        </ol>
      </section>
      <section className="shell first-light-readiness">
        <Telescope aria-hidden="true" />
        <div><p className="kicker">First-light switchboard</p><h2>Prepared before the first pixels arrive.</h2><p>The production adapter can remain feature-flagged while contract fixtures test new metadata, supersession, prompt products, and preserved releases. When official public previews are verified, one switch enables discovery without redesigning the site.</p></div>
        <Link className="button button-primary" href="/collections/what-roman-may-see">See what Roman may see</Link>
      </section>
    </main>
  );
}
