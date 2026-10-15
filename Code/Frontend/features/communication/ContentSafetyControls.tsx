'use client';

import { useEffect, useId, useRef, useState, type FormEvent } from 'react';
import { api, ApiError } from '@/lib/api';
import type { Actor, ContentItem, ReportReceipt } from '@/lib/types';
import styles from './communication.module.css';

type ContentKind = 'comment' | 'message';
type ReportReason = 'harassment' | 'spam' | 'deception' | 'impersonation' | 'other';
type ReportChoice = 'content' | 'person';

const REASONS: { value: ReportReason; label: string }[] = [
  { value: 'harassment', label: 'Harassment' },
  { value: 'spam', label: 'Spam' },
  { value: 'deception', label: 'Deception' },
  { value: 'impersonation', label: 'Impersonation' },
  { value: 'other', label: 'Other' },
];

function actionError(error: unknown, label: string) {
  if (error instanceof ApiError && error.status === 401) return 'Sign in again, then retry.';
  if (error instanceof ApiError && error.status === 403) return 'This action is unavailable for this account.';
  if (error instanceof ApiError && error.status === 404) return 'This item is no longer available.';
  return `${label} could not be completed. Retry the same action.`;
}

export function ContentSafetyControls({
  eventId,
  kind,
  item,
  actor,
  token,
  onChange,
  onRestore,
}: {
  eventId: string;
  kind: ContentKind;
  item: ContentItem;
  actor: Actor | null;
  token: string | null;
  onChange: (item: ContentItem) => void;
  onRestore: (item: ContentItem, signal: AbortSignal) => Promise<ContentItem | null>;
}) {
  const [choice, setChoice] = useState<ReportChoice>('content');
  const [reason, setReason] = useState<ReportReason>('harassment');
  const [receipt, setReceipt] = useState<{ value: ReportReceipt; choice: ReportChoice } | null>(null);
  const [reportError, setReportError] = useState<string | null>(null);
  const [reporting, setReporting] = useState(false);
  const [hiding, setHiding] = useState(false);
  const [hideError, setHideError] = useState<string | null>(null);
  const reportController = useRef<AbortController | null>(null);
  const hideController = useRef<AbortController | null>(null);
  const id = useId();

  useEffect(() => () => {
    reportController.current?.abort();
    hideController.current?.abort();
  }, []);

  if (!token || !actor?.eligible || item.removed) return null;
  const canReport = !item.mine && item.author_id !== actor.id && !item.locally_hidden;

  async function toggleHidden() {
    if (!token || !actor?.eligible || hiding) return;
    const controller = new AbortController();
    hideController.current?.abort();
    hideController.current = controller;
    const hidden = !item.locally_hidden;
    setHiding(true);
    setHideError(null);
    try {
      await api<unknown>('/me/content-hides', {
        token,
        method: 'POST',
        body: { event_id: eventId, kind, target_id: item.id, hidden },
        signal: controller.signal,
      });
      if (controller.signal.aborted) return;
      if (hidden) {
        onChange({ ...item, body: null, locally_hidden: true });
      } else {
        const restored = await onRestore(item, controller.signal);
        if (!controller.signal.aborted && restored) onChange(restored);
        else if (!controller.signal.aborted) setHideError('Restored on the server, but this item could not be reloaded. Retry restore.');
      }
    } catch (error) {
      if (!controller.signal.aborted) setHideError(actionError(error, hidden ? 'Hiding' : 'Restoring'));
    } finally {
      if (!controller.signal.aborted) setHiding(false);
      if (hideController.current === controller) hideController.current = null;
    }
  }

  async function submitReport(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!token || !actor?.eligible || !canReport || reporting) return;
    const controller = new AbortController();
    reportController.current?.abort();
    reportController.current = controller;
    setReporting(true);
    setReportError(null);
    setReceipt(null);
    const reportKind = choice === 'person' ? 'person' : kind;
    const targetId = choice === 'person' ? item.author_id : item.id;
    try {
      const nextReceipt = await api<ReportReceipt>(`/events/${encodeURIComponent(eventId)}/reports`, {
        token,
        method: 'POST',
        body: { kind: reportKind, target_id: targetId, reason },
        signal: controller.signal,
      });
      if (!controller.signal.aborted) setReceipt({ value: nextReceipt, choice });
    } catch (error) {
      if (!controller.signal.aborted) setReportError(actionError(error, 'The report'));
    } finally {
      if (!controller.signal.aborted) setReporting(false);
      if (reportController.current === controller) reportController.current = null;
    }
  }

  return (
    <div className={styles.itemControls}>
      <button className={styles.smallButton} type="button" onClick={() => void toggleHidden()} disabled={hiding}>
        {hiding ? 'Saving…' : item.locally_hidden ? 'Restore for me' : 'Hide for me'}
      </button>
      {canReport ? (
        <details className={styles.reportDetails}>
          <summary className={styles.reportSummary}>Report</summary>
          <form className={styles.reportPanel} onSubmit={(event) => void submitReport(event)}>
            <fieldset>
              <legend>What are you reporting?</legend>
              <label className={styles.reportChoice}>
                <input
                  className={styles.radio}
                  type="radio"
                  name={`report-choice-${id}`}
                  value="content"
                  checked={choice === 'content'}
                  disabled={reporting || receipt !== null}
                  onChange={() => setChoice('content')}
                />
                <span>This {kind === 'comment' ? 'comment' : 'message'}</span>
              </label>
              <label className={styles.reportChoice}>
                <input
                  className={styles.radio}
                  type="radio"
                  name={`report-choice-${id}`}
                  value="person"
                  checked={choice === 'person'}
                  disabled={reporting || receipt !== null}
                  onChange={() => setChoice('person')}
                />
                <span>This member</span>
              </label>
            </fieldset>
            <label htmlFor={`report-reason-${id}`}>Reason</label>
            <select
              className={styles.select}
              id={`report-reason-${id}`}
              value={reason}
              disabled={reporting || receipt !== null}
              onChange={(event) => setReason(event.target.value as ReportReason)}
            >
              {REASONS.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
            </select>
            <p className={styles.muted}>
              A content report does not hide the item. Hide it separately if you do not want to see it.
            </p>
            <button className={styles.primaryButton} type="submit" disabled={reporting || receipt !== null}>
              {reporting ? 'Sending…' : receipt ? 'Report submitted' : 'Submit report'}
            </button>
            {reportError ? <p className={styles.errorText} role="alert">{reportError}</p> : null}
            {receipt ? (
              <p className={styles.statusText} role="status">
                {receipt.choice === 'person' ? 'Person report sent for review.' : 'Content report sent. The item remains visible while it is reviewed.'}
              </p>
            ) : null}
          </form>
        </details>
      ) : null}
      {hideError ? <span className={styles.errorText} role="alert">{hideError}</span> : null}
    </div>
  );
}
