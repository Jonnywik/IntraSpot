import type {AttendanceCommand, AttendanceCommandInput, AttendanceAttendee} from './types.js';

export const DESKTOP_ATTENDANCE_QUERY: '(min-width: 768px)';
export function canLoadAttendance(input: {
  isDesktop: boolean;
  isExpanded: boolean;
  eventId: string;
  token: string | null | undefined;
}): boolean;
export function captureAttendanceCommand(input: AttendanceCommandInput): AttendanceCommand;
export function matchesAttendanceCommand(command: AttendanceCommand | null, context: object): boolean;
export function filterAttendanceAttendees<T extends AttendanceAttendee>(attendees: T[], query: string): T[];
export function registrationReferenceFromLabel(label: string): string;
export function isUncertainAttendanceFailure(status: number | null): boolean;
