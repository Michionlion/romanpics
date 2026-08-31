import type { Metadata } from 'next';
import { ArrowUpRight, CheckCircle2, Clock3, FlaskConical, Radio, ServerCog } from 'lucide-react';
import { PageIntro } from '@/components/page-intro';
import { readSourceStatus } from '@/lib/api';

export const metadata: Metadata = { title: 'Source status', description: 'Freshness and planned ingestion paths for RomanPics data sources.' };

export default async function StatusPage() {
  const { data: sourceStatuses, transport } = await readSourceStatus();
  const apiConnected = transport === 'api';
  const activeRecords = sourceStatuses.reduce((sum, source) => sum + source.records, 0);
  return (
    <main id="main-content" className="shell">
      <PageIntro kicker="Open operations" title="Know where every picture came from.">
        <p>{apiConnected ? 'RomanPics is reading source freshness from the connected catalog API.' : 'RomanPics is showing fixture-backed source readiness because the catalog API is unavailable or not configured.'}</p>
      </PageIntro>
      <section className="status-summary">
        <div><Radio aria-hidden="true" /><span><strong>{apiConnected ? 'API connected' : 'Fixture mode'}</strong><small>{apiConnected ? 'Live catalog status' : 'Checked-in readiness data'}</small></span></div>
        <div><ServerCog aria-hidden="true" /><span><strong>{activeRecords} records</strong><small>Linked, never mirrored</small></span></div>
        <div><Clock3 aria-hidden="true" /><span><strong>6-hour target</strong><small>Production media cadence</small></span></div>
      </section>
      <div className="status-notice"><FlaskConical aria-hidden="true" /><p><strong>{apiConnected ? 'Operational status is connected.' : 'This is a readiness screen.'}</strong> {apiConnected ? 'Adapter state and timestamps below come from ingest-run records; checked-in catalog records remain clearly identified.' : 'Dates below demonstrate the live UI contract. Configure the API to populate adapter health and degraded-state messages.'}</p></div>
      <section className="source-list" aria-label="Source adapters">
        {sourceStatuses.map((source) => (
          <article key={source.id}>
            <div className={`source-state ${source.state}`}><CheckCircle2 aria-hidden="true" /><span>{source.statusLabel}</span></div>
            <div className="source-copy"><p className="kicker">{source.purpose}</p><h2>{source.name}</h2><p>{source.note}</p></div>
            <dl><div><dt>Indexed records</dt><dd>{source.records}</dd></div><div><dt>Target cadence</dt><dd>{source.cadence}</dd></div><div><dt>Last success</dt><dd>{source.lastSuccessAt ? new Date(source.lastSuccessAt).toLocaleString() : 'Not started'}</dd></div></dl>
            <a className="text-link" href={source.canonicalUrl} target="_blank" rel="noreferrer">Open source <ArrowUpRight aria-hidden="true" /></a>
          </article>
        ))}
      </section>
    </main>
  );
}
