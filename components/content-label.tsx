import type { ContentClass } from '@/lib/catalog';

export function ContentLabel({
  contentClass,
  label,
}: {
  contentClass: ContentClass;
  label: string;
}) {
  return <span className={`content-label content-label-${contentClass}`}>{label}</span>;
}
