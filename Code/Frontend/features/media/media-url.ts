const MEDIA_URL = /^\/api\/v1\/media\/([0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12})$/i;

export function mediaApiPath(mediaUrl: string): string | null {
  const match = MEDIA_URL.exec(mediaUrl);
  return match && match[0] === mediaUrl ? `/media/${match[1]}` : null;
}
