'use client';

import { useEffect, useState } from 'react';
import { Feedback } from '@/components/feedback';
import { ApiError, api } from '@/lib/api';
import { formatDate, formatTime } from '@/lib/date';
import type { ReportReview } from '@/lib/types';
import { useApiResource } from '@/lib/use-api-resource';
import styles from './report-queue.module.css';

type DecisionAction = 'dismiss' | 'remove' | 'escalate' | 'warn';

const terminalStatuses = new Set<ReportReview['status']>(['dismissed', 'removed', 'warned', 'expired']);

function titleCase(value: string) {
  return value.replaceAll('_', ' ').replace(/\b\w/g, character => character.toUpperCase());
}

function isVisibleInQueue(report: ReportReview, orgId?: string) {
  return orgId
    ? report.stage === 'organization' && report.kind !== 'person'
    : report.stage === 'platform';
}

function decisionActions(report: ReportReview, orgId?: string): {action: DecisionAction; label: string}[] {
  if (report.kind === 'person') {
    return !orgId && report.stage === 'platform'
      ? [{action: 'dismiss', label: 'Dismiss'}, {action: 'warn', label: 'Warn user'}]
      : [];
  }

  if (orgId && report.stage === 'organization') {
    return [
      {action: 'dismiss', label: 'Dismiss'},
      {action: 'remove', label: 'Remove globally'},
      {action: 'escalate', label: 'Escalate to platform'},
    ];
  }

  return !orgId && report.stage === 'platform'
    ? [{action: 'dismiss', label: 'Dismiss'}, {action: 'remove', label: 'Remove globally'}]
    : [];
}

function reportIsStale(report: ReportReview) {
  const deadline = Date.parse(report.deadline);
  return terminalStatuses.has(report.status) ||
    !['open', 'escalated'].includes(report.status) ||
    !Number.isFinite(deadline) || deadline <= Date.now();
}

function ReportDetails({report, orgId}: {
  report: ReportReview;
  orgId?: string;
}) {
  const authorizedStage = isVisibleInQueue(report, orgId);
  const stale = reportIsStale(report);
  const evidenceVisible = authorizedStage && !stale && report.evidence !== null;

  if (!authorizedStage) {
    return <p className="muted" role="status">This report is no longer available in this review queue. Refresh the queue to continue.</p>;
  }

  return (
    <div className="stack">
      <header>
        <div className="actions">
          <h3>{titleCase(report.kind)} report</h3>
          <span className="status-chip">{titleCase(report.status)}</span>
          <span className="status-chip">{titleCase(report.stage)} review</span>
        </div>
        <p className={styles.reportMeta}>Report ID <span className={styles.identifier}>{report.id}</span></p>
      </header>

      <dl className="stack">
        <div>
          <dt><strong>Reason</strong></dt>
          <dd>{titleCase(report.reason)}</dd>
        </div>
        <div>
          <dt><strong>Event ID</strong></dt>
          <dd className={styles.identifier}>{report.event_id}</dd>
        </div>
        <div>
          <dt><strong>Organization ID</strong></dt>
          <dd className={styles.identifier}>{report.org_id}</dd>
        </div>
        <div>
          <dt><strong>Reporter ID</strong></dt>
          <dd className={styles.identifier}>{report.reporter_id}</dd>
        </div>
        {report.kind === 'person' ? (
          <div>
            <dt><strong>Subject user ID</strong></dt>
            <dd className={styles.identifier}>{report.subject_user_id}</dd>
          </div>
        ) : (
          <div>
            <dt><strong>Reported item ID</strong></dt>
            <dd className={styles.identifier}>{report.target_id}</dd>
          </div>
        )}
        <div>
          <dt><strong>Review deadline</strong></dt>
          <dd><time dateTime={report.deadline}>{formatDate(report.deadline)} · {formatTime(report.deadline)} (Manila)</time></dd>
        </div>
      </dl>

      <section aria-labelledby={`report-evidence-${report.id}`}>
        <h4 id={`report-evidence-${report.id}`}>Retained evidence</h4>
        {evidenceVisible && report.evidence ? (
          <blockquote className={styles.evidence}>{report.evidence}</blockquote>
        ) : (
          <p className="muted">
            {stale
              ? 'Evidence is unavailable after resolution or the review deadline.'
              : 'No evidence snapshot is available for this report.'}
          </p>
        )}
      </section>

      <section aria-labelledby={`report-audit-${report.id}`}>
        <h4 id={`report-audit-${report.id}`}>Decision audit</h4>
        {report.decisions.length === 0 ? (
          <p className="muted">No decision has been recorded.</p>
        ) : (
          <ol className={styles.auditList}>
            {report.decisions.map(decision => (
              <li key={decision.id}>
                <strong>{titleCase(decision.action)}</strong>
                {' · '}
                {decision.reviewer_id
                  ? <>Reviewer ID <span className={styles.identifier}>{decision.reviewer_id}</span></>
                  : 'Automatic deadline transition'}
                <br />
                <time dateTime={decision.created_at}>
                  {formatDate(decision.created_at)} · {formatTime(decision.created_at)} (Manila)
                </time>
              </li>
            ))}
          </ol>
        )}
      </section>

      {stale && !terminalStatuses.has(report.status) && (
        <p className="panel muted" role="status">
          The review deadline has passed. New decisions are unavailable and retained evidence is hidden; refresh to load the latest audit state.
        </p>
      )}

    </div>
  );
}

