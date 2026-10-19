'use client';

import { useEffect, useState } from 'react';
import { ApiError, api } from '@/lib/api';
import { formatDate, formatTime } from '@/lib/date';
import { useT } from '@/lib/i18n';
import { usePreferences } from '@/lib/preferences';
import type { Translate } from '@/lib/i18n';
import type { ReportReview } from '@/lib/types';
import { useApiResource } from '@/lib/use-api-resource';
import styles from './report-queue.module.css';

type DecisionAction = 'dismiss' | 'remove' | 'escalate' | 'warn';

const terminalStatuses = new Set<ReportReview['status']>(['dismissed', 'removed', 'warned', 'expired']);
const reportKindLabels: Record<ReportReview['kind'], string> = {
  comment: 'Comment',
  message: 'Message',
  person: 'Person',
};
const reportReasonLabels: Record<ReportReview['reason'], string> = {
  harassment: 'Harassment',
  spam: 'Spam',
  deception: 'Deception',
  impersonation: 'Impersonation',
  other: 'Other',
};
const reportStatusLabels: Record<ReportReview['status'], string> = {
  open: 'Open',
  escalated: 'Escalated',
  dismissed: 'Dismissed',
  removed: 'Removed',
  warned: 'Warned',
  expired: 'Expired',
};
const reportStageLabels: Record<ReportReview['stage'], string> = {
  organization: 'Organization',
  platform: 'Platform',
};
const decisionLabels: Record<ReportReview['decisions'][number]['action'], string> = {
  dismiss: 'Dismiss',
  remove: 'Remove globally',
  escalate: 'Escalate to platform',
  warn: 'Warn user',
  expire: 'Deadline expired',
};
const actionLabels: Record<DecisionAction, string> = {
  dismiss: 'Dismiss',
  remove: 'Remove globally',
  escalate: 'Escalate to platform',
  warn: 'Warn user',
};

function isVisibleInQueue(report: ReportReview, orgId?: string) {
  return orgId
    ? report.stage === 'organization' && report.kind !== 'person'
    : report.stage === 'platform';
}

function decisionActions(report: ReportReview, orgId?: string): DecisionAction[] {
  if (report.kind === 'person') {
    return !orgId && report.stage === 'platform' ? ['dismiss', 'warn'] : [];
  }

  if (orgId && report.stage === 'organization') {
    return ['dismiss', 'remove', 'escalate'];
  }

  return !orgId && report.stage === 'platform' ? ['dismiss', 'remove'] : [];
}

function reportIsStale(report: ReportReview) {
  const deadline = Date.parse(report.deadline);
  return terminalStatuses.has(report.status) ||
    !['open', 'escalated'].includes(report.status) ||
    !Number.isFinite(deadline) || deadline <= Date.now();
}

