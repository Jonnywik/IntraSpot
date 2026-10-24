export const DESKTOP_ATTENDANCE_QUERY = '(min-width: 768px)';

export function canLoadAttendance({isDesktop, isExpanded, eventId, token}) {
  return isDesktop && isExpanded && Boolean(eventId) && Boolean(token);
}

export function captureAttendanceCommand({context, eventId, token, kind, registrationId = null, value, sessionOpen, version, clientKey}) {
  const session = kind === 'session';
  const path = `/events/${encodeURIComponent(eventId)}/attendance${session
    ? '/session'
    : `/registrations/${encodeURIComponent(registrationId)}`}`;
  const body = session
    ? {is_open: value, version, client_key: clientKey}
    : {attended: value, version, client_key: clientKey};
  return Object.freeze({
    context,
    eventId,
    token,
    kind,
    registrationId,
    value,
    sessionOpen,
    version,
    clientKey,
    path,
    body: Object.freeze(body),
  });
}

export function matchesAttendanceCommand(command, context) {
  return Boolean(command && command.context === context);
}

export function filterAttendanceAttendees(attendees, query) {
  const needle = query.trim().toLocaleLowerCase();
  return needle
    ? attendees.filter(attendee => attendee.participant_label.toLocaleLowerCase().includes(needle))
    : attendees;
}

export function registrationReferenceFromLabel(label) {
  const prefix = 'Registration · ';
  return label.startsWith(prefix) ? label.slice(prefix.length) : label;
}

export function isUncertainAttendanceFailure(status) {
  return status === null || status === 0 || status === 408 || status === 429 || status >= 500;
}