export function ModerationReportQueue({token, orgId}: {token: string; orgId?: string}) {
  const queuePath = orgId
    ? `/moderation/reports?org_id=${encodeURIComponent(orgId)}`
    : '/moderation/reports';
  const reports = useApiResource<ReportReview[]>(queuePath, token);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [workingAction, setWorkingAction] = useState<DecisionAction | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [decisionError, setDecisionError] = useState<string | null>(null);
  const [, setDeadlineTick] = useState(0);
  const selectedPath = selectedId ? `/moderation/reports/${encodeURIComponent(selectedId)}` : null;
  const selected = useApiResource<ReportReview>(selectedPath, token);
  const visibleReports = (reports.data ?? []).filter(report => isVisibleInQueue(report, orgId));

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
    if (action === 'remove' && !window.confirm('Remove this reported content for everyone?')) return;
    if (reportIsStale(report)) {
      setDecisionError('The review deadline has passed. Refresh the queue and audit before continuing.');
      reports.reload();
      selected.reload();
      return;
    }
    setWorkingAction(action);
    setNotice(null);
    setDecisionError(null);
    try {
      await api<ReportReview>(`/moderation/reports/${encodeURIComponent(report.id)}/decision`, {
        token,
        method: 'POST',
        body: {action},
      });
      setNotice(action === 'escalate'
        ? 'The report was escalated to platform review.'
        : 'The decision was recorded.');
      reports.reload();
      if (orgId && action === 'escalate') setSelectedId(null);
      else selected.reload();
    } catch (error) {
      setDecisionError(error instanceof ApiError && error.status === 409
        ? 'This report changed while you were reviewing it. The queue and audit have been refreshed.'
        : error instanceof Error ? error.message : 'The decision could not be recorded.');
      reports.reload();
      if (selectedId) selected.reload();
    } finally {
      setWorkingAction(null);
    }
  }

  return (
    <section className="panel stack" aria-labelledby={orgId ? `moderation-queue-${orgId}` : 'platform-moderation-queue'}>
      <header className="actions">
        <h2 id={orgId ? `moderation-queue-${orgId}` : 'platform-moderation-queue'}>
          {orgId ? 'Organization event reports' : 'Platform report review'}
        </h2>
        <button className="button button-secondary" type="button" onClick={refresh} disabled={reports.loading || selected.loading || workingAction !== null}>
          Refresh queue
        </button>
      </header>
      <p className="muted">
        {orgId
          ? 'Review reports assigned to this organization. Personal reports are handled by platform moderators.'
          : 'Review reports assigned to the platform. Only the report snapshot and decision audit are shown; private profiles and email addresses are not available here.'}
      </p>

      {notice && <p className="success panel" role="status">{notice}</p>}
      {decisionError && <div className="error panel" role="alert"><p>{decisionError}</p><button className="button button-secondary" type="button" onClick={refresh}>Refresh report</button></div>}

      <Feedback loading={reports.loading} error={reports.error} onRetry={reports.reload}>
        {reports.data && (
          <div className={styles.layout}>
            <section className={styles.list} aria-labelledby={orgId ? `report-list-${orgId}` : 'platform-report-list'}>
              <h3 id={orgId ? `report-list-${orgId}` : 'platform-report-list'}>Reports ({visibleReports.length})</h3>
              {!visibleReports.length ? (
                <p className="empty-state muted">No reports are available in this review stage.</p>
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
                        <strong>{titleCase(report.kind)} · {titleCase(report.reason)}</strong>
                        <span className={styles.reportMeta}>{titleCase(report.status)} · {titleCase(report.stage)} review</span>
                        <span className={styles.reportMeta}>Review deadline {formatDate(report.deadline)} · {formatTime(report.deadline)} (Manila)</span>
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </section>

            <section className={`${styles.detail} stack`} aria-label="Selected report details" aria-live="polite">
              {!selectedId ? (
                <p className="empty-state muted">Select a report to inspect its permitted evidence and decision audit.</p>
              ) : selected.loading ? (
                <p className="panel muted" role="status">Loading report details…</p>
              ) : selected.error ? (
                <div className="error panel" role="alert">
                  <p>{selected.error.message}</p>
                  <button className="button button-secondary" type="button" onClick={refresh}>Refresh report</button>
                </div>
              ) : selected.data ? (
                <ReportDetails report={selected.data} orgId={orgId} />
              ) : null}

              {selected.data && !reportIsStale(selected.data) && isVisibleInQueue(selected.data, orgId) && (
                <div className="actions" aria-label="Report decisions">
                  {decisionActions(selected.data, orgId).map(({action, label}) => (
                    <button
                      key={action}
                      className={action === 'remove' || action === 'warn' ? 'button button-danger' : 'button button-secondary'}
                      type="button"
                      disabled={workingAction !== null}
                      onClick={() => void decide(action)}
                    >
                      {workingAction === action ? 'Saving…' : label}
                    </button>
                  ))}
                </div>
              )}
            </section>
          </div>
        )}
      </Feedback>
    </section>
  );
}
