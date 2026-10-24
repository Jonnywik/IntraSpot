import type { ContentItem } from './types';

/** Refresh private labels without dropping loaded messages or changing bodies. */
export function applyAuthorLabels(items: ContentItem[], labels?: Record<string, string>): ContentItem[] {
  if (labels === undefined) return items;
  return items.map(item => ({
    ...item,
    author_label: item.mine ? 'You' : item.removed || item.locally_hidden
      ? 'PLM member' : labels[item.author_id] ?? 'PLM member',
  }));
}

export function clearAuthorLabels(items: ContentItem[], userId?: string): ContentItem[] {
  return items.map(item => item.mine || userId && item.author_id !== userId
    ? item : { ...item, author_label: 'PLM member' });
}
