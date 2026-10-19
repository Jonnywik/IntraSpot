'use client';

import { useEffect, useId, useState } from 'react';
import { ApiError, api } from '@/lib/api';
import { formatDate, formatTime } from '@/lib/date';
import { useT } from '@/lib/i18n';
import { usePreferences } from '@/lib/preferences';
import type { AnnouncementReportReceipt, AnnouncementReportReview } from '@/lib/types';
import { useApiResource } from '@/lib/use-api-resource';
import styles from './announcement-report-queue.module.css';

type DecisionAction = 'dismiss' | 'hide' | 'restore' | 'remove';

const EMPTY_REPORTS: AnnouncementReportReview[] = [];

const reasonLabels: Record<AnnouncementReportReview['reason'], string> = {
  harassment: 'Harassment',
  spam: 'Spam',
  deception: 'Deception',
  impersonation: 'Impersonation',
  other: 'Other',
};

const statusLabels: Record<AnnouncementReportReview['status'], string> = {
  open: 'Open',
  dismissed: 'Dismissed',
  hidden: 'Hidden',
  restored: 'Restored',
  removed: 'Removed',
  expired: 'Expired',
};

const actionLabels: Record<DecisionAction, string> = {
  dismiss: 'Dismiss',
  hide: 'Hide announcement',
  restore: 'Restore announcement',
  remove: 'Remove announcement',
};

const auditLabels: Record<AnnouncementReportReview['decisions'][number]['action'], string> = {
  dismiss: 'Dismiss report',
  hide: 'Hide',
  restore: 'Restore',
  remove: 'Remove',
  expire: 'Expire',
};

function deadlinePassed(report: AnnouncementReportReceipt, currentTime: number): boolean {
  const deadline = Date.parse(report.deadline);
  return !Number.isFinite(deadline) || deadline <= currentTime;
}

function evidenceIsAvailable(report: AnnouncementReportReview, currentTime: number): boolean {
  return report.status === 'open' && !deadlinePassed(report, currentTime) && report.evidence !== null;
}

function availableActions(report: AnnouncementReportReview, currentTime: number): DecisionAction[] {
  if (report.status === 'open') {
    if (deadlinePassed(report, currentTime)) return [];
    if (report.post_state === 'visible') return ['dismiss', 'hide', 'remove'];
    if (report.post_state === 'hidden') return ['dismiss', 'remove'];
    return ['dismiss'];
  }
  if (report.status === 'hidden') {
    return report.post_state === 'hidden' ? ['restore', 'remove'] : ['remove'];
  }
  return [];
}

function parseEvidenceSnapshot(evidence: string): { title: string; body: string | null } | null {
  try {
    const parsed: unknown = JSON.parse(evidence);
    if (typeof parsed !== 'object' || parsed === null || Array.isArray(parsed)) return null;
    const snapshot = parsed as { title?: unknown; body?: unknown };
    if (typeof snapshot.title !== 'string') return null;
    if (snapshot.body !== null && typeof snapshot.body !== 'string') return null;
    return { title: snapshot.title, body: snapshot.body };
  } catch {
    return null;
  }
}

function AnnouncementState({state, t}: {
  state: AnnouncementReportReview['post_state'];
  t: ReturnType<typeof useT>;
}) {
  const label = state === 'visible' ? 'Visible' : state === 'hidden' ? 'Hidden' : 'Removed';
  return <>{t(label)}</>;
}

