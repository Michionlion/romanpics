import { queryCatalog } from '@/lib/catalog';
import { toApiItem } from '@/lib/api-contract';

export function GET(request: Request) {
  const url = new URL(request.url);
  const apiClass = url.searchParams.get('content_class');
  const classMap: Record<string, string> = { FLIGHT_SCIENCE: 'flight-science', SIMULATION: 'simulation', GROUND_TEST: 'telescope', MISSION_PHOTO: 'mission-photo', VISUALIZATION: 'visualization' };
  const cursor = url.searchParams.get('cursor');
  const cursorPage = cursor?.startsWith('fixture:') ? Number(cursor.slice('fixture:'.length)) : 1;
  const result = queryCatalog({
    q: url.searchParams.get('q') ?? '',
    contentClass: apiClass ? (classMap[apiClass] ?? apiClass) : 'all',
    sort: (url.searchParams.get('sort') as 'top' | 'trending' | 'newest' | 'relevance' | null) ?? 'newest',
    page: Number.isSafeInteger(cursorPage) && cursorPage > 0 ? cursorPage : 1,
    limit: Number(url.searchParams.get('limit') ?? 6),
  });
  const nextCursor = result.meta.page < result.meta.totalPages ? `fixture:${result.meta.page + 1}` : null;
  return Response.json({ data: result.data.map((item) => toApiItem(item)), next_cursor: nextCursor, total_estimate: result.meta.total }, { headers: { 'Cache-Control': 'public, max-age=60', 'X-RomanPics-Mode': 'fixture' } });
}
