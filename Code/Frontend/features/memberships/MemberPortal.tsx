'use client';

import { useEffect, useRef, useState } from 'react';
import { Feedback } from '@/components/feedback';
import { ApiError, api } from '@/lib/api';
import { formatDate, formatTime } from '@/lib/date';
import { useApiResource } from '@/lib/use-api-resource';
import { useSession } from '@/lib/session';
import { AnnouncementReader } from '@/features/announcements/AnnouncementReader';
import type { Organization, MembershipApplicationOut, MembershipInviteOut, MembershipSelfOut,
  MembershipApplicationInput, MembershipKeyInput } from '@/lib/types';
import styles from './member-portal.module.css';

type ApplicationStatus = 'pending' | 'approved' | 'rejected' | 'withdrawn' | 'superseded';
type RejectionReason = 'requirements_not_met' | 'applications_closed' | 'other';

interface MutationAttempt {
  id: string;
  label: string;
  successMessage: string;
  path: string;
  body: MembershipApplicationInput | MembershipKeyInput | undefined;
}

const reasonLabels: Record<RejectionReason, string> = {
  requirements_not_met: 'Membership requirements not met',
  applications_closed: 'Applications currently closed',
  other: 'Other membership criteria',
};

const applicationLabels: Record<ApplicationStatus, string> = {
  pending: 'Awaiting review',
  approved: 'Approved',
  rejected: 'Not approved',
  withdrawn: 'Withdrawn',
  superseded: 'Closed after another request succeeded',
};

function formatMoment(value: string | null | undefined) {
  if (!value || !Number.isFinite(Date.parse(value))) return null;
  return `${formatDate(value)} at ${formatTime(value)}`;
}

function isUncertain(error: ApiError) {
  return error.status === 0 || error.status >= 500;
}

export function MemberPortal({ orgId }: { orgId?: string }) {
  const { actor, token, authLoading, version } = useSession();
  return (
    <MemberPortalView
      key={`${version}:${token ?? 'guest'}`}
      actor={actor}
      token={token}
      authLoading={authLoading}
      orgId={orgId}
    />
  );
}

