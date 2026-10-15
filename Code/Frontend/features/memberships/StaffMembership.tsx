'use client';

import { useEffect, useState, type FormEvent } from 'react';
import { Feedback } from '@/components/feedback';
import { ApiError, api } from '@/lib/api';
import { formatDate, formatTime } from '@/lib/date';
import { useSession } from '@/lib/session';
import { useApiResource } from '@/lib/use-api-resource';
import type { MembershipApplicationReview, MembershipInviteOut, MembershipRosterItem,
  MembershipChangeOut, MembershipAuditOut } from '@/lib/types';
import styles from './staff-membership.module.css';

type MembershipRole = 'owner' | 'admin' | 'moderator' | 'member';
type RejectionReason = 'requirements_not_met' | 'applications_closed' | 'other';

const rejectionReasons: { value: RejectionReason; label: string }[] = [
  { value: 'requirements_not_met', label: 'Membership requirements not met' },
  { value: 'applications_closed', label: 'Applications currently closed' },
  { value: 'other', label: 'Other membership criteria' },
];

type MembershipWrite =
  | { kind: 'invite'; recipientId: string; clientKey: string }
  | { kind: 'role'; membershipId: string; label: string; oldRole: MembershipRole; newRole: MembershipRole; clientKey: string }
  | { kind: 'remove'; membershipId: string; label: string; oldRole: MembershipRole; clientKey: string };

type Confirmation =
  | { kind: 'role'; member: MembershipRosterItem; nextRole: MembershipRole }
  | { kind: 'remove'; member: MembershipRosterItem }
  | { kind: 'revoke'; invitation: MembershipInviteOut };

interface StaffMembershipProps {
  orgId: string;
  role: string;
  onChanged?: () => void;
}

const uuidPattern = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

function dateLabel(value: string | null): string {
  if (!value) return 'Not recorded';
  return `${formatDate(value)} · ${formatTime(value)} Manila time`;
}

function roleLabel(value: string): string {
  return value.charAt(0).toUpperCase() + value.slice(1);
}

function statusClass(value: string): string {
  switch (value) {
    case 'pending': return styles.pending;
    case 'approved':
    case 'accepted': return styles.approved;
    case 'rejected':
    case 'revoked': return styles.rejected;
    case 'withdrawn':
    case 'declined': return styles.withdrawn;
    default: return styles.superseded;
  }
}

function isUncertain(error: unknown): boolean {
  return !(error instanceof ApiError) || error.status === 0 || error.status >= 500;
}

function errorText(error: unknown, fallback: string): string {
  return error instanceof Error ? error.message : fallback;
}

function writeDescription(write: MembershipWrite): string {
  if (write.kind === 'invite') return `invitation for account ${write.recipientId}`;
  if (write.kind === 'role') return `${write.label}'s role change from ${roleLabel(write.oldRole)} to ${roleLabel(write.newRole)}`;
  return `removal of ${write.label}`;
}

