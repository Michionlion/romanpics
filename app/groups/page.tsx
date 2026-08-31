import type { Metadata } from 'next';
import { GroupBrowser } from '@/components/group-browser';
import { PageIntro } from '@/components/page-intro';
import { listClusters } from '@/lib/api';

export const metadata: Metadata = { title: 'Similarity groups', description: 'Explore and vote for understandable neighborhoods of related Roman imagery.' };

export default async function GroupsPage() {
  const groups = await listClusters();
  return (
    <main id="main-content" className="shell">
      <PageIntro kicker="Community discovery" title="Pictures that belong together.">
        <p>Groups bring near-duplicates, related mission moments, and visually similar images into stable neighborhoods. Vote for a whole group—or for the best picture inside it.</p>
      </PageIntro>
      <div className="group-explainer"><strong>How groups work</strong><span>Shared observation metadata</span><span>Duplicate checks</span><span>Visual + semantic similarity</span><span>Human-readable explanations</span></div>
      <GroupBrowser groups={groups} />
    </main>
  );
}
