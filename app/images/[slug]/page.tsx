import type { Metadata } from 'next';
import Link from 'next/link';
import { notFound } from 'next/navigation';
import { ArrowLeft, ArrowUpRight, Database, FileImage, Info, Link as LinkIcon, Orbit } from 'lucide-react';
import { CatalogCard } from '@/components/catalog-card';
import { ContentLabel } from '@/components/content-label';
import { ShareButton } from '@/components/share-button';
import { VoteButton } from '@/components/vote-button';
import { listSimilarItems, readItem, readItemClusters } from '@/lib/api';
import { catalog } from '@/lib/catalog';

type Props = { params: Promise<{ slug: string }> };

export function generateStaticParams() {
  return catalog.map((item) => ({ slug: item.slug }));
}

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const item = await readItem((await params).slug);
  if (!item) return { title: 'Picture not found' };
  return {
    title: item.title,
    description: item.summary,
    alternates: { canonical: `/images/${item.slug}` },
    openGraph: {
      title: `${item.title} · RomanPics`,
      description: `${item.contentLabel}: ${item.summary}`,
      type: 'article',
      publishedTime: item.publishedAt,
      images: [{ url: item.image, alt: item.alt }],
    },
    twitter: { card: 'summary_large_image', title: item.title, description: item.summary, images: [item.image] },
  };
}

export default async function ItemPage({ params }: Props) {
  const item = await readItem((await params).slug);
  if (!item) notFound();
  const [related, groups] = await Promise.all([
    listSimilarItems(item.slug, item.relatedSlugs),
    readItemClusters(item),
  ]);
  const structuredData = {
    '@context': 'https://schema.org',
    '@type': 'ImageObject',
    name: item.title,
    caption: item.summary,
    description: item.alt,
    contentUrl: item.originalUrl,
    thumbnailUrl: item.thumbnail,
    creditText: item.credit,
    acquireLicensePage: item.rightsUrl ?? item.sourceUrl,
    isBasedOn: item.sourceUrl,
    datePublished: item.publishedAt,
  };

  return (
    <main id="main-content" className="shell detail-main">
      <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify(structuredData).replaceAll('<', '\\u003c') }} />
      <Link className="back-link" href="/"><ArrowLeft aria-hidden="true" /> Back to explore</Link>
      <article>
        <header className="item-header">
          <div>
            <ContentLabel contentClass={item.contentClass} label={item.contentLabel} />
            <p className="item-eyebrow">{item.eyebrow}</p>
            <h1>{item.title}</h1>
            <p>{item.summary}</p>
          </div>
          <div className="item-actions">
            <VoteButton id={item.id} kind="items" initialVotes={item.votes} initialActive={item.viewerHasVoted} />
            <ShareButton title={item.title} text={item.summary} />
          </div>
        </header>

        <figure className="detail-figure">
          <a href={item.originalUrl} target="_blank" rel="noreferrer">
            <img src={item.image} alt={item.alt} />
            <span><ArrowUpRight aria-hidden="true" /> Open provider-hosted image</span>
          </a>
          <figcaption><strong>{item.alt}</strong><span>Credit: {item.credit}</span></figcaption>
        </figure>

        <div className="detail-grid">
          <section className="detail-story">
            <p className="kicker">Why this is here</p>
            <h2>A beautiful image, with its context intact.</h2>
            <p>{item.summary}</p>
            {!item.isFlightData && (
              <div className="explain-callout">
                <Info aria-hidden="true" />
                <div><strong>This is {item.contentLabel.toLowerCase()}, not Roman flight science.</strong><p>RomanPics keeps simulations, visualizations, ground imagery, and future observations visibly distinct.</p></div>
              </div>
            )}

            {groups.length > 0 && (
              <div className="detail-groups">
                <h3>Found in {groups.length === 1 ? 'this similarity group' : 'these similarity groups'}</h3>
                {groups.map((group) => (
                  <Link href={`/groups/${group.slug}`} key={group.id}><Orbit aria-hidden="true" /><span><strong>{group.title}</strong><small>{group.summary}</small></span><ArrowUpRight aria-hidden="true" /></Link>
                ))}
              </div>
            )}
          </section>

          <aside className="provenance-panel">
            <div className="panel-heading"><Database aria-hidden="true" /><div><p className="kicker">Provenance</p><h2>Trace it to the source</h2></div></div>
            <dl>
              {item.provenance.map((event) => <div key={`${event.label}-${event.detail}`}><dt>{event.label}</dt><dd>{event.detail}</dd></div>)}
              <div><dt>Credit</dt><dd>{item.credit}</dd></div>
              <div><dt>Rights</dt><dd>{item.rights}{item.rightsUrl && <> <a href={item.rightsUrl} target="_blank" rel="noreferrer">Guidelines <ArrowUpRight aria-hidden="true" /></a></>}</dd></div>
            </dl>
            <div className="provenance-actions">
              <a className="button button-primary" href={item.sourceUrl} target="_blank" rel="noreferrer"><LinkIcon aria-hidden="true" /> View source record</a>
              <a className="button button-secondary" href={item.originalUrl} target="_blank" rel="noreferrer"><FileImage aria-hidden="true" /> View original</a>
            </div>
          </aside>
        </div>

        <section className="technical-section">
          <details>
            <summary><span><Database aria-hidden="true" /><strong>Technical details and upstream products</strong></span><small>{item.products.length} linked {item.products.length === 1 ? 'record' : 'records'}</small></summary>
            <div className="technical-content">
              <dl className="technical-facts">
                {item.target && <div><dt>Target</dt><dd>{item.target}</dd></div>}
                {item.instrument && <div><dt>Instrument</dt><dd>{item.instrument}</dd></div>}
                {item.survey && <div><dt>Survey</dt><dd>{item.survey}</dd></div>}
                {item.opticalElements && <div><dt>Filters / optical elements</dt><dd>{item.opticalElements.join(', ')}</dd></div>}
                <div><dt>Flight data</dt><dd>{item.isFlightData ? 'Yes' : 'No'}</dd></div>
                <div><dt>Published</dt><dd>{new Date(item.publishedAt).toLocaleDateString()}</dd></div>
              </dl>
              <div className="product-list">
                {item.products.map((product) => (
                  <a href={product.url} target="_blank" rel="noreferrer" key={product.id}>
                    <FileImage aria-hidden="true" /><span><strong>{product.label}</strong><small>{product.mediaType}{product.dataLevel ? ` · ${product.dataLevel}` : ''} · {product.note}</small></span><ArrowUpRight aria-hidden="true" />
                  </a>
                ))}
              </div>
            </div>
          </details>
        </section>
      </article>

      {related.length > 0 && (
        <section className="related-section">
          <div className="section-heading"><p className="kicker">Keep exploring</p><h2>More like this</h2><p>Related through trusted tags, mission context, or a shared visual neighborhood.</p></div>
          <div className="catalog-grid">{related.map((relatedItem) => <CatalogCard item={relatedItem} key={relatedItem.id} />)}</div>
        </section>
      )}
    </main>
  );
}