function ReportDetails({report, orgId, t, language}: {
  report: ReportReview;
  orgId?: string;
  t: Translate;
  language: 'en' | 'fil';
}) {
  const authorizedStage = isVisibleInQueue(report, orgId);
  const stale = reportIsStale(report);
  const evidenceVisible = authorizedStage && !stale && report.evidence !== null;

  if (!authorizedStage) {
    return <p className="muted" role="status">{t('This report is no longer available in this review queue. Refresh the queue to continue.')}</p>;
  }

  return (
    <div className={styles.reportDetails}>
      <header className={styles.detailHeading}>
        <div>
          <div className={styles.titleLine}>
            <h3>{t('{kind} report', {kind: t(reportKindLabels[report.kind])})}</h3>
            <span className={styles.statusTag}>{t(reportStatusLabels[report.status])}</span>
            <span className={styles.statusTag}>{t('{stage} review', {stage: t(reportStageLabels[report.stage])})}</span>
          </div>
          <p className={styles.reportMeta}>
            {t('Report ID')} <span className={styles.identifier}>{report.id}</span>
          </p>
        </div>
      </header>

      <dl className={styles.detailsGrid}>
        <div className={styles.detailField}>
          <dt>{t('Reason')}</dt>
          <dd>{t(reportReasonLabels[report.reason])}</dd>
        </div>
        <div className={styles.detailField}>
          <dt>{t('Review deadline')}</dt>
          <dd>
            <time dateTime={report.deadline}>
              {formatDate(report.deadline, language)} · {formatTime(report.deadline, language)} ({t('Manila time')})
            </time>
          </dd>
        </div>
        <div className={styles.detailField}>
          <dt>{t('Event ID')}</dt>
          <dd className={styles.identifier}>{report.event_id}</dd>
        </div>
        <div className={styles.detailField}>
          <dt>{t('Organization ID')}</dt>
          <dd className={styles.identifier}>{report.org_id}</dd>
        </div>
        <div className={styles.detailField}>
          <dt>{t('Reporter ID')}</dt>
          <dd className={styles.identifier}>{report.reporter_id}</dd>
        </div>
        {report.kind === 'person' ? (
          <div className={styles.detailField}>
            <dt>{t('Subject user ID')}</dt>
            <dd className={styles.identifier}>{report.subject_user_id}</dd>
          </div>
        ) : (
          <div className={styles.detailField}>
            <dt>{t('Reported item ID')}</dt>
            <dd className={styles.identifier}>{report.target_id}</dd>
          </div>
        )}
      </dl>

      <section className={styles.detailSection} aria-labelledby={'report-evidence-' + report.id}>
        <h4 id={'report-evidence-' + report.id}>{t('Retained evidence')}</h4>
        {evidenceVisible && report.evidence ? (
          <blockquote className={styles.evidence}>{report.evidence}</blockquote>
        ) : (
          <p className="muted">
            {stale
              ? t('Evidence is unavailable after resolution or the review deadline.')
              : t('No evidence snapshot is available for this report.')}
          </p>
        )}
      </section>

      <section className={styles.detailSection} aria-labelledby={'report-audit-' + report.id}>
        <h4 id={'report-audit-' + report.id}>{t('Decision history')}</h4>
        {report.decisions.length === 0 ? (
          <p className="muted">{t('No decision has been recorded.')}</p>
        ) : (
          <ol className={styles.auditList}>
            {report.decisions.map(decision => (
              <li key={decision.id}>
                <strong>{t(decisionLabels[decision.action])}</strong>
                {' · '}
                {decision.reviewer_id ? (
                  <>{t('Reviewer ID')} <span className={styles.identifier}>{decision.reviewer_id}</span></>
                ) : t('Automatic deadline transition')}
                <time dateTime={decision.created_at}>
                  {formatDate(decision.created_at, language)} · {formatTime(decision.created_at, language)} ({t('Manila time')})
                </time>
              </li>
            ))}
          </ol>
        )}
      </section>

      {stale && !terminalStatuses.has(report.status) && (
        <p className={'panel ' + styles.deadlineNotice} role="status">
          {t('The review deadline has passed. New decisions are unavailable and retained evidence is hidden; refresh to load the latest audit state.')}
        </p>
      )}
    </div>
  );
}