function StaffMembershipContent({ orgId, role, onChanged }: StaffMembershipProps) {
  const { actor, token, authLoading, error: sessionError } = useSession();
  const [isDesktop, setIsDesktop] = useState(false);
  useEffect(() => {
    const query = window.matchMedia('(min-width: 768px)');
    const update = () => setIsDesktop(query.matches);
    update();
    query.addEventListener('change', update);
    return () => query.removeEventListener('change', update);
  }, []);
  const isStaff = role === 'owner' || role === 'admin' || role === 'moderator';
  const canReview = Boolean(token && actor?.eligible === true && isStaff && isDesktop);
  const canInvite = Boolean(canReview && (role === 'owner' || role === 'admin'));
  const orgPath = `/organizations/${encodeURIComponent(orgId)}`;
  const applications = useApiResource<MembershipApplicationReview[]>(
    canReview ? `${orgPath}/membership-applications` : null, token,
  );
  const invitations = useApiResource<MembershipInviteOut[]>(
    canInvite ? `${orgPath}/membership-invitations` : null, token,
  );
  const roster = useApiResource<MembershipRosterItem[]>(
    canReview ? `${orgPath}/members` : null, token,
  );
  const audit = useApiResource<MembershipAuditOut[]>(
    canReview ? `${orgPath}/membership-audit` : null, token,
  );

  const [rejectionByApplication, setRejectionByApplication] = useState<Record<string, RejectionReason | ''>>({});
  const [reviewBusyId, setReviewBusyId] = useState<string | null>(null);
  const [reviewError, setReviewError] = useState<string | null>(null);
  const [reviewNotice, setReviewNotice] = useState<string | null>(null);
  const [recipientCode, setRecipientCode] = useState('');
  const [recipientError, setRecipientError] = useState<string | null>(null);
  const [pendingWrite, setPendingWrite] = useState<MembershipWrite | null>(null);
  const [writeBusy, setWriteBusy] = useState(false);
  const [writeError, setWriteError] = useState<{ message: string; uncertain: boolean } | null>(null);
  const [writeNotice, setWriteNotice] = useState<string | null>(null);
  const [revokeBusyId, setRevokeBusyId] = useState<string | null>(null);
  const [revokeError, setRevokeError] = useState<string | null>(null);
  const [revokeNotice, setRevokeNotice] = useState<string | null>(null);
  const [confirmation, setConfirmation] = useState<Confirmation | null>(null);
  const [roleSelection, setRoleSelection] = useState<Record<string, MembershipRole>>({});

  function reloadAll() {
    applications.reload();
    invitations.reload();
    roster.reload();
    audit.reload();
  }

  async function decide(
    application: MembershipApplicationReview,
    outcome: 'approved' | 'rejected',
    reason?: RejectionReason,
  ) {
    if (!token || reviewBusyId || pendingWrite || confirmation || (outcome === 'rejected' && !reason)) return;
    const body = { outcome, reason: outcome === 'approved' ? null : reason! };
    setReviewBusyId(application.id);
    setReviewError(null);
    setReviewNotice(null);
    let result: MembershipApplicationReview | null = null;
    try {
      result = await api<MembershipApplicationReview>(
        `${orgPath}/membership-applications/${encodeURIComponent(application.id)}/decision`,
        { token, method: 'POST', body },
      );
    } catch (error) {
      const uncertainty = isUncertain(error)
        ? ' The server may have recorded the decision; refresh the review list before trying again.'
        : '';
      setReviewError(`${errorText(error, 'The decision could not be recorded.')}${uncertainty}`);
    } finally {
      setReviewBusyId(null);
    }
    if (result) {
      setReviewNotice(
        `${result.status.charAt(0).toUpperCase()}${result.status.slice(1)} decision recorded by account ${result.decided_by || 'not returned'} at ${dateLabel(result.resolved_at)}.`,
      );
      reloadAll();
      onChanged?.();
    } else {
      reloadAll();
    }
  }

  async function executeWrite(write: MembershipWrite) {
    if (!token || writeBusy) return;
    setWriteBusy(true);
    setWriteError(null);
    setWriteNotice(null);
    let change: MembershipChangeOut | null = null;
    let invitation: MembershipInviteOut | null = null;
    try {
      if (write.kind === 'invite') {
        invitation = await api<MembershipInviteOut>(`${orgPath}/membership-invitations`, {
          token, method: 'POST',
          body: { recipient_id: write.recipientId, client_key: write.clientKey },
        });
      } else if (write.kind === 'role') {
        change = await api<MembershipChangeOut>(
          `${orgPath}/members/${encodeURIComponent(write.membershipId)}/role`,
          { token, method: 'PATCH', body: { client_key: write.clientKey, role: write.newRole } },
        );
      } else {
        change = await api<MembershipChangeOut>(
          `${orgPath}/members/${encodeURIComponent(write.membershipId)}/remove`,
          { token, method: 'POST', body: { client_key: write.clientKey } },
        );
      }
    } catch (error) {
      const uncertain = isUncertain(error);
      if (!uncertain) setPendingWrite(null);
      setWriteError({ message: errorText(error, 'The membership change could not be completed.'), uncertain });
      reloadAll();
      setWriteBusy(false);
      return;
    }

    setPendingWrite(null);
    setWriteBusy(false);
    setWriteError(null);
    setConfirmation(null);
    if (write.kind === 'invite' && invitation) {
      setRecipientCode('');
      setRecipientError(null);
      setWriteNotice(`Invitation created for account ${invitation.recipient_id}; it expires ${dateLabel(invitation.expires_at)}.`);
    } else if (write.kind === 'role' && change) {
      setRoleSelection(previous => ({ ...previous, [write.membershipId]: change!.role }));
      setWriteNotice(`${write.label}'s role changed from ${roleLabel(write.oldRole)} to ${roleLabel(change.role)}. Existing event registrations were not changed.`);
    } else if (write.kind === 'remove' && change) {
      setWriteNotice(
        `${write.label} was removed. ${change.cancelled_registrations} organization registrations or waitlist entries were canceled; ${change.chat_revoked} event chat access records were revoked.`,
      );
    }
    reloadAll();
    onChanged?.();
  }

  function beginWrite(write: MembershipWrite) {
    if (pendingWrite || writeBusy) return;
    setConfirmation(null);
    setWriteError(null);
    setWriteNotice(null);
    setPendingWrite(write);
    void executeWrite(write);
  }

  function retryLockedWrite() {
    if (pendingWrite && !writeBusy) void executeWrite(pendingWrite);
  }

  function createInvitation(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const recipientId = recipientCode.trim().toLowerCase();
    if (!uuidPattern.test(recipientId)) {
      setRecipientError('Enter the existing account code in UUID format.');
      return;
    }
    setRecipientError(null);
    beginWrite({ kind: 'invite', recipientId, clientKey: crypto.randomUUID() });
  }

  async function revokeInvitation(invitation: MembershipInviteOut) {
    if (!token || revokeBusyId || pendingWrite || writeBusy) return;
    setRevokeBusyId(invitation.id);
    setRevokeError(null);
    setRevokeNotice(null);
    let result: MembershipInviteOut | null = null;
    try {
      result = await api<MembershipInviteOut>(
        `${orgPath}/membership-invitations/${encodeURIComponent(invitation.id)}/revoke`,
        { token, method: 'POST' },
      );
    } catch (error) {
      const uncertainty = isUncertain(error)
        ? ' The response may have been lost; the invite list was refreshed so you can check its current status.'
        : '';
      setRevokeError(`${errorText(error, 'The invitation could not be revoked.')}${uncertainty}`);
    } finally {
      setRevokeBusyId(null);
    }
    if (result) {
      setRevokeNotice(`Invitation status is now ${result.status}; recorded at ${dateLabel(result.resolved_at)}.`);
      reloadAll();
      onChanged?.();
    } else {
      invitations.reload();
    }
  }

  function roleOptions(member: MembershipRosterItem): MembershipRole[] {
    const options: MembershipRole[] = ['member'];
    const self = member.user_id === actor?.id;
    if (member.eligible && !self) {
      if (role === 'owner') options.push('moderator', 'admin');
      else if (role === 'admin') options.push('moderator');
    }
    if (!options.includes(member.role)) options.push(member.role);
    return [...new Set(options)];
  }

  function canChangeRole(member: MembershipRosterItem): boolean {
    if (role === 'owner') return member.role !== 'owner';
    return role === 'admin' && member.role !== 'owner' && member.role !== 'admin';
  }

  function canRemove(member: MembershipRosterItem): boolean {
    if (member.role === 'owner') return false;
    if (member.role === 'admin') return role === 'owner';
    return role === 'owner' || role === 'admin';
  }

  const reviewRows = (applications.data ?? []).slice().sort(
    (left, right) => new Date(right.created_at).getTime() - new Date(left.created_at).getTime(),
  );
  const pendingReviews = reviewRows.filter(application => application.status === 'pending');
  const reviewHistory = reviewRows.filter(application => application.status !== 'pending');
  const lockedWrite = pendingWrite !== null;

  return (
    <div className={styles.root}>
      <p className={styles.mobileNotice} role="note">
        Membership management is available on desktop. Open this page on a wider screen to continue.
      </p>
      <div className={styles.desktopOnly}>
        <header className={styles.heading}>
          <p className={styles.eyebrow}>Organization workspace</p>
          <h2 className={styles.title}>Membership management</h2>
          <p className={styles.intro}>Review applications, manage account-bound invitations, and view the staff roster and audit history.</p>
        </header>

        {authLoading ? <Feedback loading /> : !token || !actor ? (
          <section className={styles.gate} role={sessionError ? 'alert' : 'status'}>
            {sessionError?.message || 'Choose a local account to access this organization workspace.'}
          </section>
        ) : actor.eligible !== true ? (
          <section className={styles.gate} role="status">
            Organization workspace access is locked until trusted PLM eligibility is current.
          </section>
        ) : !isStaff ? (
          <section className={styles.gate} role="status">
            This panel is available to organization staff. Membership access is still checked by the service.
          </section>
        ) : !isDesktop ? (
          <Feedback loading />
        ) : (
          <div className={styles.content}>
            {pendingWrite && (
              <section className={styles.locked} role="status" aria-live="polite">
                <strong>{writeBusy ? `Saving ${writeDescription(pendingWrite)}…` : `Retry locked ${writeDescription(pendingWrite)}.`}</strong>
                <p>
                  {writeError?.uncertain
                    ? 'The server may have applied this action. Retry the exact saved payload and key before starting another membership change.'
                    : 'This action is in progress. Other membership changes are temporarily disabled.'}
                </p>
                {writeError && <p role="alert">{writeError.message}</p>}
                {!writeBusy && (
                  <button className="button button-secondary" type="button" onClick={retryLockedWrite}>
                    Retry the same {pendingWrite.kind === 'role' ? 'role change' : pendingWrite.kind === 'remove' ? 'removal' : 'invitation'}
                  </button>
                )}
              </section>
            )}
            {writeNotice && <p className={styles.success} role="status">{writeNotice}</p>}
            {writeError && !pendingWrite && (
              <div className={styles.error} role="alert">
                <p>{writeError.message}</p>
                <button className="button button-secondary" type="button" onClick={reloadAll}>Refresh membership lists</button>
              </div>
            )}

            <section className={styles.section} aria-labelledby="membership-review-title">
              <div className={styles.sectionHeader}>
                <div>
                  <h2 id="membership-review-title">Applications</h2>
                  <p className={styles.muted}>Pending requests and closed review history. Decisions show the recorded staff account and server time.</p>
                </div>
              </div>
              {reviewNotice && <p className={styles.success} role="status">{reviewNotice}</p>}
              {reviewError && (
                <div className={styles.error} role="alert">
                  <p>{reviewError}</p>
                  <button className="button button-secondary" type="button" onClick={applications.reload}>Refresh review list</button>
                </div>
              )}
              <Feedback loading={applications.loading} error={applications.error} onRetry={applications.reload}>
                <div className={styles.subsection}>
                  <h3>Pending</h3>
                  {!pendingReviews.length ? <p className={styles.empty}>No pending membership applications.</p> : (
                    <div className={styles.list}>
                      {pendingReviews.map(application => {
                        const selectedReason = rejectionByApplication[application.id] ?? '';
                        const showPersona = application.status === 'pending' && application.persona_shared && application.persona !== null;
                        return (
                          <article className={styles.card} key={application.id}>
                            <header className={styles.cardHeader}>
                              <div>
                                <h4>{application.applicant_label}</h4>
                                <p className={styles.meta}>Submitted <time dateTime={application.created_at}>{dateLabel(application.created_at)}</time></p>
                              </div>
                              <span className={`${styles.status} ${statusClass(application.status)}`}>Pending</span>
                            </header>
                            {showPersona ? (
                              <div className={styles.persona} aria-label="Membership-review details the applicant chose to share">
                                <p className={styles.personaHeading}>Applicant opted in to share these details for this pending review</p>
                                {application.persona?.nickname && <p>Nickname: {application.persona.nickname}</p>}
                                {application.persona?.tags.length ? (
                                  <p>Interests: {application.persona.tags.map((tag, index) => <span className={styles.tag} key={`${application.id}-${index}`}>{tag}</span>)}</p>
                                ) : null}
                                {!application.persona?.nickname && !application.persona?.tags.length && <p className={styles.muted}>No nickname or interests were provided for this review.</p>}
                              </div>
                            ) : (
                              <p className={styles.muted}>No membership-review persona was shared. Other profile or event visibility settings do not apply here.</p>
                            )}
                            <div className={styles.actions}>
                              <button
                                className="button"
                                type="button"
                                disabled={reviewBusyId !== null || lockedWrite || confirmation !== null}
                                onClick={() => void decide(application, 'approved')}
                              >
                                {reviewBusyId === application.id ? 'Saving…' : 'Approve membership'}
                              </button>
                              <label className={styles.reasonField} htmlFor={`membership-reason-${application.id}`}>
                                Rejection reason
                                <select
                                  id={`membership-reason-${application.id}`}
                                  required
                                  value={selectedReason}
                                  disabled={reviewBusyId !== null || lockedWrite || confirmation !== null}
                                  onChange={event => setRejectionByApplication(previous => ({
                                    ...previous, [application.id]: event.target.value as RejectionReason | '',
                                  }))}
                                >
                                  <option value="">Choose a reason</option>
                                  {rejectionReasons.map(reason => <option key={reason.value} value={reason.value}>{reason.label}</option>)}
                                </select>
                              </label>
                              <button
                                className="button button-danger"
                                type="button"
                                disabled={!selectedReason || reviewBusyId !== null || lockedWrite || confirmation !== null}
                                onClick={() => void decide(application, 'rejected', selectedReason || undefined)}
                              >
                                Reject application
                              </button>
                            </div>
                          </article>
                        );
                      })}
                    </div>
                  )}
                </div>
                <div className={styles.subsection}>
                  <h3>Review history</h3>
                  {!reviewHistory.length ? <p className={styles.empty}>No closed membership reviews yet.</p> : (
                    <div className={styles.list}>
                      {reviewHistory.map(application => (
                        <article className={styles.card} key={application.id}>
                          <header className={styles.cardHeader}>
                            <div>
                              <h4>{application.applicant_label}</h4>
                              <p className={styles.meta}>Submitted <time dateTime={application.created_at}>{dateLabel(application.created_at)}</time></p>
                            </div>
                            <span className={`${styles.status} ${statusClass(application.status)}`}>{application.status}</span>
                          </header>
                          <p className={styles.meta}>
                            Recorded by account {application.decided_by || 'not returned'} at{' '}
                            <time dateTime={application.resolved_at || undefined}>{dateLabel(application.resolved_at)}</time>
                          </p>
                          {application.status === 'rejected' && application.reason && (
                            <p>Reason: {rejectionReasons.find(reason => reason.value === application.reason)?.label || 'Other membership criteria'}</p>
                          )}
                          {application.can_reapply_at && (
                            <p className={styles.meta}>Reapplication available <time dateTime={application.can_reapply_at}>{dateLabel(application.can_reapply_at)}</time></p>
                          )}
                        </article>
                      ))}
                    </div>
                  )}
                </div>
              </Feedback>
            </section>

            {canInvite && (
              <section className={styles.section} aria-labelledby="membership-invitations-title">
                <div className={styles.sectionHeader}>
                  <div>
                    <h2 id="membership-invitations-title">Targeted invitations</h2>
                    <p className={styles.muted}>Invite an existing account by its account code. Invitations are private, single-use, and expire after seven days.</p>
                  </div>
                </div>
                {revokeNotice && <p className={styles.success} role="status">{revokeNotice}</p>}
                {revokeError && <p className={styles.error} role="alert">{revokeError}</p>}
                <form className={styles.invitationForm} onSubmit={createInvitation}>
                  <label className={styles.field} htmlFor="membership-recipient-code">
                    Existing account code (UUID)
                    <input
                      id="membership-recipient-code"
                      type="text"
                      autoComplete="off"
                      maxLength={36}
                      pattern="[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
                      placeholder="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
                      value={recipientCode}
                      disabled={lockedWrite || confirmation !== null}
                      onChange={event => { setRecipientCode(event.target.value); setRecipientError(null); }}
                      required
                    />
                  </label>
                  {recipientError && <p className={styles.error} role="alert">{recipientError}</p>}
                  <button className="button" type="submit" disabled={lockedWrite || confirmation !== null}>
                    {pendingWrite?.kind === 'invite' && writeBusy ? 'Sending…' : 'Send invitation'}
                  </button>
                </form>
                <Feedback loading={invitations.loading} error={invitations.error} onRetry={invitations.reload}>
                  {!invitations.data?.length ? <p className={styles.empty}>No membership invitations have been recorded.</p> : (
                    <div className={styles.list}>
                      {invitations.data.map(invitation => (
                        <article className={styles.card} key={invitation.id}>
                          <header className={styles.cardHeader}>
                            <div>
                              <h4>Account {invitation.recipient_id}</h4>
                              <p className={styles.meta}>Sent {dateLabel(invitation.created_at)} · expires {dateLabel(invitation.expires_at)}</p>
                            </div>
                            <span className={`${styles.status} ${statusClass(invitation.status)}`}>{invitation.status}</span>
                          </header>
                          <p className={styles.meta}>
                            {invitation.sender_id === actor.id ? 'Sent by you' : `Sent by account ${invitation.sender_id}`}
                            {' · '}{invitation.access_ready ? 'Workspace access is ready on acceptance' : 'Access remains eligibility-gated'}
                          </p>
                          {invitation.resolved_at && <p className={styles.meta}>Resolved <time dateTime={invitation.resolved_at}>{dateLabel(invitation.resolved_at)}</time></p>}
                          {invitation.status === 'pending' && (role === 'owner' || role === 'admin') ? (
                            confirmation?.kind === 'revoke' && confirmation.invitation.id === invitation.id ? (
                              <div className={styles.confirmation} role="group" aria-label="Confirm invitation revocation">
                                <p>Revoke this invitation now? The intended account will no longer be able to accept it.</p>
                                <div className={styles.actions}>
                                  <button className="button button-danger" type="button" disabled={revokeBusyId !== null || lockedWrite} onClick={() => {
                                    const target = confirmation.invitation;
                                    setConfirmation(null);
                                    void revokeInvitation(target);
                                  }}>Confirm revocation</button>
                                  <button className="button button-secondary" type="button" onClick={() => setConfirmation(null)}>Keep invitation</button>
                                </div>
                              </div>
                            ) : (
                              <button
                                className="button button-danger"
                                type="button"
                                disabled={revokeBusyId !== null || lockedWrite || confirmation !== null}
                                onClick={() => setConfirmation({ kind: 'revoke', invitation })}
                              >
                                {revokeBusyId === invitation.id ? 'Revoking…' : 'Revoke invitation'}
                              </button>
                            )
                          ) : null}
                        </article>
                      ))}
                    </div>
                  )}
                </Feedback>
              </section>
            )}

            <section className={styles.section} aria-labelledby="membership-roster-title">
              <div className={styles.sectionHeader}>
                <div>
                  <h2 id="membership-roster-title">Staff roster</h2>
                  <p className={styles.muted}>Staff-only account labels and membership state. This roster contains no private profile details.</p>
                </div>
              </div>
              <Feedback loading={roster.loading} error={roster.error} onRetry={roster.reload}>
                {!roster.data?.length ? <p className={styles.empty}>No active organization memberships were returned.</p> : (
                  <div className={styles.list}>
                    {roster.data.map(member => {
                      const options = roleOptions(member);
                      const selectedRole = roleSelection[member.id] ?? member.role;
                      const canEditRole = canChangeRole(member) && options.length > 1;
                      const memberConfirmation = confirmation && confirmation.kind !== 'revoke' && confirmation.member.id === member.id
                        ? confirmation : null;
                      return (
                        <article className={styles.card} key={member.id}>
                          <header className={styles.cardHeader}>
                            <div>
                              <h4>{member.label}</h4>
                              <p className={styles.meta}>{roleLabel(member.role)} · {member.eligible ? 'PLM eligible' : 'PLM eligibility not current'} · {member.access_ready ? 'workspace access ready' : 'workspace access locked'}</p>
                              <p className={styles.meta}>Joined {dateLabel(member.joined_at)}</p>
                            </div>
                            <span className={`${styles.status} ${member.access_ready ? styles.approved : styles.withdrawn}`}>
                              {member.access_ready ? 'Active access' : 'Access locked'}
                            </span>
                          </header>
                          {(canEditRole || canRemove(member)) && (
                            <div className={styles.memberActions}>
                              {canEditRole && (
                                <div className={styles.roleControl}>
                                  <label className={styles.field} htmlFor={`membership-role-${member.id}`}>
                                    Change role
                                    <select
                                      id={`membership-role-${member.id}`}
                                      value={selectedRole}
                                      disabled={lockedWrite || confirmation !== null}
                                      onChange={event => setRoleSelection(previous => ({ ...previous, [member.id]: event.target.value as MembershipRole }))}
                                    >
                                      {options.map(option => <option value={option} key={option}>{roleLabel(option)}</option>)}
                                    </select>
                                  </label>
                                  <button
                                    className="button button-secondary"
                                    type="button"
                                    disabled={selectedRole === member.role || lockedWrite || confirmation !== null}
                                    onClick={() => setConfirmation({ kind: 'role', member, nextRole: selectedRole })}
                                  >Confirm role change</button>
                                </div>
                              )}
                              {canRemove(member) && (
                                <button
                                  className="button button-danger"
                                  type="button"
                                  disabled={lockedWrite || confirmation !== null}
                                  onClick={() => setConfirmation({ kind: 'remove', member })}
                                >Remove member</button>
                              )}
                            </div>
                          )}
                          {memberConfirmation?.kind === 'role' && (
                            <div className={styles.confirmation} role="group" aria-label="Confirm membership role change">
                              <p>Change {member.label} from {roleLabel(member.role)} to {roleLabel(memberConfirmation.nextRole)}? Role changes do not alter event registrations or chat access.</p>
                              <div className={styles.actions}>
                                <button className="button" type="button" disabled={lockedWrite} onClick={() => beginWrite({
                                  kind: 'role', membershipId: member.id, label: member.label, oldRole: member.role,
                                  newRole: memberConfirmation.nextRole, clientKey: crypto.randomUUID(),
                                })}>Confirm role change</button>
                                <button className="button button-secondary" type="button" onClick={() => {
                                  setRoleSelection(previous => ({ ...previous, [member.id]: member.role }));
                                  setConfirmation(null);
                                }}>Cancel</button>
                              </div>
                            </div>
                          )}
                          {memberConfirmation?.kind === 'remove' && (
                            <div className={styles.confirmation} role="group" aria-label="Confirm membership removal">
                              <p>Remove {member.label} from this organization? This ends membership, cancels affected organization registrations and waitlist entries, releases seats under the waitlist rules, and ends their organization-event chat access.</p>
                              <div className={styles.actions}>
                                <button className="button button-danger" type="button" disabled={lockedWrite} onClick={() => beginWrite({
                                  kind: 'remove', membershipId: member.id, label: member.label, oldRole: member.role,
                                  clientKey: crypto.randomUUID(),
                                })}>Confirm removal</button>
                                <button className="button button-secondary" type="button" onClick={() => setConfirmation(null)}>Cancel</button>
                              </div>
                            </div>
                          )}
                          {canChangeRole(member) && !member.eligible && member.role === 'member' && (
                            <p className={styles.meta}>Staff roles can be assigned only while this member has current trusted PLM eligibility.</p>
                          )}
                        </article>
                      );
                    })}
                  </div>
                )}
              </Feedback>
            </section>

            <section className={styles.section} aria-labelledby="membership-audit-title">
              <div className={styles.sectionHeader}>
                <div>
                  <h2 id="membership-audit-title">Membership audit</h2>
                  <p className={styles.muted}>Latest organization membership actions recorded by the service.</p>
                </div>
              </div>
              <Feedback loading={audit.loading} error={audit.error} onRetry={audit.reload}>
                {!audit.data?.length ? <p className={styles.empty}>No membership audit records were returned.</p> : (
                  <ol className={styles.auditList}>
                    {audit.data.map(record => (
                      <li className={styles.auditRow} key={record.id}>
                        <div>
                          <strong>{record.action.replace(/_/g, ' ')}</strong>
                          {record.old_role && record.new_role && <span> · {roleLabel(record.old_role)} → {roleLabel(record.new_role)}</span>}
                          <p className={styles.meta}>
                            Actor: {record.actor_id ? `account ${record.actor_id}` : 'system'} · affected account: {record.user_id}
                          </p>
                        </div>
                        <time className={styles.meta} dateTime={record.created_at}>{dateLabel(record.created_at)}</time>
                      </li>
                    ))}
                  </ol>
                )}
              </Feedback>
            </section>
          </div>
        )}
      </div>
    </div>
  );
}

export function StaffMembership(props: StaffMembershipProps) {
  const { version } = useSession();
  return <StaffMembershipContent key={`${props.orgId}:${version}`} {...props} />;
}
