const dateFormatter = new Intl.DateTimeFormat('en-PH', {timeZone: 'Asia/Manila', dateStyle: 'medium'});
const timeFormatter = new Intl.DateTimeFormat('en-PH', {timeZone: 'Asia/Manila', timeStyle: 'short'});
export const formatDate = (value: string) => dateFormatter.format(new Date(value));
export const formatTime = (value: string) => timeFormatter.format(new Date(value));
export function toUtcFromManila(value: string): string {
  if (!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/.test(value)) throw new Error('Enter a valid Manila date and time.');
  const date = new Date(`${value}:00+08:00`);
  if (!Number.isFinite(date.getTime())) throw new Error('Enter a valid Manila date and time.');
  const utc = date.toISOString();
  if (fromUtcToManila(utc) !== value) throw new Error('Enter a valid Manila date and time.');
  return utc;
}
export function fromUtcToManila(value: string | null | undefined): string {
  if (!value) return '';
  return new Date(new Date(value).getTime() + 8 * 60 * 60 * 1000).toISOString().slice(0, 16);
}
