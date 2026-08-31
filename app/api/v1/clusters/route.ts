import { clusters, itemsForSlugs } from '@/lib/catalog';
import { toApiCluster } from '@/lib/api-contract';
export function GET() { return Response.json({ data: clusters.map((group) => toApiCluster(group, itemsForSlugs(group.memberSlugs))), next_cursor: null, total_estimate: clusters.length }, { headers: { 'Cache-Control': 'public, max-age=60', 'X-RomanPics-Mode': 'fixture' } }); }