function ReportDetails({report, t, language, currentTime}: {
  report: AnnouncementReportReview;
  t: ReturnType<typeof useT>;
  language: 'en' | 'fil';
  currentTime: number;
}) {
  const deadline = Date.parse(report.deadline);
  const canReadEvidence = evidenceIsAvailable(report, currentTime);
  const snapshot = canReadEvidence && report.evidence ? parseEvidenceSnapshot(report.evidence) : null;
  const history = report.decisions.slice(-8).reverse();

  return (
    <div className={styles.reportDetails}>
      <header className={styles.detailHeading}>
        <div>
          <div className={styles.titleLine}>
            <h3>{t('Announcement safety report')}</h3>
            <span className={styles.statusTag}>{t(statusLabels[report.status])}</span>
          </div>
          <p className={styles.reportMeta}>{t('Reason')}: {t(reasonLabels[report.reason])}</p>
        </div>
      </header>

      <dl className={styles.detailsGrid}>
        <div className={styles.detailField}>
          <dt>{t('Review deadline')}</dt>
          <dd>
            <time dateTime={report.deadline}>
              {formatDate(report.deadline, language)} · {formatTime(report.deadline, language)} ({t('Manila time')})
            </time>
          </dd>
        </div>
        <div className={styles.detailField}>
          <dt>{t('Current announcement state')}</dt>
          <dd><AnnouncementState state={report.post_state} t={t} /></dd>
        </div>
        <div className={styles.detailField}>
          <dt>{t('Current announcement version')}</dt>
          <dd>{report.post_version}</dd>
        </div>
        <div className={styles.detailField}>
          <dt>{t('Reported version')}</dt>
          <dd>{report.reported_version}</dd>
        </div>
        <div className={styles.detailField}>
          <dt>{t('Report ID')}</dt>
          <dd className={styles.identifier}>{report.id}</dd>
        </div>
        <div className={styles.detailField}>
          <dt>{t('Organization ID')}</dt>
          <dd className={styles.identifier}>{report.org_id}</dd>
        </div>
        <div className={styles.detailField}>
          <dt>{t('Announcement ID')}</dt>
          <dd className={styles.identifier}>{report.announcement_id}</dd>
        </div>
        <div className={styles.detailField}>
          <dt>{t('Reporter ID')}</dt>
          <dd className={styles.identifier}>{report.reporter_id}</dd>
        </div>
        <div className={styles.detailField}>
          <dt>{t('Subject author ID')}</dt>
          <dd className={styles.identifier}>{report.subject_user_id}</dd>
        </div>
      </dl>

      <section className={styles.detailSection} aria-labelledby={`announcement-evidence-${report.id}`}>
        <h4 id={`announcement-evidence-${report.id}`}>{t('Retained evidence snapshot')}</h4>
        {snapshot ? (
          <dl className={styles.evidenceFields}>
            <div>
              <dt>{t('Reported title')}</dt>
              <dd>{snapshot.title}</dd>
            </div>
            <div>
              <dt>{t('Reported body')}</dt>
              <dd>{snapshot.body ?? ''}</dd>
            </div>
          </dl>
        ) : (
          <p className={styles.muted}>
            {canReadEvidence
              ? t('The stored evidence snapshot cannot be displayed.')
              : t('Evidence is unavailable after the review deadline or once the case is resolved.')}
          </p>
        )}
      </section>

      <section className={styles.detailSection} aria-labelledby={`announcement-history-${report.id}`}>
        <h4 id={`announcement-history-${report.id}`}>{t('Decision and expiry history')}</h4>
        {!history.length ? (
          <p className={styles.muted}>{t('No actions have been recorded.')}</p>
        ) : (
          <ol className={styles.auditList}>
            {history.map(decision => (
              <li key={decision.id}>
                <span>{t('Decision: {action}', {action: t(auditLabels[decision.action])})}</span>
                <span className={styles.identifier}>{decision.reviewer_id ?? ''}</span>
                <time dateTime={decision.created_at}>
                  {formatDate(decision.created_at, language)} · {formatTime(decision.created_at, language)} ({t('Manila time')})
                </time>
              </li>
            ))}
          </ol>
        )}
      </section>
      {Number.isFinite(deadline) && deadline <= currentTime && report.status === 'open' && (
        <p className={styles.deadlineNotice} role="status">
          {t('Evidence is unavailable after the review deadline or once the case is resolved.')}
        </p>
      )}
    </div>
  );
}

