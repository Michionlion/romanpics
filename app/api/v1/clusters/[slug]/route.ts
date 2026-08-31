import { getCluster, itemsForSlugs } from '@/lib/catalog';
import { toApiCluster } from '@/lib/api-contract';
export async function GET(_request: Request, context: { params: Promise<{ slug: string }> }) { const cluster = getCluster((await context.params).slug); return cluster ? Response.json(toApiCluster(cluster, itemsForSlugs(cluster.memberSlugs), true)) : Response.json({ title: 'Not found', status: 404 }, { status: 404 }); }
