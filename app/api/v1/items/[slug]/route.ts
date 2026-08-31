import { getItem } from '@/lib/catalog';
import { toApiItem } from '@/lib/api-contract';
export async function GET(_request: Request, context: { params: Promise<{ slug: string }> }) {
  const item = getItem((await context.params).slug);
  return item ? Response.json(toApiItem(item, true)) : Response.json({ title: 'Not found', status: 404 }, { status: 404 });
}
