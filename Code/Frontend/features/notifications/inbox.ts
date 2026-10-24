import type { Actor, Notification } from '@/lib/types';

export type NotificationCategory = 'registrations' | 'clubs' | 'chat' | 'safety';

export type NotificationDestination = {
  href: string;
  label: string;
};

const STAFF_ROLES = new Set(['owner', 'admin', 'moderator']);
const REVIEW_WARNING_MESSAGE = 'A registration assigned to you still awaits review during its extension window.';

export function notificationCategory(kind: string): NotificationCategory {
  if (kind === 'membership_attendance_ended') return 'registrations';
  if (kind.startsWith('membership')) return 'clubs';
  if (kind.startsWith('ownership_transfer_')) return 'clubs';
  if (kind === 'chat_message') return 'chat';
  if (kind.startsWith('report') || kind.startsWith('personal') || kind.startsWith('safety')) return 'safety';
  return 'registrations';
}

function hasStaffGrant(actor: Actor | null, orgId?: string | null) {
  return actor?.grants.some(grant => STAFF_ROLES.has(grant.role)
    && (orgId == null || grant.org_id === orgId)) ?? false;
}

function eventHref(eventId: string) {
  return `/events?eventId=${encodeURIComponent(eventId)}`;
}

function organizationHref(orgId: string) {
  return `/organizations?orgId=${encodeURIComponent(orgId)}`;
}

function workspaceHref(orgId?: string | null, eventId?: string | null) {
  if (!orgId) return '/workspace';

  const params = new URLSearchParams({ orgId });
  if (eventId) params.set('eventId', eventId);
  return `/workspace?${params.toString()}`;
}

function isStaffRegistrationReview(notice: Notification) {
  return notice.kind === 'registration_review_requested'
    || (notice.kind === 'registration_review_warning' && notice.message === REVIEW_WARNING_MESSAGE);
}

export function notificationDestination(
  notice: Notification,
  actor: Actor | null,
): NotificationDestination | null {
  if (notificationCategory(notice.kind) === 'safety') {
    if (actor?.platform_admin) return { href: '/admin', label: 'Open safety review' };
    if (hasStaffGrant(actor, notice.org_id)) {
      return {
        href: workspaceHref(notice.org_id, notice.event_id),
        label: 'Open organization workspace',
      };
    }
    if (notice.event_id) return { href: eventHref(notice.event_id), label: 'View event' };
    if (notice.org_id) return { href: organizationHref(notice.org_id), label: 'View club' };
    return null;
  }

  if (notice.kind === 'membership_attendance_ended') {
    if (notice.event_id) return { href: eventHref(notice.event_id), label: 'View event' };
    if (notice.org_id) return { href: organizationHref(notice.org_id), label: 'View club' };
    return null;
  }

  if (notice.kind.startsWith('membership')) {
    if (notice.org_id) {
      return {
        href: organizationHref(notice.org_id),
        label: notice.kind === 'membership_invitation' ? 'Open club invitation' : 'View club',
      };
    }
    if (notice.event_id) return { href: eventHref(notice.event_id), label: 'View event' };
    return null;
  }

  if (notice.kind.startsWith('ownership_transfer_')) {
    if (!notice.org_id) return null;
    return hasStaffGrant(actor, notice.org_id)
      ? { href: workspaceHref(notice.org_id), label: 'Open organization workspace' }
      : { href: organizationHref(notice.org_id), label: 'View club' };
  }

  if (isStaffRegistrationReview(notice)) {
    const canOpenWorkspace = hasStaffGrant(actor, notice.org_id);
    if (canOpenWorkspace) {
      return {
        href: workspaceHref(notice.org_id, notice.event_id),
        label: 'Open registration review',
      };
    }
  }

  if (notice.kind === 'chat_message' && notice.event_id) {
    return { href: `/chat?eventId=${encodeURIComponent(notice.event_id)}`, label: 'Open event chat' };
  }
  if (notice.event_id) return { href: eventHref(notice.event_id), label: 'View event' };
  if (notice.org_id) return { href: organizationHref(notice.org_id), label: 'View club' };
  return null;
}