function MemberPortalView({
  actor,
  token,
  authLoading,
  orgId,
}: {
  actor: ReturnType<typeof useSession>['actor'];
  token: string | null;
  authLoading: boolean;
  orgId?: string;
}) {
  const { refreshActor } = useSession();
  const organizations = useApiResource<Organization[]>('/organizations');
  const applications = useApiResource<MembershipApplicationOut[]>(token ? '/me/membership-applications' : null, token);
  const invitations = useApiResource<MembershipInviteOut[]>(token ? '/me/membership-invitations' : null, token);
  const memberships = useApiResource<MembershipSelfOut[]>(token ? '/me/memberships' : null, token);
  const [selectedOrgId, setSelectedOrgId] = useState(orgId ?? '');
  const [personaShared, setPersonaShared] = useState(false);
  const [withdrawingId, setWithdrawingId] = useState<string | null>(null);
  const [leavingId, setLeavingId] = useState<string | null>(null);
  const [pendingAttempt, setPendingAttempt] = useState<MutationAttempt | null>(null);
  const [mutationError, setMutationError] = useState<ApiError | null>(null);
  const [mutationBusy, setMutationBusy] = useState(false);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);
  const [copyMessage, setCopyMessage] = useState<string | null>(null);
  const [accountRefreshError, setAccountRefreshError] = useState(false);
  const [now, setNow] = useState(() => Date.now());
  const mutationController = useRef<AbortController | null>(null);

  useEffect(() => () => mutationController.current?.abort(), []);

  const visibleOrganizations = (organizations.data ?? []).filter((organization) => !orgId || organization.id === orgId);
  const activeOrgId = orgId ?? (selectedOrgId || (organizations.data?.[0]?.id ?? ''));
  const selectedOrganization = visibleOrganizations.find((organization) => organization.id === activeOrgId) ?? null;
  const ownApplications = applications.data ?? [];
  const ownInvitations = invitations.data ?? [];
  const ownMemberships = memberships.data ?? [];
  const selectedApplications = selectedOrganization
    ? ownApplications
      .filter((application) => application.org_id === selectedOrganization.id)
      .slice()
      .sort((left, right) => Date.parse(right.created_at) - Date.parse(left.created_at))
    : [];
  const latestApplication = selectedApplications[0] ?? null;
  const pendingApplication = selectedApplications.find((application) => application.status === 'pending') ?? null;
  const selectedMembership = selectedOrganization
    ? ownMemberships.find((membership) => membership.org_id === selectedOrganization.id) ?? null
    : null;
  const selectedActiveMembership = selectedMembership?.active ? selectedMembership : null;
  const reapplyAt = latestApplication?.status === 'withdrawn' ? latestApplication.can_reapply_at : null;
  const reapplyTimestamp = reapplyAt ? Date.parse(reapplyAt) : null;
  const cooldownActive = Boolean(reapplyAt && (!Number.isFinite(reapplyTimestamp) || reapplyTimestamp! > now));

  const deadlines = [
    ...ownApplications.map((application) => application.status === 'withdrawn' && application.can_reapply_at
      ? Date.parse(application.can_reapply_at)
      : Number.NaN),
    ...ownInvitations.map((invitation) => invitation.status === 'pending' ? Date.parse(invitation.expires_at) : Number.NaN),
  ].filter((deadline) => Number.isFinite(deadline) && deadline > now);
  const nextDeadline = deadlines.length ? Math.min(...deadlines) : null;
  useEffect(() => {
    if (nextDeadline === null) return;
    const timer = window.setTimeout(() => setNow(Date.now()), Math.max(0, nextDeadline - Date.now() + 1));
    return () => window.clearTimeout(timer);
  }, [nextDeadline]);

  async function performAttempt(attempt: MutationAttempt) {
    if (!token || mutationController.current) return;
    const controller = new AbortController();
    mutationController.current = controller;
    setMutationBusy(true);
    setMutationError(null);
    setSuccessMessage(null);
    try {
      await api<unknown>(attempt.path, {
        token,
        method: 'POST',
        body: attempt.body,
        signal: controller.signal,
      });
      if (controller.signal.aborted) return;
      setPendingAttempt(null);
      setMutationError(null);
      setSuccessMessage(attempt.successMessage);
      setWithdrawingId(null);
      setLeavingId(null);
      if (attempt.id.startsWith('apply:')) setPersonaShared(false);
      applications.reload();
      invitations.reload();
      memberships.reload();
      void refreshAccount();
    } catch (caught) {
      if (controller.signal.aborted) return;
      const error = caught instanceof ApiError
        ? caught
        : new ApiError(0, 'request_failed', 'The result could not be confirmed. Retry the same request.');
      setMutationError(error);
      if (!isUncertain(error)) setPendingAttempt(null);
    } finally {
      if (!controller.signal.aborted) setMutationBusy(false);
      if (mutationController.current === controller) mutationController.current = null;
    }
  }

  function beginMutation(attempt: MutationAttempt) {
    if (!token || mutationBusy || pendingAttempt) return;
    setMutationError(null);
    setSuccessMessage(null);
    setPendingAttempt(attempt);
    void performAttempt(attempt);
  }

  function refreshOwnStatus() {
    applications.reload();
    invitations.reload();
    memberships.reload();
    void refreshAccount();
  }

  async function refreshAccount() {
    try { await refreshActor(); setAccountRefreshError(false); }
    catch { setAccountRefreshError(true); }
  }

  async function copyAccountCode() {
    if (!actor) return;
    try {
      await navigator.clipboard.writeText(actor.id);
      setCopyMessage('Account code copied.');
    } catch {
      setCopyMessage('Copy is unavailable here. You can select the account code to copy it.');
    }
  }

  const privateStatusReady = Boolean(
    token && actor && applications.data !== null && memberships.data !== null &&
    !applications.loading && !memberships.loading && !applications.error && !memberships.error,
  );

  return (
    <div className={styles.portal}>
      {accountRefreshError && <p role="status" className="panel muted">The account menu could not refresh. Retrying updates your access display without repeating a membership action. <button type="button" className="text-action" onClick={() => void refreshAccount()}>Retry account refresh</button></p>}
      <header className={styles.hero}>
        <div className={styles.heroCopy}>
          <p className={styles.eyebrow}>Organizations · Memberships</p>
          <h1>Find your people</h1>
          <p className={styles.lede}>Browse approved organizations and keep your membership requests and invitations in one place.</p>
          {actor && !actor.eligible ? (
            <p className={styles.accessNote} role="status">
              You can apply and follow your request now. Organization member features stay locked until current PLM eligibility is confirmed.
            </p>
          ) : null}
        </div>
        <div className={styles.accountCard}>
          <p className={styles.accountLabel}>Your shareable account code</p>
          {authLoading && !actor ? <p role="status" className="muted">Checking your account…</p> : null}
          {actor ? (
            <>
              <div className={styles.accountCode}>
                <code>{actor.id}</code>
                <button type="button" className="button button-secondary" onClick={() => void copyAccountCode()}>Copy</button>
              </div>
              {copyMessage ? <p role="status" className={styles.copyMessage}>{copyMessage}</p> : null}
              <p className={styles.accountHint}>Share this code directly with an organization that invites you. There is no public member directory.</p>
            </>
          ) : !authLoading ? (
            <p className={styles.accountHint}>Sign in to see your code, submit a request, or manage invitations. Organization browsing is available without signing in.</p>
          ) : null}
        </div>
      </header>

      {successMessage ? <p className={styles.success} role="status">{successMessage}</p> : null}
      {mutationError ? (
        <div className="panel error" role="alert">
          <p>{mutationError.message}</p>
          {pendingAttempt ? (
            <>
              <p>The {pendingAttempt.label} result is uncertain. Its request is locked, so retrying will send the exact same path and body, including the same request key.</p>
              <button type="button" className="button button-secondary" disabled={mutationBusy} onClick={() => void performAttempt(pendingAttempt)}>
                {mutationBusy ? 'Checking…' : `Retry ${pendingAttempt.label}`}
              </button>
            </>
          ) : (
            <button type="button" className="button button-secondary" onClick={refreshOwnStatus}>Refresh your status</button>
          )}
        </div>
      ) : null}

      <div className={styles.portalGrid}>
        <div className={styles.primaryColumn}>
          <section className="panel stack" aria-labelledby="organization-directory-title">
            <div className={styles.sectionHeading}>
              <div>
                <p className={styles.eyebrow}>Open to everyone</p>
                <h2 id="organization-directory-title">Browse organizations</h2>
              </div>
            </div>
            <Feedback loading={organizations.loading} error={organizations.error} onRetry={organizations.reload}>
              {visibleOrganizations.length ? (
                <div className={styles.organizationList}>
                  {visibleOrganizations.map((organization) => (
                    <button
                      className={styles.organizationChoice}
                      type="button"
                      key={organization.id}
                      aria-pressed={organization.id === activeOrgId}
                      disabled={Boolean(pendingAttempt)}
                      onClick={() => {
                        setSelectedOrgId(organization.id);
                        setPersonaShared(false);
                        setWithdrawingId(null);
                        setLeavingId(null);
                      }}
                    >
                      <span className={styles.organizationName}>{organization.name}</span>
                      <span className={styles.organizationDescription}>{organization.description}</span>
                      <span className={styles.choiceHint}>{organization.id === activeOrgId ? 'Selected' : 'View membership options'}</span>
                    </button>
                  ))}
                </div>
              ) : (
                <p className="panel muted">{orgId ? 'This approved organization is not available to browse right now.' : 'No approved organizations are listed yet.'}</p>
              )}
            </Feedback>
          </section>

          {selectedOrganization ? (
            <section className={`panel ${styles.selectedOrganization}`} aria-labelledby="selected-organization-title">
              <div>
                <p className={styles.eyebrow}>Membership request</p>
                <h2 id="selected-organization-title">{selectedOrganization.name}</h2>
                <p className="muted">{selectedOrganization.description}</p>
              </div>

              {!token || !actor ? (
                <p className={styles.info}>Sign in with your own account to request membership. Guests can browse, but cannot acquire an anonymous membership.</p>
              ) : !privateStatusReady ? (
                applications.error || memberships.error ? (
                  <p className={styles.info}>Your private status must load before you can submit a request. Use the retry controls in Your activity below.</p>
                ) : <p className="muted" role="status">Checking your request and membership status…</p>
              ) : selectedActiveMembership ? (
                <div className={styles.info}>
                  <strong>{actor.eligible && selectedActiveMembership.access_ready ? 'Your membership is active.' : 'Your membership is on file, but member features are locked.'}</strong>
                  {!(actor.eligible && selectedActiveMembership.access_ready) ? (
                    <p>Member features require both an active membership and current PLM eligibility.</p>
                  ) : null}
                </div>
              ) : pendingApplication ? (
                <div className={styles.applicationPanel}>
                  <p className={styles.status} data-status="pending">Awaiting organization review</p>
                  <p>Your request is pending. You may withdraw it; withdrawing starts a 24-hour cooldown before you can apply to this organization again.</p>
                  {withdrawingId === pendingApplication.id ? (
                    <div className={styles.confirmation} role="group" aria-label="Confirm request withdrawal">
                      <p>Withdraw this request? You can apply to this organization again after the 24-hour cooldown. The consent attached to this pending request ends when you withdraw.</p>
                      <div className={styles.actions}>
                        <button
                          type="button"
                          className="button button-danger"
                          disabled={mutationBusy || Boolean(pendingAttempt)}
                          onClick={() => beginMutation({
                            id: `withdraw:${pendingApplication.id}`,
                            label: 'withdrawal',
                            successMessage: 'Your request was withdrawn. A 24-hour cooldown applies before reapplying to this organization.',
                            path: `/membership-applications/${encodeURIComponent(pendingApplication.id)}/withdraw`,
                            body: undefined,
                          })}
                        >{mutationBusy ? 'Withdrawing…' : 'Confirm withdrawal'}</button>
                        <button type="button" className="button button-secondary" disabled={mutationBusy} onClick={() => setWithdrawingId(null)}>Keep request</button>
                      </div>
                    </div>
                  ) : (
                    <button type="button" className="button button-secondary" disabled={Boolean(pendingAttempt)} onClick={() => setWithdrawingId(pendingApplication.id)}>Withdraw request</button>
                  )}
                </div>
              ) : cooldownActive ? (
                <div className={styles.info}>
                  <strong>Reapplication is temporarily paused after withdrawal.</strong>
                  <p>You can apply again{formatMoment(reapplyAt) ? ` after ${formatMoment(reapplyAt)}` : ' once the 24-hour cooldown ends'}.</p>
                </div>
              ) : (
                <div className={styles.applicationPanel}>
                  {latestApplication?.status === 'rejected' ? (
                    <p className={styles.info}>
                      Your previous request was not approved{latestApplication.reason ? `: ${reasonLabels[latestApplication.reason]}` : ''}. You may reapply immediately.
                    </p>
                  ) : latestApplication?.status === 'withdrawn' ? (
                    <p className={styles.info}>The withdrawal cooldown has ended. You may apply again.</p>
                  ) : null}
                  <form onSubmit={(event) => {
                    event.preventDefault();
                    if (!privateStatusReady || pendingAttempt || mutationBusy) return;
                    beginMutation({
                      id: `apply:${selectedOrganization.id}`,
                      label: 'membership request',
                      successMessage: 'Your request was sent. It is not a confirmed membership; the organization must review it.',
                      path: `/organizations/${encodeURIComponent(selectedOrganization.id)}/membership-applications`,
                      body: { client_key: window.crypto.randomUUID(), persona_shared: personaShared },
                    });
                  }}>
                    <label className={styles.consentLabel}>
                      <input
                        type="checkbox"
                        checked={personaShared}
                        disabled={mutationBusy || Boolean(pendingAttempt)}
                        onChange={(event) => setPersonaShared(event.target.checked)}
                      />
                      <span>Optionally share my nickname and interests with this organization&apos;s reviewers while my request is pending.</span>
                    </label>
                    <p className={styles.privacyCopy}>This starts unchecked. It does not share age, pronouns, email, photos, or a written note, and ends when the request is approved, rejected, or withdrawn.</p>
                    <button type="submit" className="button" disabled={mutationBusy || Boolean(pendingAttempt)}>
                      {mutationBusy && pendingAttempt?.id === `apply:${selectedOrganization.id}` ? 'Sending…' : 'Request membership'}
                    </button>
                  </form>
                </div>
              )}
            </section>
          ) : null}
          {selectedOrganization?.accreditation_status === 'approved' ? (
            <AnnouncementReader
              key={`${selectedOrganization.id}:${token ?? 'guest'}`}
              orgId={selectedOrganization.id}
              token={token}
              eligible={Boolean(token && actor?.eligible)}
            />
          ) : null}
        </div>

        <aside className={styles.activityColumn} aria-label="Your membership activity">
          <section className="panel stack" aria-labelledby="memberships-title">
            <div className={styles.sectionHeading}>
              <div>
                <p className={styles.eyebrow}>Your account only</p>
                <h2 id="memberships-title">Your memberships</h2>
              </div>
            </div>
            {!token || !actor ? (
              <p className="muted">Sign in to see your membership status. No member directory is shown here.</p>
            ) : (
              <Feedback loading={memberships.loading} error={memberships.error} onRetry={memberships.reload}>
                {ownMemberships.length ? (
                  <div className={styles.recordList}>
                    {ownMemberships.map((membership) => {
                      const accessReady = actor.eligible && membership.active && membership.access_ready;
                      return (
                        <article className={styles.record} key={membership.id}>
                          <div className={styles.recordHeading}>
                            <h3>{membership.organization_name}</h3>
                            <span className={styles.status} data-status={membership.active ? (accessReady ? 'approved' : 'locked') : 'ended'}>
                              {membership.active ? (accessReady ? 'Access ready' : 'Access locked') : 'Membership ended'}
                            </span>
                          </div>
                          <p className={styles.recordMeta}>Your role: {membership.role}{membership.joined_at ? ` · Joined ${formatMoment(membership.joined_at) ?? 'date unavailable'}` : ''}</p>
                          {membership.active && !accessReady ? (
                            <p className={styles.privacyCopy}>Organization member features stay locked until current PLM eligibility and membership access are both confirmed.</p>
                          ) : null}
                          {membership.active && membership.role === 'owner' ? (
                            <p className={styles.privacyCopy}>Owners cannot leave while they remain the organization owner. Ownership transfer is not available here.</p>
                          ) : null}
                          {membership.active && membership.role !== 'owner' ? (
                            leavingId === membership.id ? (
                              <div className={styles.confirmation} role="group" aria-label={`Confirm leaving ${membership.organization_name}`}>
                                <p>Leaving ends your organization access, cancels your active registrations and waitlist entries for its events, and revokes access to those event chats. Attendance history remains on record.</p>
                                <div className={styles.actions}>
                                  <button
                                    type="button"
                                    className="button button-danger"
                                    disabled={mutationBusy || Boolean(pendingAttempt)}
                                    onClick={() => beginMutation({
                                      id: `leave:${membership.id}`,
                                      label: 'membership leave',
                                      successMessage: `You left ${membership.organization_name}. Related active event participation and chat access were ended.`,
                                      path: `/organizations/${encodeURIComponent(membership.org_id)}/membership/leave`,
                                      body: { client_key: window.crypto.randomUUID() },
                                    })}
                                  >{mutationBusy ? 'Leaving…' : 'Confirm leave'}</button>
                                  <button type="button" className="button button-secondary" disabled={mutationBusy} onClick={() => setLeavingId(null)}>Stay</button>
                                </div>
                              </div>
                            ) : (
                              <button type="button" className="button button-secondary" disabled={Boolean(pendingAttempt)} onClick={() => setLeavingId(membership.id)}>Leave organization</button>
                            )
                          ) : null}
                        </article>
                      );
                    })}
                  </div>
                ) : <p className="panel muted">You do not have any organization memberships yet.</p>}
              </Feedback>
            )}
          </section>

          <section className="panel stack" aria-labelledby="requests-title">
            <div className={styles.sectionHeading}>
              <div>
                <p className={styles.eyebrow}>Private to you</p>
                <h2 id="requests-title">Your requests</h2>
              </div>
            </div>
            {!token || !actor ? (
              <p className="muted">Sign in to see your request history.</p>
            ) : (
              <Feedback loading={applications.loading} error={applications.error} onRetry={applications.reload}>
                {ownApplications.length ? (
                  <div className={styles.recordList}>
                    {ownApplications.map((application) => {
                      const cooldownTime = application.can_reapply_at ? Date.parse(application.can_reapply_at) : Number.NaN;
                      const cooldown = application.status === 'withdrawn' && application.can_reapply_at &&
                        (!Number.isFinite(cooldownTime) || cooldownTime > now);
                      const isExpired = application.status === 'withdrawn' && application.can_reapply_at && Number.isFinite(cooldownTime) && cooldownTime <= now;
                      return (
                        <article className={styles.record} key={application.id}>
                          <div className={styles.recordHeading}>
                            <h3>{application.organization_name}</h3>
                            <span className={styles.status} data-status={application.status}>{applicationLabels[application.status]}</span>
                          </div>
                          <p className={styles.recordMeta}>Submitted {formatMoment(application.created_at) ?? 'date unavailable'}</p>
                          {application.status === 'rejected' && application.reason ? <p className={styles.privacyCopy}>Reason: {reasonLabels[application.reason]}. This rejection did not impose a reapplication cooldown; your current request status determines when you can apply again.</p> : null}
                          {application.status === 'approved' && (!actor.eligible || !application.access_ready) ? (
                            <p className={styles.privacyCopy}>Approved, but organization member features remain locked until current PLM eligibility and access are confirmed.</p>
                          ) : null}
                          {cooldown ? <p className={styles.privacyCopy}>You can reapply after {formatMoment(application.can_reapply_at) ?? 'the 24-hour cooldown ends'}.</p> : null}
                          {isExpired ? <p className={styles.privacyCopy}>The 24-hour withdrawal cooldown has ended. You may apply again.</p> : null}
                          {application.status === 'pending' ? (
                            <>
                              <p className={styles.privacyCopy}>Awaiting organization review. This is not a confirmed membership.</p>
                              <p className={styles.privacyCopy}>
                                {application.persona_shared
                                  ? 'You chose to share only your nickname and interests with reviewers while this request is pending.'
                                  : 'You chose not to share profile details with reviewers while this request is pending.'}
                              </p>
                            </>
                          ) : null}
                        </article>
                      );
                    })}
                  </div>
                ) : <p className="panel muted">You have not sent any membership requests.</p>}
              </Feedback>
            )}
          </section>

          <section className="panel stack" aria-labelledby="invitations-title">
            <div className={styles.sectionHeading}>
              <div>
                <p className={styles.eyebrow}>Addressed to your account</p>
                <h2 id="invitations-title">Invitations</h2>
              </div>
            </div>
            {!token || !actor ? (
              <p className="muted">Sign in to see invitations sent to your account.</p>
            ) : (
              <Feedback loading={invitations.loading} error={invitations.error} onRetry={invitations.reload}>
                {ownInvitations.length ? (
                  <div className={styles.recordList}>
                    {ownInvitations.map((invitation) => {
                      const expiry = Date.parse(invitation.expires_at);
                      const expired = invitation.status === 'pending' && (!Number.isFinite(expiry) || now >= expiry);
                      const canRespond = invitation.status === 'pending' && !expired;
                      const visibleStatus = expired ? 'expired' : invitation.status;
                      return (
                        <article className={styles.record} key={invitation.id}>
                          <div className={styles.recordHeading}>
                            <h3>{invitation.organization_name}</h3>
                            <span className={styles.status} data-status={visibleStatus}>{visibleStatus === 'pending' ? 'Invitation pending' : visibleStatus[0].toUpperCase() + visibleStatus.slice(1)}</span>
                          </div>
                          <p className={styles.recordMeta}>Expires {formatMoment(invitation.expires_at) ?? 'date unavailable'}</p>
                          {invitation.status === 'accepted' && (!actor.eligible || !invitation.access_ready) ? (
                            <p className={styles.privacyCopy}>Accepted, but organization member features stay locked until current PLM eligibility and access are confirmed.</p>
                          ) : null}
                          {canRespond ? (
                            <div className={styles.actions}>
                              <button
                                type="button"
                                className="button"
                                disabled={mutationBusy || Boolean(pendingAttempt)}
                                onClick={() => beginMutation({
                                  id: `accept:${invitation.id}`,
                                  label: 'invitation acceptance',
                                  successMessage: `You accepted the invitation to ${invitation.organization_name}.`,
                                  path: `/membership-invitations/${encodeURIComponent(invitation.id)}/accept`,
                                  body: undefined,
                                })}
                              >Accept</button>
                              <button
                                type="button"
                                className="button button-secondary"
                                disabled={mutationBusy || Boolean(pendingAttempt)}
                                onClick={() => beginMutation({
                                  id: `decline:${invitation.id}`,
                                  label: 'invitation decline',
                                  successMessage: `You declined the invitation to ${invitation.organization_name}.`,
                                  path: `/membership-invitations/${encodeURIComponent(invitation.id)}/decline`,
                                  body: undefined,
                                })}
                              >Decline</button>
                            </div>
                          ) : null}
                          {expired ? <p className={styles.privacyCopy}>This invitation has expired and can no longer be accepted.</p> : null}
                        </article>
                      );
                    })}
                  </div>
                ) : <p className="panel muted">You have no membership invitations.</p>}
              </Feedback>
            )}
          </section>
        </aside>
      </div>
    </div>
  );
}
