import type {components} from '@/lib/api.generated';

export type AttendanceOut = components['schemas']['AttendanceOut'];

export type AttendanceAttendee = AttendanceOut['attendees'][number];

export type AttendanceAuditOut = components['schemas']['AttendanceAuditOut'];

export type AttendanceMutationOut = components['schemas']['AttendanceMutationOut'];
export type AttendanceSessionInput = components['schemas']['AttendanceSessionInput'];
export type AttendanceMarkInput = components['schemas']['AttendanceMarkInput'];

export type AttendanceCommandInput = {
  context: object;
  eventId: string;
  token: string;
  kind: 'session' | 'mark';
  registrationId?: string | null;
  value: boolean;
  sessionOpen: boolean;
  version: number;
  clientKey: string;
};

export type AttendanceCommand = {
  context: object;
  eventId: string;
  token: string;
  kind: 'session' | 'mark';
  registrationId: string | null;
  value: boolean;
  sessionOpen: boolean;
  version: number;
  clientKey: string;
  path: string;
  body: AttendanceSessionInput | AttendanceMarkInput;
};
