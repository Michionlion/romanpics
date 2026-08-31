import { collections } from '@/lib/catalog';
export function GET() { return Response.json({ data: collections.map((collection) => ({ slug: collection.slug, title: collection.title, summary: collection.summary, item_count: collection.itemSlugs.length, updated_at: collection.updatedAt })) }, { headers: { 'Cache-Control': 'public, max-age=300', 'X-RomanPics-Mode': 'fixture' } }); }
