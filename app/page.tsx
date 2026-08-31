import { ArrowRight, Images, Layers3, Orbit, Palette, ScanSearch, Telescope } from 'lucide-react';
import Link from 'next/link';
import { ExploreClient } from '@/components/explore-client';
import { SurprisePanel } from '@/components/surprise-panel';
import { listClusters, listItems } from '@/lib/api';
import { collections, contentClassOptions } from '@/lib/catalog';

type SearchParams = Record<string, string | string[] | undefined>;

function one(value: string | string[] | undefined) {
  return Array.isArray(value) ? value[0] : value;
}

export default async function Home({ searchParams }: { searchParams: Promise<SearchParams> }) {
  const params = await searchParams;
  const requestedSort = one(params.sort);
  const sort = ['top', 'trending', 'newest', 'relevance'].includes(requestedSort ?? '')
    ? (requestedSort as 'top' | 'trending' | 'newest' | 'relevance')
    : 'newest';
  const page = Math.max(1, Number.parseInt(one(params.page) ?? '1', 10) || 1);
  const requestedType = one(params.type) ?? 'all';
  const contentClass = contentClassOptions.some((option) => option.value === requestedType)
    ? requestedType
    : 'all';
  const q = one(params.q) ?? '';
  const cursor = one(params.cursor);
  const initialQuery = { q, contentClass, sort, page, limit: 6, cursor };
  const [initialPage, homeClusters] = await Promise.all([
    listItems(initialQuery),
    listClusters(),
  ]);

  return (
    <main id="main-content">
      <section className="hero shell">
        <div className="hero-copy">
          <p className="mission-note"><span /> Launch-era catalog · Science imagery coming later</p>
          <p className="kicker">NASA’s next great observatory</p>
          <h1>The wide universe,<br /><em>easy to explore.</em></h1>
          <p className="hero-lede">Find beautiful Roman imagery without learning an archive. See what is observed, simulated, photographed, or illustrated—and always reach the authoritative original.</p>
          <div className="hero-actions">
            <a className="button button-primary" href="#explore"><ScanSearch aria-hidden="true" /> Explore pictures</a>
            <Link className="button button-secondary" href="/journey"><Orbit aria-hidden="true" /> Follow the mission</Link>
          </div>
          <dl className="hero-stats">
            <div><dt>{initialPage.meta.total}</dt><dd>discoverable catalog records</dd></div>
            <div><dt>0</dt><dd>originals copied or hosted</dd></div>
            <div><dt>4</dt><dd>authoritative source paths planned</dd></div>
          </dl>
        </div>
        <div className="hero-visual">
          <Link href="/images/simulated-ultra-deep-field" className="hero-image">
            <img src="https://svs.gsfc.nasa.gov/vis/a010000/a013900/a013921/DREaM_Roman_15_Percent_print.jpg" alt="A simulated deep field filled with distant galaxies." />
            <span className="content-label content-label-simulation">Simulation</span>
            <span className="hero-image-caption"><strong>A window into the early universe</strong><small>NASA GSFC / DREaM team</small></span>
          </Link>
          <div className="orbit-line" aria-hidden="true"><span /></div>
          <span className="hero-wide-note"><Images aria-hidden="true" /> Built to reveal the panoramic sky</span>
        </div>
      </section>

      <section className="quick-paths shell" aria-label="Ways to explore">
        <Link href="/groups"><Layers3 aria-hidden="true" /><span><strong>Similarity groups</strong><small>Vote on visual neighborhoods</small></span><ArrowRight aria-hidden="true" /></Link>
        <Link href="/compare/field-of-view"><Telescope aria-hidden="true" /><span><strong>See Roman’s scale</strong><small>Compare Hubble, Webb, and Roman</small></span><ArrowRight aria-hidden="true" /></Link>
        <Link href="/tools/color"><Palette aria-hidden="true" /><span><strong>Compose infrared color</strong><small>Assign filters to visible channels</small></span><ArrowRight aria-hidden="true" /></Link>
      </section>

      <div className="shell">
        <ExploreClient initial={{ q, contentClass, sort, page, cursor }} initialPage={initialPage} />
      </div>

      <section className="feature-band">
        <div className="shell">
          <div className="section-heading split-heading">
            <div><p className="kicker">Browse together</p><h2>Pictures find their neighborhoods.</h2></div>
            <Link className="text-link" href="/groups">See every similarity group <ArrowRight aria-hidden="true" /></Link>
          </div>
          <div className="group-preview-grid">
            {homeClusters.slice(0, 3).map((group) => (
              <Link className="group-preview" href={`/groups/${group.slug}`} key={group.id}>
                <span className="group-stack">
                  {group.memberSlugs.slice(0, 2).map((slug, index) => {
                    const collection = collections.flatMap((item) => item.itemSlugs).includes(slug);
                    return <span key={slug} style={{ '--i': index } as React.CSSProperties} className={collection ? 'stack-card warm' : 'stack-card'} />;
                  })}
                  <Layers3 aria-hidden="true" />
                </span>
                <span><strong>{group.title}</strong><small>{group.memberSlugs.length} pictures · {group.votes} group votes</small></span>
                <ArrowRight aria-hidden="true" />
              </Link>
            ))}
          </div>
        </div>
      </section>

      <section className="shell surprise-wrap"><SurprisePanel /></section>
    </main>
  );
}