export function AnnouncementReportQueue({token}: {token: string}) {
  const t = useT();
  const {preferences} = usePreferences();
  const headingId = useId();
  const queue = useApiResource<AnnouncementReportReview[]>('/moderation/announcement-reports', token);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const reports = queue.data ?? EMPTY_REPORTS;
  const effectiveSelectedId = reports.length
    ? selectedId && reports.some(report => report.id === selectedId) ? selectedId : reports[0].id
    : null;
  const detail = useApiResource<AnnouncementReportReview>(
    effectiveSelectedId ? `/moderation/announcement-reports/${effectiveSelectedId}` : null,
    token,
  );
  const [currentTime, setCurrentTime] = useState(() => Date.now());
  const [workingAction, setWorkingAction] = useState<DecisionAction | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [decisionError, setDecisionError] = useState<string | null>(null);
  const selected = detail.data;
  const actions = selected ? availableActions(selected, currentTime) : [];
  const selectedDeadline = selected?.deadline ?? null;

  useEffect(() => {
    if (!selectedDeadline) return;
    const deadline = Date.parse(selectedDeadline);
    if (!Number.isFinite(deadline)) return;
    const timeout = window.setTimeout(
      () => setCurrentTime(Date.now()),
      Math.max(0, deadline - Date.now()) + 5,
    );
    return () => window.clearTimeout(timeout);
  }, [selectedDeadline]);

  function refresh() {
    setNotice(null);
    setDecisionError(null);
    queue.reload();
    detail.reload();
  }

  async function decide(action: DecisionAction) {
    if (!selected) return;
    if (action === 'remove' && !window.confirm(t(
      'Remove this announcement? This permanently removes its body from public access. The safety report and audit record are retained.',
    ))) return;

    setWorkingAction(action);
    setNotice(null);
    setDecisionError(null);
    try {
      await api<AnnouncementReportReview>(
        `/moderation/announcement-reports/${selected.id}/decision`,
        {
          token,
          method: 'POST',
          body: {action},
          ...(action === 'hide' || action === 'restore' || action === 'remove'
            ? {ifMatch: String(selected.post_version)}
            : {}),
        },
      );
      setNotice(t('The report decision was saved.'));
      queue.reload();
      detail.reload();
    } catch (error) {
      if (error instanceof ApiError && error.status === 409) {
        setDecisionError(t('This announcement changed since it was loaded. Refresh and review the latest version before trying again.'));
        queue.reload();
        detail.reload();
      } else if (error instanceof ApiError && (error.status === 403 || error.status === 404)) {
        setDecisionError(t('This report can no longer be changed.'));
      } else {
        setDecisionError(t('The decision could not be saved. Refresh the report and try again.'));
      }
    } finally {
      setWorkingAction(null);
    }
  }

  return (
    <section className={styles.queue} aria-labelledby={headingId}>
      <header className={styles.queueHeading}>
        <div>
          <h2 id={headingId}>{t('Announcement safety report queue')}</h2>
          <p className={styles.queueDescription}>
            {t('Platform-only review. Reporting never hides an announcement automatically.')}
          </p>
        </div>
        <button className="button button-secondary" type="button" onClick={refresh}>
          {t('Refresh queue')}
        </button>
      </header>

      {notice && <p className={'success panel ' + styles.feedback} role="status">{notice}</p>}
      {decisionError && (
        <div className={'error panel ' + styles.feedback} role="alert">
          <p>{decisionError}</p>
          <button className="button button-secondary" type="button" onClick={refresh}>{t('Refresh report')}</button>
        </div>
      )}
      {queue.loading && !queue.data && (
        <p className={styles.feedback} role="status">{t('Loading announcement safety reports…')}</p>
      )}
      {queue.error && (
        <div className={'error panel ' + styles.feedback} role="alert">
          <p>{t('The announcement report queue could not be loaded.')}</p>
          <button className="button button-secondary" type="button" onClick={queue.reload}>{t('Retry loading reports')}</button>
        </div>
      )}
      {!queue.loading && !queue.error && queue.data && (
        <div className={styles.layout}>
          <section className={styles.list} aria-label={t('Reports ({count})', {count: reports.length})}>
            <h3 className={styles.listHeading}>{t('Reports ({count})', {count: reports.length})}</h3>
            {!reports.length ? (
              <p className={styles.emptyState}>{t('No announcement reports are available.')}</p>
            ) : (
              <ul className={styles.reportList}>
                {reports.map(report => (
                  <li key={report.id}>
                    <button
                      className={styles.reportButton}
                      type="button"
                      aria-pressed={effectiveSelectedId === report.id}
                      onClick={() => {
                        setSelectedId(report.id);
                        setNotice(null);
                        setDecisionError(null);
                      }}
                    >
                      <span className={styles.reportTitle}>{t(reasonLabels[report.reason])} · {report.announcement_id}</span>
                      <span className={styles.reportMeta}>{t(statusLabels[report.status])} · {t('Review deadline')}</span>
                      <span className={styles.reportMeta}>
                        {formatDate(report.deadline, preferences.language)} · {formatTime(report.deadline, preferences.language)} ({t('Manila time')})
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </section>

          <section className={styles.detail} aria-label={t('Selected report details')} aria-live="polite">
            {!effectiveSelectedId ? (
              <p className={styles.emptyState}>{t('Select a report to inspect its permitted evidence and action history.')}</p>
            ) : detail.loading ? (
              <p className={styles.inlineStatus} role="status">{t('Loading report details…')}</p>
            ) : detail.error ? (
              <div className="error panel" role="alert">
                <p>{t('The selected report could not be loaded.')}</p>
                <button className="button button-secondary" type="button" onClick={detail.reload}>{t('Retry loading report')}</button>
              </div>
            ) : selected ? (
              <ReportDetails report={selected} t={t} language={preferences.language} currentTime={currentTime} />
            ) : null}

            {selected && !detail.loading && !detail.error && actions.length > 0 && (
              <div className={styles.decisionActions} role="group" aria-label={t('Report decisions')}>
                {actions.map(action => (
                  <button
                    key={action}
                    className={action === 'remove' ? 'button button-danger' : 'button button-secondary'}
                    type="button"
                    disabled={workingAction !== null}
                    onClick={() => void decide(action)}
                  >
                    {workingAction === action ? t('Saving decision…') : t(actionLabels[action])}
                  </button>
                ))}
              </div>
            )}
          </section>
        </div>
      )}
    </section>
  );
}
