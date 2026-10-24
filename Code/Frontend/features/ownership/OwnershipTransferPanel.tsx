'use client';

import Link from 'next/link';
import {useCallback, useEffect, useMemo, useRef, useState, useSyncExternalStore, type SyntheticEvent} from 'react';
import {ApiError, api} from '@/lib/api';
import type {components} from '@/lib/api.generated';
import {useT} from '@/lib/i18n';
import type {MembershipRosterItem} from '@/lib/types';
import {usePreferences} from '@/lib/preferences';
import {useSession} from '@/lib/session';
import {
  canLoadOwnershipData,
  captureDecision,
  decisionPayload,
  getOrCreateOfferAttempt,
  isBeforeExpiry,
  isDecisionCurrent,
  matchesOfferAttempt,
  parseExactTimestamp,
  shouldShowAdminOwnershipPanel,
  type OwnershipCreateAttempt,
  type ReviewedOwnershipDecision,
} from './ownership-helpers.mjs';
import styles from './ownership.module.css';

export type OwnershipTransferOut = components['schemas']['OwnershipTransferOut'];

type OwnershipData = {
  context: object;
  transfers: OwnershipTransferOut[];
  roster: MembershipRosterItem[];
  transferError: boolean;
  rosterError: boolean;
  accessLost: boolean;
  notNominee: boolean;
  lastRefreshedAt: number;
};

type ContextMessage = {context: object; key: string; tone: 'error' | 'notice' | 'warning'};
type OwnershipDialog =
  | {context: object; kind: 'create'; nomineeId: string; errorKey: string | null}
  | {context: object; kind: 'decision'; reviewed: ReviewedOwnershipDecision; stale: boolean; errorKey: string | null};

const DESKTOP_QUERY = '(min-width: 768px)';
const statusMessages: Record<OwnershipTransferOut['status'], string> = {
  pending: 'Pending',
  accepted: 'Accepted',
  declined: 'Declined',
  revoked: 'Revoked',
  expired: 'Expired',
};

function subscribeDesktop(onChange: () => void): () => void {
  if (typeof window === 'undefined') return () => {};
  const query = window.matchMedia(DESKTOP_QUERY);
  query.addEventListener('change', onChange);
  return () => query.removeEventListener('change', onChange);
}

function getDesktopSnapshot(): boolean {
  return typeof window !== 'undefined' && window.matchMedia(DESKTOP_QUERY).matches;
}

function subscribeClock(onChange: () => void): () => void {
  if (typeof window === 'undefined') return () => {};
  const timer = window.setInterval(onChange, 1_000);
  return () => window.clearInterval(timer);
}

function getClockSnapshot(): number {
  return Math.floor(Date.now() / 1_000) * 1_000;
}

function getServerClockSnapshot(): number {
  return 0;
}

function formatDeadline(value: string, language: string): string | null {
  const timestamp = parseExactTimestamp(value);
  if (!timestamp) return null;
  try {
    const parts = new Intl.DateTimeFormat(language === 'fil' ? 'fil-PH' : 'en-PH', {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
      fractionalSecondDigits: 3,
      hourCycle: 'h23',
      timeZone: 'Asia/Manila',
      timeZoneName: 'short',
    }).formatToParts(timestamp.epochMilliseconds);
    const exactFraction = timestamp.fraction.length < 3
      ? timestamp.fraction.padEnd(3, '0')
      : timestamp.fraction;
    return parts.map(part => part.type === 'fractionalSecond' ? (exactFraction || '000') : part.value).join('');
  } catch {
    return null;
  }
}

function statusSymbol(status: OwnershipTransferOut['status']): string {
  switch (status) {
    case 'pending': return '◷';
    case 'accepted': return '✓';
    case 'declined': return '↘';
    case 'revoked': return '↺';
    case 'expired': return '⌛';
  }
}

function apiStatus(error: unknown): number {
  return error instanceof ApiError ? error.status : 0;
}

function isUncertain(error: unknown): boolean {
  return !(error instanceof ApiError) || error.status === 0 || error.status >= 500;
}

