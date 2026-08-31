import { surprisePool, type SurpriseMode } from '@/lib/catalog';
import { toApiItem } from '@/lib/api-contract';
const modes = new Set<SurpriseMode>(['anything', 'galaxies', 'mission', 'calm', 'engineering']);
export function GET(request: Request) { const requested = new URL(request.url).searchParams.get('mode') as SurpriseMode | null; const mode = requested && modes.has(requested) ? requested : 'anything'; const pool = surprisePool(mode); return Response.json({ mode, item: toApiItem(pool[Math.floor(Math.random() * pool.length)]) }); }
