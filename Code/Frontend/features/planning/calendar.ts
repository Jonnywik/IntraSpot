export type CalendarInterval = {
  starts_at: string | null;
  ends_at: string | null;
};

function timestamp(value: string | number | Date | null | undefined): number | null {
  const result = value instanceof Date
    ? value.getTime()
    : typeof value === 'number'
      ? value
      : typeof value === 'string'
        ? Date.parse(value)
        : Number.NaN;
  return Number.isFinite(result) ? result : null;
}

function dateParts(value: Date): {year: number; month: number; day: number} {
  const parts = new Intl.DateTimeFormat('en-CA', {
    timeZone: 'Asia/Manila',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).formatToParts(value);
  const part = (type: string) => parts.find((item) => item.type === type)?.value ?? '';
  return {year: Number(part('year')), month: Number(part('month')), day: Number(part('day'))};
}

function dateKey(year: number, month: number, day: number): string {
  return String(year).padStart(4, '0') + '-' + String(month).padStart(2, '0') + '-' + String(day).padStart(2, '0');
}

function parseDateKey(value: string): {year: number; month: number; day: number} | null {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value);
  if (!match) return null;
  const year = Number(match[1]);
  const month = Number(match[2]);
  const day = Number(match[3]);
  const check = new Date(Date.UTC(year, month - 1, day));
  if (check.getUTCFullYear() !== year || check.getUTCMonth() + 1 !== month || check.getUTCDate() !== day) return null;
  return {year, month, day};
}

export function getManilaDateKey(value: string | number | Date): string | null {
  const time = timestamp(value);
  if (time === null) return null;
  const parts = dateParts(new Date(time));
  return dateKey(parts.year, parts.month, parts.day);
}

export function isValidDateInterval(startsAt: string | null, endsAt: string | null): boolean {
  const start = timestamp(startsAt);
  const end = timestamp(endsAt);
  return start !== null && end !== null && end > start;
}

export function intervalIncludesManilaDay(startsAt: string | null, endsAt: string | null, day: string): boolean {
  if (!isValidDateInterval(startsAt, endsAt)) return false;
  const parts = parseDateKey(day);
  if (!parts) return false;
  const dayStart = Date.parse(day + 'T00:00:00+08:00');
  const dayEnd = dayStart + 24 * 60 * 60 * 1000;
  const start = timestamp(startsAt);
  const end = timestamp(endsAt);
  return start !== null && end !== null && start < dayEnd && dayStart < end;
}

export function eventsForManilaDay<T extends CalendarInterval>(events: readonly T[], day: string): T[] {
  return events.filter((event) => intervalIncludesManilaDay(event.starts_at, event.ends_at, day));
}

export function addManilaDays(day: string, amount: number): string | null {
  const parts = parseDateKey(day);
  if (!parts || !Number.isInteger(amount)) return null;
  const result = new Date(Date.UTC(parts.year, parts.month - 1, parts.day + amount));
  return dateKey(result.getUTCFullYear(), result.getUTCMonth() + 1, result.getUTCDate());
}

export function manilaMonthDays(year: number, month: number): string[] {
  if (!Number.isInteger(year) || year < 1 || year > 9999 || !Number.isInteger(month) || month < 1 || month > 12) return [];
  const first = new Date(Date.UTC(year, month - 1, 1));
  const offset = first.getUTCDay();
  const monthLength = new Date(Date.UTC(year, month, 0)).getUTCDate();
  const count = Math.ceil((offset + monthLength) / 7) * 7;
  const start = new Date(Date.UTC(year, month - 1, 1 - offset));
  return Array.from({length: count}, (_, index) => {
    const current = new Date(start.getTime() + index * 24 * 60 * 60 * 1000);
    return dateKey(current.getUTCFullYear(), current.getUTCMonth() + 1, current.getUTCDate());
  });
}

export function shiftCalendarMonth(year: number, month: number, amount: number): {year: number; month: number} | null {
  if (!Number.isInteger(year) || year < 1 || year > 9999 || !Number.isInteger(month) || month < 1 || month > 12 || !Number.isInteger(amount)) return null;
  const shifted = new Date(Date.UTC(year, month - 1 + amount, 1));
  return {year: shifted.getUTCFullYear(), month: shifted.getUTCMonth() + 1};
}

export function intervalsOverlap(
  startsA: string | null,
  endsA: string | null,
  startsB: string | null,
  endsB: string | null,
): boolean {
  if (!isValidDateInterval(startsA, endsA) || !isValidDateInterval(startsB, endsB)) return false;
  const startA = timestamp(startsA);
  const endA = timestamp(endsA);
  const startB = timestamp(startsB);
  const endB = timestamp(endsB);
  return startA !== null && endA !== null && startB !== null && endB !== null && startA < endB && startB < endA;
}