function upsertTransfer(transfers: OwnershipTransferOut[], next: OwnershipTransferOut): OwnershipTransferOut[] {
  return [next, ...transfers.filter(transfer => transfer.id !== next.id)]
    .sort((first, second) => Date.parse(second.created_at) - Date.parse(first.created_at));
}

export function OwnershipTransferPanel({orgId, role, onChanged}: {
  orgId: string;
  role: string;
  onChanged?: () => void;
}) {
  const t = useT();
  const {preferences: {language}} = usePreferences();
  const {actor, token, version: sessionVersion} = useSession();
  const actorId = actor?.id ?? '';
  const isDesktop = useSyncExternalStore(subscribeDesktop, getDesktopSnapshot, () => false);
  const now = useSyncExternalStore(subscribeClock, getClockSnapshot, getServerClockSnapshot);
  const contextIdentity = useMemo(() => ({
    orgId,
    role,
    actorId,
    eligible: actor?.eligible === true,
    token,
    sessionVersion,
  }), [orgId, role, actorId, actor?.eligible, token, sessionVersion]);
  const canRead = canLoadOwnershipData({
    isDesktop,
    role,
    actorEligible: actor?.eligible === true,
    token,
  });
  const organizationPath = `/organizations/${encodeURIComponent(orgId)}`;
  const transfersPath = `${organizationPath}/ownership-transfers`;
  const [resource, setResource] = useState<OwnershipData | null>(null);
  const data = resource?.context === contextIdentity ? resource : null;
  const [nomination, setNomination] = useState<{context: object; nomineeId: string} | null>(null);
  const [retryNominee, setRetryNominee] = useState<{context: object; nomineeId: string} | null>(null);
  const [createFeedback, setCreateFeedback] = useState<ContextMessage | null>(null);
  const [decisionFeedback, setDecisionFeedback] = useState<ContextMessage | null>(null);
  const [workingContext, setWorkingContext] = useState<object | null>(null);
  const [dialog, setDialog] = useState<OwnershipDialog | null>(null);
  const activeDialog = dialog?.context === contextIdentity && !data?.accessLost && !data?.notNominee ? dialog : null;
  const retryAttemptRef = useRef<OwnershipCreateAttempt | null>(null);
  const mutationControllerRef = useRef<{context: object; controller: AbortController} | null>(null);
  const mutationInFlightRef = useRef(false);
  const refreshRef = useRef<(() => void) | null>(null);
  const onChangedRef = useRef(onChanged);
  const notifiedRef = useRef(new Set<string>());
  const dialogRef = useRef<HTMLDialogElement | null>(null);
  const cancelButtonRef = useRef<HTMLButtonElement | null>(null);
  const restoreFocusRef = useRef<HTMLElement | null>(null);
  const panelRef = useRef<HTMLElement | null>(null);
  const isWorking = workingContext === contextIdentity;
  const activeCreateFeedback = createFeedback?.context === contextIdentity ? createFeedback : null;
  const activeDecisionFeedback = decisionFeedback?.context === contextIdentity ? decisionFeedback : null;
  const activeRetryNominee = retryNominee?.context === contextIdentity ? retryNominee.nomineeId : '';
  const selectedNominee = activeRetryNominee || (nomination?.context === contextIdentity ? nomination.nomineeId : '');
  const lastChecked = data ? formatDeadline(new Date(data.lastRefreshedAt).toISOString(), language) : null;

  const notifyRoleRefresh = useCallback((transfer: OwnershipTransferOut) => {
    if (transfer.status !== 'accepted' || (transfer.from_user_id !== actorId && transfer.nominee_id !== actorId)) return;
    const notificationKey = `${actorId}:${orgId}:${transfer.id}`;
    if (notifiedRef.current.has(notificationKey)) return;
    notifiedRef.current.add(notificationKey);
    try {
      void Promise.resolve(onChangedRef.current?.()).catch(() => {});
    } catch {
      // Keep the transfer response visible even if the workspace refresh fails.
    }
  }, [actorId, orgId]);

  const notifyOwnerAccessLost = useCallback(() => {
    const notificationKey = `${actorId}:${orgId}:access-lost`;
    if (notifiedRef.current.has(notificationKey)) return;
    notifiedRef.current.add(notificationKey);
    try {
      void Promise.resolve(onChangedRef.current?.()).catch(() => {});
    } catch {
      // The membership link remains available if the parent refresh cannot run.
    }
  }, [actorId, orgId]);

  useEffect(() => {
    onChangedRef.current = onChanged;
  }, [onChanged]);

  useEffect(() => () => {
    if (retryAttemptRef.current?.context === contextIdentity) retryAttemptRef.current = null;
    if (mutationControllerRef.current?.context === contextIdentity) {
      mutationControllerRef.current.controller.abort();
      mutationControllerRef.current = null;
      mutationInFlightRef.current = false;
    }
    notifiedRef.current.clear();
  }, [contextIdentity]);

  useEffect(() => {
    if (!canRead || !actorId || !token) return;
    let disposed = false;
    let stopped = false;
    let fetching = false;
    let refreshQueued = false;
    let controller: AbortController | null = null;

    const refresh = async () => {
      if (disposed || stopped) return;
      if (fetching) {
        refreshQueued = true;
        return;
      }
      fetching = true;
      controller = new AbortController();
      const signal = controller.signal;
      let transfers: OwnershipTransferOut[] = [];
      let roster: MembershipRosterItem[] = [];
      let transferError = false;
      let rosterError = false;
      let accessLost = false;
      let notNominee = false;

      try {
        try {
          transfers = await api<OwnershipTransferOut[]>(transfersPath, {token, signal});
        } catch (error) {
          transferError = true;
          if (role === 'owner' && [401, 403].includes(apiStatus(error))) accessLost = true;
          if (role === 'admin' && [401, 403].includes(apiStatus(error))) notNominee = true;
        }

        if (role === 'owner' && !accessLost) {
          try {
            roster = await api<MembershipRosterItem[]>(`${organizationPath}/members`, {token, signal});
          } catch (error) {
            rosterError = true;
            if ([401, 403].includes(apiStatus(error))) accessLost = true;
          }
        }

        if (disposed || signal.aborted) return;
        const visibleTransfers = role === 'admin'
          ? transfers.filter(transfer => transfer.nominee_id === actorId)
          : transfers;
        setResource(previous => {
          const previousContext = previous?.context === contextIdentity ? previous : null;
          const retainedOffers = role === 'admin' && transferError && !notNominee
            ? previousContext?.transfers ?? []
            : visibleTransfers;
          return {
            context: contextIdentity,
            transfers: retainedOffers,
            roster,
            transferError,
            rosterError,
            accessLost,
            notNominee,
            lastRefreshedAt: Date.now(),
          };
        });
        if (accessLost) {
          stopped = true;
          notifyOwnerAccessLost();
        }
        if (notNominee) stopped = true;
        if (!transferError) for (const transfer of visibleTransfers) notifyRoleRefresh(transfer);
      } finally {
        fetching = false;
        if (refreshQueued && !disposed && !stopped) {
          refreshQueued = false;
          void refresh();
        }
      }
    };

    refreshRef.current = () => { void refresh(); };
    const initialRequest = window.setTimeout(() => { void refresh(); }, 0);
    const refreshWhenActive = () => {
      if (document.visibilityState === 'visible' && document.hasFocus()) void refresh();
    };
    const interval = window.setInterval(refreshWhenActive, 15_000);
    window.addEventListener('focus', refreshWhenActive);
    document.addEventListener('visibilitychange', refreshWhenActive);
    return () => {
      disposed = true;
      stopped = true;
      window.clearTimeout(initialRequest);
      window.clearInterval(interval);
      window.removeEventListener('focus', refreshWhenActive);
      document.removeEventListener('visibilitychange', refreshWhenActive);
      controller?.abort();
      if (refreshRef.current) refreshRef.current = null;
    };
  }, [actorId, canRead, contextIdentity, notifyOwnerAccessLost, notifyRoleRefresh, organizationPath, role, token, transfersPath]);

  const candidates = (data?.roster ?? []).filter(member =>
    member.user_id !== actorId && member.role === 'admin' && member.eligible,
  );
  const candidateForSelection = candidates.find(member => member.user_id === selectedNominee);
  const pendingOffer = data?.transfers.find(transfer => transfer.status === 'pending');
  const activeOffers = data?.transfers ?? [];
  const isOwner = role === 'owner';

  function setCurrentResource(update: (previous: OwnershipData) => OwnershipData) {
    setResource(previous => {
      if (previous?.context !== contextIdentity) return previous;
      return update(previous);
    });
  }

  function closeDialog() {
    setDialog(null);
  }

  function rememberDialogTrigger() {
    restoreFocusRef.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
  }

  function openCreateDialog(nomineeId: string) {
    const capturedRetry = matchesOfferAttempt(retryAttemptRef.current, contextIdentity, nomineeId);
    if (!nomineeId || (!capturedRetry && (!candidateForSelection || candidateForSelection.user_id !== nomineeId))) return;
    rememberDialogTrigger();
    setCreateFeedback(null);
    setDialog({context: contextIdentity, kind: 'create', nomineeId, errorKey: null});
  }

  function openDecisionDialog(offer: OwnershipTransferOut, action: ReviewedOwnershipDecision['action']) {
    rememberDialogTrigger();
    setDecisionFeedback(null);
    setDialog({context: contextIdentity, kind: 'decision', reviewed: captureDecision(offer, action), stale: false, errorKey: null});
  }

  const dialogVisible = Boolean(activeDialog);
  useEffect(() => {
    const node = dialogRef.current;
    if (!node) return;
    if (dialogVisible) {
      if (!node.open) {
        node.showModal();
        cancelButtonRef.current?.focus();
      }
    } else if (node.open) {
      node.close();
      window.requestAnimationFrame(() => {
        if (restoreFocusRef.current?.isConnected) restoreFocusRef.current.focus();
        else panelRef.current?.focus();
      });
    }
  }, [dialogVisible]);

  function handleDialogCancel(event: SyntheticEvent<HTMLDialogElement>) {
    event.preventDefault();
    closeDialog();
  }

  async function submitOffer(nomineeId: string) {
    if (!token || !actorId || role !== 'owner' || !canRead || data?.accessLost || isWorking || mutationInFlightRef.current) return;
    const existingAttempt = retryAttemptRef.current;
    const isRetry = matchesOfferAttempt(existingAttempt, contextIdentity, nomineeId);
    if (!isRetry && (pendingOffer || !candidates.some(candidate => candidate.user_id === nomineeId) || data?.transferError || data?.rosterError)) return;
    let attempt: OwnershipCreateAttempt;
    try {
      if (existingAttempt?.context === contextIdentity && existingAttempt.nomineeId !== nomineeId) {
        setCreateFeedback({context: contextIdentity, key: 'The offer status is uncertain. Retry the same request here before starting another.', tone: 'warning'});
        return;
      }
      attempt = getOrCreateOfferAttempt(existingAttempt, contextIdentity, nomineeId, () => window.crypto.randomUUID());
    } catch {
      setCreateFeedback({context: contextIdentity, key: 'A secure request key could not be created. Please use an updated browser.', tone: 'error'});
      return;
    }

    retryAttemptRef.current = attempt;
    setRetryNominee({context: contextIdentity, nomineeId: attempt.nomineeId});
    setCreateFeedback(null);
    setWorkingContext(contextIdentity);
    mutationInFlightRef.current = true;
    const controller = new AbortController();
    mutationControllerRef.current = {context: contextIdentity, controller};
    try {
      const result = await api<OwnershipTransferOut>(transfersPath, {
        method: 'POST',
        token,
        body: attempt.payload,
        signal: controller.signal,
      });
      if (controller.signal.aborted) return;
      retryAttemptRef.current = null;
      setRetryNominee(null);
      setCurrentResource(previous => ({...previous, transfers: upsertTransfer(previous.transfers, result), lastRefreshedAt: Date.now()}));
      notifyRoleRefresh(result);
      setCreateFeedback({context: contextIdentity, key: result.status === 'pending'
        ? 'The ownership offer was sent. Your role stays the same unless the admin accepts.'
        : result.status === 'accepted'
          ? 'Organization ownership was transferred. Review your current role.'
          : statusMessages[result.status], tone: 'notice'});
      setDialog(null);
      void refreshRef.current?.();
    } catch (error) {
      if (controller.signal.aborted) return;
      const status = apiStatus(error);
      if (isUncertain(error)) {
        setCreateFeedback({context: contextIdentity, key: 'The offer status is uncertain. Retry the same request here before starting another.', tone: 'warning'});
        setDialog(current => current?.context === contextIdentity && current.kind === 'create'
          ? {...current, errorKey: 'The offer status is uncertain. Retry the same request here before starting another.'}
          : current);
      } else {
        retryAttemptRef.current = null;
        setRetryNominee(null);
        setDialog(null);
        if (status === 409) {
          setCreateFeedback({context: contextIdentity, key: 'A pending offer must be declined, revoked, or expire before another can be sent.', tone: 'error'});
        } else {
          setCreateFeedback({context: contextIdentity, key: 'The offer could not be sent. Please retry.', tone: 'error'});
        }
        if (status === 401 || status === 403) {
          setCurrentResource(previous => ({...previous, accessLost: true}));
          notifyOwnerAccessLost();
        }
        void refreshRef.current?.();
      }
    } finally {
      if (mutationControllerRef.current?.controller === controller) {
        mutationControllerRef.current = null;
        mutationInFlightRef.current = false;
        setWorkingContext(null);
      }
    }
  }

  function reviewLatestOffer(review: Extract<OwnershipDialog, {kind: 'decision'}>) {
    const latest = data?.transfers.find(transfer => transfer.id === review.reviewed.transferId);
    if (!latest || latest.status !== 'pending') return;
    setDialog({
      context: contextIdentity,
      kind: 'decision',
      reviewed: captureDecision(latest, review.reviewed.action),
      stale: false,
      errorKey: null,
    });
  }

  async function submitDecision(review: Extract<OwnershipDialog, {kind: 'decision'}>) {
    if (!token || !actorId || !canRead || data?.accessLost || data?.notNominee || isWorking || data?.transferError || mutationInFlightRef.current) return;
    const latest = data?.transfers.find(transfer => transfer.id === review.reviewed.transferId);
    if (!isDecisionCurrent(review.reviewed, latest) || review.stale) {
      setDialog(current => current?.context === contextIdentity && current.kind === 'decision'
        ? {...current, stale: true, errorKey: 'This offer changed while you were reviewing it. The latest details are loaded; review them before deciding.'}
        : current);
      void refreshRef.current?.();
      return;
    }
    if (!latest || !formatDeadline(latest.expires_at, language) || !isBeforeExpiry(latest.expires_at, Date.now())) {
      setDialog(current => current?.context === contextIdentity && current.kind === 'decision'
        ? {...current, stale: true, errorKey: 'Deadline unavailable. Decisions are disabled.'}
        : current);
      return;
    }
    if (review.reviewed.action === 'revoke' && (role !== 'owner' || latest.from_user_id !== actorId)) return;
    if (review.reviewed.action !== 'revoke' && (role !== 'admin' || latest.nominee_id !== actorId)) return;

    setWorkingContext(contextIdentity);
    mutationInFlightRef.current = true;
    const controller = new AbortController();
    mutationControllerRef.current = {context: contextIdentity, controller};
    try {
      const result = await api<OwnershipTransferOut>(
        `${transfersPath}/${encodeURIComponent(review.reviewed.transferId)}/decision`,
        {method: 'POST', token, body: decisionPayload(review.reviewed), signal: controller.signal},
      );
      if (controller.signal.aborted) return;
      setCurrentResource(previous => ({...previous, transfers: upsertTransfer(previous.transfers, result), lastRefreshedAt: Date.now()}));
      if (result.status === 'accepted') {
        notifyRoleRefresh(result);
        setDecisionFeedback({context: contextIdentity, key: 'Organization ownership was transferred. Review your current role.', tone: 'notice'});
      } else if (result.status === 'declined') {
        setDecisionFeedback({context: contextIdentity, key: 'The offer was declined.', tone: 'notice'});
      } else if (result.status === 'revoked') {
        setDecisionFeedback({context: contextIdentity, key: 'The offer was revoked.', tone: 'notice'});
      }
      setDialog(null);
      void refreshRef.current?.();
    } catch (error) {
      if (controller.signal.aborted) return;
      const errorKey = apiStatus(error) === 409
        ? 'This offer changed while you were reviewing it. The latest details are loaded; review them before deciding.'
        : 'The ownership decision could not be completed. Refresh and review the offer before retrying.';
      setDialog(current => current?.context === contextIdentity && current.kind === 'decision'
        ? {...current, stale: apiStatus(error) === 409, errorKey}
        : current);
      void refreshRef.current?.();
    } finally {
      if (mutationControllerRef.current?.controller === controller) {
        mutationControllerRef.current = null;
        mutationInFlightRef.current = false;
        setWorkingContext(null);
      }
    }
  }

  if (!canRead) return null;
  if (role === 'admin' && !shouldShowAdminOwnershipPanel({
    dataLoaded: Boolean(data),
    notNominee: Boolean(data?.notNominee),
    requestFailed: Boolean(data?.transferError),
    hasOwnOffer: Boolean(data?.transfers.some(transfer => transfer.nominee_id === actorId)),
  })) return null;

  const showAccessLost = isOwner && data?.accessLost;
  const transferCards = activeOffers.map(offer => {
    const nomineeLabel = data?.roster.find(member => member.user_id === offer.nominee_id)?.label ?? t('Named admin');
    const deadline = formatDeadline(offer.expires_at, language);
    const canAcceptOrDecline = role === 'admin' && !data?.transferError && offer.nominee_id === actorId && offer.status === 'pending';
    const canRevoke = isOwner && !data?.transferError && offer.from_user_id === actorId && offer.status === 'pending';
    return (
      <article className={styles.offer} key={offer.id}>
        <div className={styles.offerHeader}>
          <h3>{isOwner ? t('Offered to {name}', {name: nomineeLabel}) : t('Ownership offer')}</h3>
          <span className={styles.status} data-status={offer.status}>
            <span aria-hidden="true">{statusSymbol(offer.status)}</span>
            {t(statusMessages[offer.status])}
          </span>
        </div>
        {deadline
          ? <p className={styles.muted}>{t('Expires {deadline} (Manila time).', {deadline})}</p>
          : <p className={styles.error} role="status">{t('Deadline unavailable. Decisions are disabled.')}</p>}
        {offer.status === 'pending' && (
          <p className={styles.muted}>
            {isOwner
              ? t('If the admin accepts, you become a member and the admin becomes the owner. Both memberships stay active.')
              : t('If you accept, you become the owner and the current owner becomes a member. Both memberships stay active.')}
            {' '}{isOwner
              ? t('The organization and its events stay available. Existing participation is unchanged.')
              : t('The organization, events, and existing participation stay unchanged.')}
          </p>
        )}
        {(canAcceptOrDecline || canRevoke) && (
          <div className={styles.actions}>
            {canAcceptOrDecline && <>
              <button className="button button-primary" type="button" onClick={() => openDecisionDialog(offer, 'accept')}>
                {t('Accept ownership offer')}
              </button>
              <button className="button button-secondary" type="button" onClick={() => openDecisionDialog(offer, 'decline')}>
                {t('Decline ownership offer')}
              </button>
            </>}
            {canRevoke && <button className="button button-secondary" type="button" onClick={() => openDecisionDialog(offer, 'revoke')}>
              {t('Revoke ownership offer')}
            </button>}
          </div>
        )}
      </article>
    );
  });

  const decisionOffer = activeDialog?.kind === 'decision'
    ? data?.transfers.find(transfer => transfer.id === activeDialog.reviewed.transferId)
    : undefined;
  const decisionDeadline = decisionOffer ? formatDeadline(decisionOffer.expires_at, language) : null;
  const decisionCurrent = activeDialog?.kind === 'decision' && isDecisionCurrent(activeDialog.reviewed, decisionOffer);
  const decisionDeadlineKnown = Boolean(decisionOffer && formatDeadline(decisionOffer.expires_at, language));
  const decisionUnexpired = Boolean(decisionOffer && isBeforeExpiry(decisionOffer.expires_at, now));
  const decisionCanConfirm = Boolean(
    activeDialog?.kind === 'decision' && !data?.transferError && decisionCurrent && !activeDialog.stale && decisionDeadlineKnown && decisionUnexpired && !isWorking,
  );
  const canReviewLatest = Boolean(activeDialog?.kind === 'decision' && !data?.transferError && decisionDeadlineKnown && decisionOffer?.status === 'pending' && (activeDialog.stale || !decisionCurrent));

  return (
    <section className={styles.panel} ref={panelRef} tabIndex={-1} aria-labelledby="ownership-panel-title">
      <div className={styles.heading}>
        <div>
          <h2 id="ownership-panel-title">{t('Organization ownership')}</h2>
          <p className={styles.muted}>{t('Updates every 15 seconds while this page is visible.')}</p>
          {lastChecked && <p className={styles.muted}>{t('Last checked {time} (Manila time).', {time: lastChecked})}</p>}
        </div>
        <button className="button button-secondary" type="button" onClick={() => refreshRef.current?.()}>
          {t('Refresh ownership transfers')}
        </button>
      </div>

      {showAccessLost ? (
        <div className={styles.errorBox} role="alert">
          <p>{t('Your sign-in or organization access has ended.')}</p>
          <Link className="button button-secondary" href="/organizations">{t('Open clubs and memberships')}</Link>
        </div>
      ) : <>
        {isOwner && !data && <p role="status">{t('Loading ownership transfers...')}</p>}
        {data?.transferError && <div className={styles.errorBox} role="alert">
          <p>{t(isOwner ? 'Could not load ownership transfers.' : 'Could not check ownership offers.')}</p>
          <button className="button button-secondary" type="button" onClick={() => refreshRef.current?.()}>{t('Refresh ownership transfers')}</button>
        </div>}
        {isOwner && data?.rosterError && <p className={styles.error} role="alert">{t('Could not load the private staff roster.')}</p>}
        {activeCreateFeedback && <p className={activeCreateFeedback.tone === 'error' ? styles.errorBox : styles.notice} role={activeCreateFeedback.tone === 'error' ? 'alert' : 'status'}>
          {t(activeCreateFeedback.key)}
        </p>}
        {activeDecisionFeedback && <p className={styles.notice} role="status">{t(activeDecisionFeedback.key)}</p>}

        {isOwner && activeRetryNominee && (data?.transferError || data?.rosterError) && <div className={styles.notice}>
          <p>{t('The offer status is uncertain. Retry the same request here before starting another.')}</p>
          <button className="button button-primary" type="button" disabled={isWorking} onClick={() => openCreateDialog(activeRetryNominee)}>
            {t('Retry same offer request')}
          </button>
        </div>}

        {isOwner && !data?.transferError && !data?.rosterError && (
          <div className={styles.nomination}>
            <label>
              {t('Choose an eligible admin')}
              <select
                value={activeRetryNominee || selectedNominee}
                disabled={Boolean(activeRetryNominee) || isWorking || Boolean(pendingOffer)}
                onChange={event => setNomination({context: contextIdentity, nomineeId: event.currentTarget.value})}
              >
                <option value="">{t('Choose an eligible admin')}</option>
                {candidates.map(candidate => <option key={candidate.user_id} value={candidate.user_id}>{candidate.label}</option>)}
                {activeRetryNominee && !candidates.some(candidate => candidate.user_id === activeRetryNominee) && <option value={activeRetryNominee}>{t('Previously nominated admin')}</option>}
              </select>
            </label>
            {candidates.length === 0 && <p className={styles.muted}>{t('No eligible admins are available to receive an offer.')}</p>}
            {pendingOffer && <p className={styles.muted}>{t('A pending offer must be declined, revoked, or expire before another can be sent.')}</p>}
            <button
              className="button button-primary"
              type="button"
              disabled={isWorking || (!activeRetryNominee && (Boolean(pendingOffer) || !candidateForSelection))}
              onClick={() => openCreateDialog(activeRetryNominee || selectedNominee)}
            >
              {t(activeRetryNominee ? 'Retry same offer request' : 'Nominate an admin')}
            </button>
          </div>
        )}

        <div className={styles.offerList}>
          <h3>{t(isOwner ? 'Transfer history' : 'Ownership offers')}</h3>
          {transferCards.length > 0
            ? transferCards
            : isOwner && data && !data.transferError
              ? <p className={styles.muted}>{t('No ownership offers have been made.')}</p>
              : null}
        </div>
      </>}

      <dialog
        ref={dialogRef}
        className={styles.dialog}
        aria-modal="true"
        aria-labelledby="ownership-confirmation-title"
        aria-describedby="ownership-confirmation-description"
        onCancel={handleDialogCancel}
      >
        <div className={styles.dialogContent}>
          <h2 id="ownership-confirmation-title">
            {t(activeDialog?.kind === 'create' ? 'Confirm offer' : 'Confirm ownership transfer')}
          </h2>
          <div id="ownership-confirmation-description" className={styles.facts}>
            {activeDialog?.kind === 'create' ? (
              <>
                <p>{t('If the admin accepts, you become a member and the admin becomes the owner. Both memberships stay active.')}</p>
                <p>{t('The organization and its events stay available. Existing participation is unchanged.')}</p>
                <p>{t('The nominee has seven days to accept. The offer expires at the exact deadline shown after it is sent.')}</p>
                {activeDialog.errorKey && <p className={styles.error} role="alert">{t(activeDialog.errorKey)}</p>}
              </>
            ) : activeDialog?.kind === 'decision' ? (
              <>
                {activeDialog.reviewed.action === 'revoke' ? (
                  <>
                    <p>{t('The offer will be revoked. The current owner stays the owner.')}</p>
                    <p>{t('The organization, events, and existing participation stay unchanged.')}</p>
                  </>
                ) : activeDialog.reviewed.action === 'decline' ? (
                  <>
                    <p>{t('If you decline, the offer ends and the current owner stays the owner.')}</p>
                    <p>{t('The organization, events, and existing participation stay unchanged.')}</p>
                  </>
                ) : (
                  <>
                    <p>{t('If you accept, you become the owner and the current owner becomes a member. Both memberships stay active.')}</p>
                    <p>{t('The organization, events, and existing participation stay unchanged.')}</p>
                  </>
                )}
                {decisionDeadline
                  ? <p>{t('Expires {deadline} (Manila time).', {deadline: decisionDeadline})}</p>
                  : <p className={styles.error} role="status">{t('Deadline unavailable. Decisions are disabled.')}</p>}
                {activeDialog.stale && !activeDialog.errorKey && <p className={styles.error} role="alert">{t('This offer changed while you were reviewing it. The latest details are loaded; review them before deciding.')}</p>}
                {!activeDialog.stale && !decisionCurrent && decisionOffer?.status !== 'pending' && <p className={styles.error} role="status">{t('This offer is no longer pending.')}</p>}
                {activeDialog.errorKey && <p className={styles.error} role="alert">{t(activeDialog.errorKey)}</p>}
              </>
            ) : null}
          </div>
          {activeDecisionFeedback && <p role="status">{t(activeDecisionFeedback.key)}</p>}
          <div className={styles.actions}>
            <button className="button button-secondary" type="button" ref={cancelButtonRef} onClick={closeDialog}>
              {t('Cancel')}
            </button>
            {activeDialog?.kind === 'create' && <button
              className="button button-primary"
              type="button"
              disabled={isWorking}
              onClick={() => { void submitOffer(activeDialog.nomineeId); }}
            >
              {t(isWorking ? 'Sending offer...' : activeRetryNominee ? 'Retry same offer request' : 'Send ownership offer')}
            </button>}
            {activeDialog?.kind === 'decision' && canReviewLatest && <button
              className="button button-secondary"
              type="button"
              disabled={isWorking}
              onClick={() => reviewLatestOffer(activeDialog)}
            >
              {t('Review latest offer')}
            </button>}
            {activeDialog?.kind === 'decision' && <button
              className="button button-primary"
              type="button"
              disabled={!decisionCanConfirm}
              onClick={() => { void submitDecision(activeDialog); }}
            >
              {t(isWorking ? 'Saving decision...' : activeDialog.reviewed.action === 'accept'
                ? 'Accept'
                : activeDialog.reviewed.action === 'decline'
                  ? 'Decline'
                  : 'Revoke')}
            </button>}
          </div>
        </div>
      </dialog>
    </section>
  );
}