export function ModerationReportQueue({token, orgId}: {token: string; orgId?: string}) {
  const t = useT();
  const {preferences} = usePreferences();
  const queuePath = orgId
    ? '/moderation/reports?org_id=' + encodeURIComponent(orgId)
    : '/moderation/reports';
  const reports = useApiResource<ReportReview[]>(queuePath, token);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [workingAction, setWorkingAction] = useState<DecisionAction | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [decisionError, setDecisionError] = useState<string | null>(null);
  const [, setDeadlineTick] = useState(0);
  const selectedPath = selectedId ? '/moderation/reports/' + encodeURIComponent(selectedId) : null;
  const selected = useApiResource<ReportReview>(selectedPath, token);
  const visibleReports = (reports.data ?? []).filter(report => isVisibleInQueue(report, orgId));
  const headingId = orgId ? 'moderation-queue-' + orgId : 'platform-moderation-queue';
  const listHeadingId = orgId ? 'report-list-' + orgId : 'platform-report-list';

  useEffect(() => {
    const deadline = selected.data?.deadline;
    if (!deadline) return;
    const dueAt = Date.parse(deadline);
    if (!Number.isFinite(dueAt)) return;
    const timer = window.setTimeout(
      () => setDeadlineTick(value => value + 1),
      Math.max(0, dueAt - Date.now()) + 1,
    );
    return () => window.clearTimeout(timer);
  }, [selected.data?.deadline]);

  function refresh() {
    setNotice(null);
    setDecisionError(null);
    reports.reload();
    if (selectedId) selected.reload();
  }

  async function decide(action: DecisionAction) {
    const report = selected.data;
    if (!report || !token || workingAction || !isVisibleInQueue(report, orgId) || reportIsStale(report)) return;
    if (action === 'remove' && !window.confirm(t('Remove this reported content for everyone?'))) return;
    if (reportIsStale(report)) {
      setDecisionError(t('The review deadline has passed. Refresh the queue and audit before continuing.'));
      reports.reload();
      selected.reload();
      return;
    }
    setWorkingAction(action);
    setNotice(null);
    setDecisionError(null);
    try {
      await api<ReportReview>('/moderation/reports/' + encodeURIComponent(report.id) + '/decision', {
        token,
        method: 'POST',
        body: {action},
      });
      setNotice(action === 'escalate'
        ? t('The report was escalated to platform review.')
        : t('The decision was recorded.'));
      reports.reload();
      if (orgId && action === 'escalate') setSelectedId(null);
      else selected.reload();
    } catch (error) {
      setDecisionError(error instanceof ApiError && error.status === 409
        ? t('This report changed while you were reviewing it. The queue and audit have been refreshed.')
        : error instanceof Error ? error.message : t('The decision could not be recorded.'));
      reports.reload();
      if (selectedId) selected.reload();
    } finally {
      setWorkingAction(null);
    }
  }

  return (
    <section className={'panel ' + styles.queue} aria-labelledby={headingId}>
      <header className={styles.queueHeading}>
        <div>
          <p className="eyebrow">{t('Platform safety')}</p>
          <h2 id={headingId}>
            {orgId ? t('Organization event reports') : t('Platform report review')}
          </h2>
        </div>
        <button
          className="button button-secondary"
          type="button"
          onClick={refresh}
          disabled={reports.loading || selected.loading || workingAction !== null}
        >
          {t('Refresh queue')}
        </button>
      </header>
      <p className={styles.queueDescription}>
        {orgId
          ? t('Review reports assigned to this organization. Personal reports are handled by platform moderators.')
          : t('Review reports assigned to the platform. Only the report snapshot and decision audit are shown; private profiles and email addresses are not available here.')}
      </p>

      {notice && <p className={'success panel ' + styles.feedback} role="status">{notice}</p>}
      {decisionError && (
        <div className={'error panel ' + styles.feedback} role="alert">
          <p>{decisionError}</p>
          <button className="button button-secondary" type="button" onClick={refresh}>{t('Refresh report')}</button>
        </div>
      )}

      {reports.loading && !reports.data && (
        <p className={styles.feedback} role="status">{t('Loading reports…')}</p>
      )}
      {reports.error && (
        <div className={'error panel ' + styles.feedback} role="alert">
          <p>{t('The report queue could not be loaded.')} {reports.error.message}</p>
          <button className="button button-secondary" type="button" onClick={refresh}>{t('Retry loading reports')}</button>
        </div>
      )}
      {!reports.loading && !reports.error && !reports.data && (
        <p className={styles.emptyState}>{t('No reports are available in this review stage.')}</p>
      )}
      {reports.data && !reports.error && (
        <div className={styles.layout}>
          <section className={styles.list} aria-labelledby={listHeadingId}>
            <div className={styles.listHeading}>
              <h3 id={listHeadingId}>{t('Reports ({count})', {count: visibleReports.length})}</h3>
            </div>
            {!visibleReports.length ? (
              <p className={styles.emptyState}>{t('No reports are available in this review stage.')}</p>
            ) : (
              <ul className={styles.reportList}>
                {visibleReports.map(report => (
                  <li key={report.id}>
                    <button
                      className={styles.reportButton}
                      type="button"
                      aria-pressed={selectedId === report.id}
                      onClick={() => {
                        setSelectedId(report.id);
                        setNotice(null);
                        setDecisionError(null);
                      }}
                    >
                      <span className={styles.reportTitle}>
                        {t(reportKindLabels[report.kind])} · {t(reportReasonLabels[report.reason])}
                      </span>
                      <span className={styles.reportMeta}>
                        {t(reportStatusLabels[report.status])} · {t('{stage} review', {stage: t(reportStageLabels[report.stage])})}
                      </span>
                      <span className={styles.reportMeta}>
                        {t('Review deadline')} · {formatDate(report.deadline, preferences.language)} · {formatTime(report.deadline, preferences.language)} ({t('Manila time')})
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </section>

          <section className={styles.detail} aria-label={t('Selected report details')} aria-live="polite">
            {!selectedId ? (
              <p className={styles.emptyState}>{t('Select a report to inspect its permitted evidence and decision history.')}</p>
            ) : selected.loading ? (
              <p className={styles.inlineStatus} role="status">{t('Loading report details…')}</p>
            ) : selected.error ? (
              <div className="error panel" role="alert">
                <p>{t('The selected report could not be loaded.')} {selected.error.message}</p>
                <button className="button button-secondary" type="button" onClick={refresh}>{t('Refresh report')}</button>
              </div>
            ) : selected.data ? (
              <ReportDetails report={selected.data} orgId={orgId} t={t} language={preferences.language} />
            ) : null}

            {selected.data && !selected.loading && !selected.error && !reports.loading && !reports.error && !reportIsStale(selected.data) && isVisibleInQueue(selected.data, orgId) && (
              <div className={styles.decisionActions} role="group" aria-label={t('Report decisions')}>
                {decisionActions(selected.data, orgId).map(action => (
                  <button
                    key={action}
                    className={action === 'remove' || action === 'warn' ? 'button button-danger' : 'button button-secondary'}
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
