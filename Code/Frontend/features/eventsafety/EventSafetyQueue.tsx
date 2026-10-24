'use client';

import {useCallback, useEffect, useRef, useState, type MouseEvent} from 'react';
import {ApiError, api} from '@/lib/api';
import {formatDate, formatTime} from '@/lib/date';
import {usePreferences} from '@/lib/preferences';
import {captureSafetyCommand, eventReportActions, eventReportDecisionOutcome, isUncertainSafetyFailure, matchesSafetyCommand, parseBoundedEventEvidence, type SafetyCommand} from './safety-helpers.mjs';
import type {EventReportDecisionInput, EventReportReview, SafetyAuditOut, SafetyReportAction, SafetyReportReason} from './types';
import {SafetyDialog} from './SafetyDialog';
import {EventSafetyControls} from './EventSafetyControls';
import {OrganizationSuspensionPanel} from './OrganizationSuspensionPanel';
import {useDesktopManagement, useSafetyResource, useSafetyTranslate} from './use-safety-ui';
import styles from './eventsafety.module.css';

function statusOf(error: unknown): number | null {
  return error instanceof ApiError ? error.status : null;
}

type Feedback = {contextKey: string; key: string; tone: 'success' | 'warning' | 'error'};
type Confirmation = {
  contextKey: string;
  reportId: string;
  action: SafetyReportAction;
  reportVersion: number;
  eventVersion: number;
};

const reasonLabels: Record<SafetyReportReason, string> = {
  safety: 'Safety concern',
  deception: 'Deception',
};

const statusLabels: Record<EventReportReview['status'], string> = {
  open: 'Open',
  escalated: 'Escalated',
  dismissed: 'Dismissed',
  hidden: 'Hidden',
  removed: 'Removed',
  upheld: 'Upheld',
  expired: 'Expired',
};

const actionLabels: Record<SafetyReportAction, string> = {
  dismiss: 'Dismiss',
  hide: 'Hide event from public discovery',
  remove: 'Permanently remove event',
  uphold: 'Uphold report',
};

const confirmationText: Record<SafetyReportAction, string> = {
  dismiss: 'Dismiss this report without changing event visibility?',
  hide: 'Hide this event using the review authority for this report?',
  remove: 'Permanently remove this event? Existing registrations are cancelled and records are retained.',
  uphold: 'Uphold this report decision? Event visibility is unchanged by this action.',
};

function historyAction(action: SafetyAuditOut['action']): string {
  switch (action) {
    case 'report': return 'Report submitted';
    case 'dismiss': return 'Dismiss';
    case 'hide': return 'Hide event from public discovery';
    case 'remove': return 'Permanently remove event';
    case 'uphold': return 'Uphold report';
    case 'expire': return 'Report expired';
    case 'restore': return 'Restore the hide you manage';
    case 'cancel': return 'Cancel event';
    case 'suspend': return 'Suspend organization';
    case 'resume': return 'Resume organization now';
  }
}

export function EventSafetyQueue({token, orgId}: {token: string; orgId?: string}) {
  const isDesktop = useDesktopManagement();
  if (!isDesktop) return null;
  return <EventSafetyQueueContext key={JSON.stringify([orgId ?? null, token])} token={token} orgId={orgId} />;
}

