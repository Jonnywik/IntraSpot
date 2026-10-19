export function eventChatAvailable(status: string, endsAt: string | null, now: number | null): boolean {
  if (status !== 'confirmed' || !endsAt || now === null) return false;
  const retentionEnd = Date.parse(endsAt) + 72 * 60 * 60 * 1000;
  return Number.isFinite(retentionEnd) && now < retentionEnd;
}
