import type { Metadata } from 'next';
import Link from 'next/link';
import { notFound } from 'next/navigation';
import { ArrowLeft, Award, GitBranch, Layers3 } from 'lucide-react';
import { CatalogCard } from '@/components/catalog-card';
import { VoteButton } from '@/components/vote-button';
import { readCluster } from '@/lib/api';
import { clusters, getItem } from '@/lib/catalog';

type Props = { params: Promise<{ slug: string }> };
export function generateStaticParams() { return clusters.map((group) => ({ slug: group.slug })); }
export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const result = await readCluster((await params).slug);
  return result ? { title: result.cluster.title, description: result.cluster.summary } : { title: 'Group not found' };
}

export default async function GroupPage({ params }: Props) {
  const result = await readCluster((await params).slug);
  if (!result) notFound();
  const { cluster: group, items: members } = result;
  const representative = members.find((item) => item.slug === group.representativeSlug) ?? getItem(group.representativeSlug);
  return (
    <main id="main-content" className="shell detail-main">
      <Link className="back-link" href="/groups"><ArrowLeft aria-hidden="true" /> All groups</Link>
      <header className="group-detail-header">
        <div><p className="kicker">Similarity neighborhood · {members.length} pictures</p><h1>{group.title}</h1><p>{group.summary}</p><div className="tag-row">{group.tags.map((tag) => <span key={tag}>{tag}</span>)}</div></div>
        <VoteButton id={group.id} kind="clusters" initialVotes={group.votes} initialActive={group.viewerHasVoted} />
      </header>
      <section className="group-reason">
        <GitBranch aria-hidden="true" />
        <div><p className="kicker">Why these are together</p><h2>An explainable group</h2><p>{group.rationale}</p><small>Grouping version: {group.algorithmVersion}. Fixture groups are editorial previews; production groups will preserve stable IDs across recomputation.</small></div>
      </section>
      {representative && (
        <section className="representative">
          <div className="representative-copy"><Award aria-hidden="true" /><p className="kicker">Community representative</p><h2>{representative.title}</h2><p>The most-upvoted picture becomes the cover without changing the group’s own vote total.</p><Link className="text-link" href={`/images/${representative.slug}`}>Open representative picture</Link></div>
          <img src={representative.thumbnail} alt={representative.alt} />
        </section>
      )}
      <section className="group-members"><div className="section-heading"><p className="kicker"><Layers3 aria-hidden="true" /> Group members</p><h2>Vote for a favorite inside the group.</h2></div><div className="catalog-grid">{members.map((item) => <CatalogCard key={item.id} item={item} />)}</div></section>
    </main>
  );
}