function EventSafetyQueueContext({token, orgId}: {token: string; orgId?: string}) {
  const t = useSafetyTranslate();
  const {preferences} = usePreferences();
  const contextKey = JSON.stringify([orgId ?? null, token]);
  const path = orgId
    ? `/moderation/event-reports?org_id=${encodeURIComponent(orgId)}`
    : '/moderation/event-reports';
  const [expanded, setExpanded] = useState(false);
  const [resourceEpoch, setResourceEpoch] = useState(0);
  const active = expanded && Boolean(token);
  const loader = useCallback(async (signal: AbortSignal) => {
    const result = await api<EventReportReview[]>(path, {token, signal});
    if (!Array.isArray(result)) throw new Error('The event safety queue response is invalid.');
    return result.slice(0, 100);
  }, [path, token]);
  const resource = useSafetyResource(active, JSON.stringify([contextKey, resourceEpoch]), loader);
  const [selected, setSelected] = useState<{contextKey: string; reportId: string} | null>(null);
  const [confirmation, setConfirmation] = useState<Confirmation | null>(null);
  const [attempt, setAttempt] = useState<{contextKey: string; command: SafetyCommand; reportId: string} | null>(null);
  const attemptRef = useRef<SafetyCommand | null>(null);
  const mutationRef = useRef<AbortController | null>(null);
  const busyRef = useRef(false);
  const [busy, setBusy] = useState(false);
  const [feedback, setFeedback] = useState<Feedback | null>(null);
  const [now, setNow] = useState(() => Date.now());
  const returnFocusRef = useRef<HTMLElement | null>(null);

  useEffect(() => {
    return () => {
      mutationRef.current?.abort();
      mutationRef.current = null;
      attemptRef.current = null;
    };
  }, []);

  useEffect(() => {
    if (!active) return;
    const timer = window.setInterval(() => setNow(Date.now()), 30_000);
    return () => window.clearInterval(timer);
  }, [active, contextKey]);

  async function sendDecision(command: SafetyCommand, reportId: string, retry: boolean) {
    if (!active || busyRef.current || !matchesSafetyCommand(command, contextKey)) return;
    if (retry) {
      if (attemptRef.current !== command) return;
    } else if (attemptRef.current) {
      return;
    }
    if (!retry) {
      attemptRef.current = command;
      setAttempt({contextKey, command, reportId});
    }
    busyRef.current = true;
    setBusy(true);
    const controller = new AbortController();
    mutationRef.current?.abort();
    mutationRef.current = controller;
    try {
      const result = await api<EventReportReview>(command.path, {
        method: 'POST', token, body: command.body as EventReportDecisionInput, signal: controller.signal,
      });
      if (controller.signal.aborted) return;
      const outcome = eventReportDecisionOutcome(result, reportId, command.body.action, command.body.version);
      if (outcome === 'uncertain') {
        throw new Error('The report decision could not be confirmed.');
      }
      attemptRef.current = null;
      setAttempt(null);
      if (outcome === 'expired') {
        setFeedback({contextKey, key: 'This report expired before your decision was applied. No decision was saved. Refresh the queue to review the latest status.', tone: 'warning'});
      } else {
        setFeedback({contextKey, key: 'The report decision was saved.', tone: 'success'});
      }
    } catch (error) {
      if (controller.signal.aborted) return;
      const status = statusOf(error);
      if (status === 409) {
        attemptRef.current = null;
        setAttempt(null);
        setFeedback({contextKey, key: 'This report or event changed while you were reviewing it. Refresh the queue and review the latest status before deciding again.', tone: 'warning'});
      } else if (isUncertainSafetyFailure(status)) {
        setFeedback({contextKey, key: 'The report decision could not be confirmed. Retry the same request.', tone: 'warning'});
      } else {
        attemptRef.current = null;
        setAttempt(null);
        setFeedback({
          contextKey,
          key: status === 401 || status === 403
            ? 'Your sign-in or staff access has ended.'
            : 'The report decision was rejected. Refresh the queue before trying again.',
          tone: 'error',
        });
      }
    } finally {
      if (!controller.signal.aborted) {
        if (mutationRef.current === controller) mutationRef.current = null;
        busyRef.current = false;
        setBusy(false);
        resource.refresh();
      }
    }
  }

  function openConfirmation(report: EventReportReview, action: SafetyReportAction, event: MouseEvent<HTMLButtonElement>) {
    if (!resource.fresh || busyRef.current || attemptRef.current || !eventReportActions(report, now).includes(action)) return;
    returnFocusRef.current = event.currentTarget;
    setConfirmation({
      contextKey,
      reportId: report.id,
      action,
      reportVersion: report.version,
      eventVersion: report.event_version,
    });
  }

  function confirmDecision() {
    const reviewed = confirmation;
    const reports = resource.data ?? [];
    const current = reviewed && reports.find(report => report.id === reviewed.reportId);
    setConfirmation(null);
    if (!reviewed || reviewed.contextKey !== contextKey || !resource.fresh || !current ||
      current.version !== reviewed.reportVersion || current.event_version !== reviewed.eventVersion ||
      !eventReportActions(current, now).includes(reviewed.action)) {
      setFeedback({contextKey, key: 'This report or event changed while you were reviewing it. Refresh the queue and review the latest status before deciding again.', tone: 'warning'});
      resource.refresh();
      return;
    }
    try {
      const command = captureSafetyCommand(contextKey,
        `/moderation/event-reports/${encodeURIComponent(reviewed.reportId)}/decision`,
        {
          action: reviewed.action,
          version: reviewed.reportVersion,
          event_version: reviewed.eventVersion,
          client_key: window.crypto.randomUUID(),
        });
      void sendDecision(command, reviewed.reportId, false);
    } catch {
      setFeedback({contextKey, key: 'A secure request key could not be created. Please use an updated browser.', tone: 'error'});
    }
  }

  const reports = resource.data ?? [];
  const chosenId = selected?.contextKey === contextKey && reports.some(report => report.id === selected.reportId)
    ? selected.reportId
    : reports[0]?.id ?? null;
  const chosen = reports.find(report => report.id === chosenId) ?? null;
  const visibleAttempt = attempt?.contextKey === contextKey ? attempt : null;
  const visibleFeedback = feedback?.contextKey === contextKey ? feedback : null;
  const deadline = chosen ? Date.parse(chosen.deadline) : NaN;
  const canReadEvidence = Boolean(resource.fresh && chosen && eventReportActions(chosen, now).length && chosen.evidence !== null);
  const snapshot = canReadEvidence && chosen?.evidence ? parseBoundedEventEvidence(chosen.evidence) : null;
  const actionChoices = chosen ? eventReportActions(chosen, now) : [];
  const actionsDisabled = !resource.fresh || busy || Boolean(visibleAttempt);

  return (
    <section className={`${styles.root} ${styles.desktopOnly}`} aria-label={t('Event safety reports')}>
      <button className="button button-secondary" type="button" aria-expanded={expanded} onClick={() => {
        if (!expanded) {
          setResourceEpoch(value => value + 1);
          setNow(Date.now());
        }
        setExpanded(value => !value);
      }}>
        {t('Event safety reports')}
      </button>
      {expanded && (
        <div className={styles.panel} aria-busy={resource.loading || busy}>
          <div className={styles.heading}>
            <h3>{t('Event safety reports')}</h3>
            <button className="button button-secondary" type="button" disabled={resource.loading} onClick={resource.refresh}>{t('Refresh report queue')}</button>
          </div>
          {resource.loading && <p className={styles.muted} role="status">{t('Loading event safety reports…')}</p>}
          {resource.status === 'forbidden' && <p className="panel error" role="alert">{t('Your sign-in or staff access has ended.')}</p>}
          {resource.status === 'error' && <div className={styles.feedback} data-tone="error" role="alert"><p>{t('The event safety report queue could not be loaded.')}</p><button className="button button-secondary" type="button" onClick={resource.refresh}>{t('Retry loading event reports')}</button></div>}
          {visibleFeedback && <p className={styles.feedback} data-tone={visibleFeedback.tone} role={visibleFeedback.tone === 'error' ? 'alert' : 'status'}>{t(visibleFeedback.key)}</p>}
          {visibleAttempt && <div className={styles.attempt}><p>{t('The pending decision for report {reportId} could not be confirmed. Retry will resend that exact request.', {reportId: visibleAttempt.reportId})}</p><button className="button button-secondary" type="button" disabled={busy} onClick={() => void sendDecision(visibleAttempt.command, visibleAttempt.reportId, true)}>{t(busy ? 'Saving report decision…' : 'Retry same report decision')}</button></div>}
          {resource.fresh && reports.length === 0 && <p className={styles.muted}>{t('No event safety reports are available.')}</p>}
          {reports.length > 0 && (
            <div className={styles.queue}>
              <div>
                <h4>{t('Reports ({count})', {count: reports.length})}</h4>
                <ul className={styles.reportList}>
                  {reports.map(report => (
                    <li key={report.id}>
                      <button
                        className={styles.reportChoice}
                        type="button"
                        aria-pressed={report.id === chosenId}
                        onClick={() => setSelected({contextKey, reportId: report.id})}
                      >
                        <strong>{t(reasonLabels[report.reason])}</strong>
                        <span>{t(statusLabels[report.status])} · {report.id}</span>
                      </button>
                    </li>
                  ))}
                </ul>
              </div>
              {chosen ? (
                <article className={styles.reportDetails} aria-label={t('Event safety report')}>
                  <div className={styles.heading}>
                    <h3>{t('Event safety report')}</h3>
                    <span className={styles.status} data-active={['open', 'escalated'].includes(chosen.status)}>{t(statusLabels[chosen.status])}</span>
                  </div>
                  <dl className={styles.metadata}>
                    <div><dt>{t('Reason')}</dt><dd>{t(reasonLabels[chosen.reason])}</dd></div>
                    <div><dt>{t('Review stage')}</dt><dd>{t(chosen.stage === 'organization' ? 'Organization review' : 'Platform review')}</dd></div>
                    <div><dt>{t('Report reference')}</dt><dd>{chosen.id}</dd></div>
                    <div><dt>{t('Event reference')}</dt><dd>{chosen.event_id}</dd></div>
                    <div><dt>{t('Current event review version')}</dt><dd>{chosen.event_version}</dd></div>
                    <div><dt>{t('Review deadline')}</dt><dd><time dateTime={chosen.deadline}>{Number.isFinite(deadline) ? `${formatDate(chosen.deadline, preferences.language)} · ${formatTime(chosen.deadline, preferences.language)} (${t('Manila time')})` : t('Evidence is unavailable after the review deadline or once the report is resolved.')}</time></dd></div>
                  </dl>
                  <section className={styles.evidence} aria-label={t('Retained event snapshot')}>
                    <h4>{t('Retained event snapshot')}</h4>
                    {snapshot ? (
                      <dl>
                        {(['title', 'summary', 'description', 'venue_name', 'venue_address'] as const).filter(field => typeof snapshot[field] === 'string').map(field => (
                          <div key={field}>
                            <dt>{t(field === 'title' ? 'Reported title' : field === 'summary' ? 'Summary' : field === 'description' ? 'Description' : field === 'venue_name' ? 'Venue' : 'Address')}</dt>
                            <dd>{snapshot[field]}</dd>
                          </div>
                        ))}
                      </dl>
                    ) : <p className={styles.muted}>{canReadEvidence ? t('The stored event snapshot cannot be displayed.') : t('Evidence is unavailable after the review deadline or once the report is resolved.')}</p>}
                  </section>
                  <section className={styles.evidence} aria-label={t('Decision history')}>
                    <h4>{t('Decision history')}</h4>
                    {chosen.decisions.length ? (
                      <ol className={styles.history}>
                        {chosen.decisions.slice(-8).reverse().map(decision => {
                          const stamp = Date.parse(decision.created_at);
                          return <li key={decision.id}>{t('Decision: {action}', {action: t(historyAction(decision.action))})}{Number.isFinite(stamp) && <> · <time dateTime={decision.created_at}>{formatDate(decision.created_at, preferences.language)} · {formatTime(decision.created_at, preferences.language)}</time></>}</li>;
                        })}
                      </ol>
                    ) : <p className={styles.muted}>{t('No decisions have been recorded.')}</p>}
                  </section>
                  {actionChoices.length > 0 && resource.fresh && <div className={styles.actions}>
                    {actionChoices.map(action => <button
                      key={action}
                      className={`button ${action === 'remove' ? 'button-danger' : 'button-secondary'}`}
                      type="button"
                      disabled={actionsDisabled}
                      onClick={event => openConfirmation(chosen, action, event)}
                    >{t(actionLabels[action])}</button>)}
                  </div>}
                  {!orgId && <>
                    <EventSafetyControls key={`safety:${token}:${chosen.event_id}`} eventId={chosen.event_id} token={token} />
                    <OrganizationSuspensionPanel key={`suspension:${token}:${chosen.org_id}`} orgId={chosen.org_id} token={token} />
                  </>}
                </article>
              ) : <p className={styles.muted}>{t('Select a report to review its permitted event snapshot and history.')}</p>}
            </div>
          )}
          {reports.length > 0 && !resource.fresh && !resource.loading && <p className={styles.muted} role="status">{t('Refreshing the latest event safety reports…')}</p>}
        </div>
      )}
      <SafetyDialog
        open={expanded && Boolean(confirmation?.contextKey === contextKey)}
        title={confirmation ? t(actionLabels[confirmation.action]) : ''}
        description={confirmation ? t(confirmationText[confirmation.action]) : ''}
        confirmLabel={confirmation ? t(actionLabels[confirmation.action]) : t('Confirm')}
        confirmDisabled={busy}
        onCancel={() => setConfirmation(null)}
        onConfirm={confirmDecision}
        returnFocusRef={returnFocusRef}
        t={t}
      />
    </section>
  );
}
