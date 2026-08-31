import { getCollection, itemsForSlugs } from '@/lib/catalog';
import { toApiItem } from '@/lib/api-contract';
export async function GET(_request: Request, context: { params: Promise<{ slug: string }> }) { const collection = getCollection((await context.params).slug); return collection ? Response.json({ slug: collection.slug, title: collection.title, summary: collection.summary, items: itemsForSlugs(collection.itemSlugs).map((item) => toApiItem(item)) }) : Response.json({ title: 'Not found', status: 404 }, { status: 404 }); }
