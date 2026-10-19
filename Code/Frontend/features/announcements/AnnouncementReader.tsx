'use client';

import { useEffect, useRef, useState, type FormEvent } from 'react';
import { ApiError, api } from '@/lib/api';
import { formatDate, formatTime } from '@/lib/date';
import { usePreferences } from '@/lib/preferences';
import { useApiResource } from '@/lib/use-api-resource';
import type { Announcement, AnnouncementReportReceipt, ReactionSummary } from '@/lib/types';
import { announcementApiMessage, type AnnouncementMessage, useAnnouncementText } from './messages';
import styles from './announcements.module.css';

const PAGE_SIZE = 50;
const REACTIONS: { kind: NonNullable<ReactionSummary['mine']>; label: string }[] = [
  { kind: 'interested', label: 'Interested' },
  { kind: 'excited', label: 'Excited' },
  { kind: 'support', label: 'Support' },
  { kind: 'kudos', label: 'Kudos' },
  { kind: 'wow', label: 'Wow' },
  { kind: 'relate', label: 'Relate' },
];
const REPORT_REASONS = ['harassment', 'spam', 'deception', 'impersonation', 'other'] as const;
type ReportReason = typeof REPORT_REASONS[number];

export function AnnouncementReader({ orgId, token, eligible }: {
  orgId: string;
  token: string | null;
  eligible: boolean;
}) {
  const text = useAnnouncementText();
  const { preferences: { language } } = usePreferences();
  const path = `/organizations/${encodeURIComponent(orgId)}/announcements?limit=${PAGE_SIZE}&offset=0`;
  const announcements = useApiResource<Announcement[]>(path, token);
  const receipts = useApiResource<AnnouncementReportReceipt[]>(token ? '/me/announcement-reports' : null, token);
  const [older, setOlder] = useState<Announcement[]>([]);
  const [olderError, setOlderError] = useState(false);
  const [olderLoading, setOlderLoading] = useState(false);
  const [hasMoreOlder, setHasMoreOlder] = useState<boolean | null>(null);
  const olderController = useRef<AbortController | null>(null);

  useEffect(() => () => olderController.current?.abort(), [orgId, token]);

  const posts = [...(announcements.data ?? []), ...older].filter((post, index, all) =>
    all.findIndex((candidate) => candidate.id === post.id) === index,
  );
  const organizationReceipts = (receipts.data ?? []).filter((receipt) => receipt.org_id === orgId);
  const hasMore = hasMoreOlder ?? (announcements.data?.length === PAGE_SIZE);

  async function loadOlder() {
    if (!hasMore || olderLoading || !announcements.data) return;
    setOlderLoading(true);
    setOlderError(false);
    const offset = announcements.data.length + older.length;
    const controller = new AbortController();
    olderController.current?.abort();
    olderController.current = controller;
    try {
      const page = await api<Announcement[]>(
        `/organizations/${encodeURIComponent(orgId)}/announcements?limit=${PAGE_SIZE}&offset=${offset}`,
        { token, signal: controller.signal },
      );
      if (controller.signal.aborted) return;
      setOlder((current) => [...current, ...page]);
      setHasMoreOlder(page.length === PAGE_SIZE);
    } catch {
      if (!controller.signal.aborted) setOlderError(true);
    } finally {
      if (!controller.signal.aborted) setOlderLoading(false);
      if (olderController.current === controller) olderController.current = null;
    }
  }

  return (
    <section className={`panel ${styles.reader}`} aria-labelledby={`announcements-${orgId}`}>
      <header className={styles.sectionHeading}>
        <div>
          <h2 id={`announcements-${orgId}`}>{text('Announcements')}</h2>
          <p className="muted">{text('Updates from this organization')}</p>
        </div>
      </header>

      {announcements.loading && announcements.data === null ? (
        <p className="muted" role="status">{text('Loading announcements…')}</p>
      ) : announcements.error ? (
        <div className="panel error" role="alert">
          <p>{text('The announcement list could not be refreshed.')}</p>
          <button type="button" className="button button-secondary" onClick={announcements.reload}>
            {text('Retry loading announcements')}
          </button>
        </div>
      ) : posts.length === 0 ? (
        <p className="empty-state muted">{text('No announcements yet.')}</p>
      ) : (
        <div className={styles.postList}>
          {posts.map((post) => (
            <AnnouncementCard
              key={post.id}
              announcement={post}
              token={token}
              eligible={eligible}
              receipt={organizationReceipts.find((item) => item.announcement_id === post.id && item.status === 'open') ?? null}
              onReportSubmitted={receipts.reload}
            />
          ))}
        </div>
      )}

      {olderError && (
        <div className="panel error" role="alert">
          <p>{text('The announcement list could not be refreshed.')}</p>
          <button type="button" className="button button-secondary" onClick={() => void loadOlder()} disabled={olderLoading}>
            {text('Retry loading older announcements')}
          </button>
        </div>
      )}
      {hasMore && !announcements.error && (
        <button type="button" className="button button-secondary" onClick={() => void loadOlder()} disabled={olderLoading}>
          {olderLoading ? text('Loading older announcements…') : text('Load older announcements')}
        </button>
      )}

      {token && (
        <section className={styles.receiptList} aria-labelledby={`announcement-receipts-${orgId}`}>
          <h3 id={`announcement-receipts-${orgId}`}>{text('Your announcement reports')}</h3>
          {receipts.loading && receipts.data === null ? (
            <p className="muted" role="status">{text('The report receipt could not be loaded.')}</p>
          ) : receipts.error ? (
            <div className={styles.inlineError} role="alert">
              <p>{text('The report receipt could not be loaded.')}</p>
              <button type="button" className="text-action" onClick={receipts.reload}>{text('Retry loading your reports')}</button>
            </div>
          ) : organizationReceipts.length === 0 ? (
            <p className="muted">{text('No announcement reports for this organization.')}</p>
          ) : (
            <ul className={styles.receipts}>
              {organizationReceipts.map((receipt) => (
                <li key={receipt.id}>
                  <span>{text('Report status: {status}', { status: text(receipt.status[0].toUpperCase() + receipt.status.slice(1)) })}</span>
                  <span className={styles.receiptId}>{receipt.id}</span>
                  <time dateTime={receipt.deadline}>{text('Review deadline')}: {formatDate(receipt.deadline, language)} · {formatTime(receipt.deadline, language)}</time>
                </li>
              ))}
            </ul>
          )}
        </section>
      )}
    </section>
  );
}

function AnnouncementCard({ announcement, token, eligible, receipt, onReportSubmitted }: {
  announcement: Announcement;
  token: string | null;
  eligible: boolean;
  receipt: AnnouncementReportReceipt | null;
  onReportSubmitted: () => void;
}) {
  const text = useAnnouncementText();
  const { preferences: { language } } = usePreferences();
  const reactionPath = `/announcements/${encodeURIComponent(announcement.id)}/reactions`;
  const reactionResource = useApiResource<ReactionSummary>(reactionPath, token);
  const [summaryOverride, setSummaryOverride] = useState<ReactionSummary | null>(null);
  const summary = summaryOverride ?? reactionResource.data;
  const loadingSummary = reactionResource.loading;
  const summaryError = reactionResource.error !== null;
  const [reactionError, setReactionError] = useState<string | null>(null);
  const [reactionPending, setReactionPending] = useState<NonNullable<ReactionSummary['mine']> | null | undefined>(undefined);
  const [reactionBusy, setReactionBusy] = useState(false);
  const reactionController = useRef<AbortController | null>(null);

  useEffect(() => () => reactionController.current?.abort(), [announcement.id, token]);

  async function setReaction(desired: NonNullable<ReactionSummary['mine']> | null) {
    if (!token || !eligible || !summary?.can_react || reactionBusy) return;
    setReactionBusy(true);
    setReactionPending(desired);
    setReactionError(null);
    const controller = new AbortController();
    reactionController.current?.abort();
    reactionController.current = controller;
    try {
      const updated = await api<ReactionSummary>(reactionPath, {
        token,
        method: 'POST',
        body: { reaction: desired },
        signal: controller.signal,
      });
      if (controller.signal.aborted) return;
      setSummaryOverride(updated);
      setReactionPending(undefined);
    } catch (error) {
      if (controller.signal.aborted) return;
      setReactionError(announcementApiMessage(error, 'Reaction update').key);
    } finally {
      if (!controller.signal.aborted) setReactionBusy(false);
      if (reactionController.current === controller) reactionController.current = null;
    }
  }

  const audience = announcement.audience === 'public' ? 'Public' : 'Members only';

  return (
    <article className={styles.post}>
      <header className={styles.postHeading}>
        <div>
          <h3>{announcement.title}</h3>
          <div className={styles.postMeta}>
            <span className={styles.audience} data-audience={announcement.audience}>{text(audience)}</span>
            <time dateTime={announcement.created_at}>{formatDate(announcement.created_at, language)} · {formatTime(announcement.created_at, language)}</time>
            {announcement.edited_at && <span className={styles.edited}>{text('Edited')}</span>}
          </div>
        </div>
      </header>
      {announcement.body && <p className={styles.postBody}>{announcement.body}</p>}

      <fieldset className={styles.reactionGroup}>
        <legend>{text('React to this announcement')}</legend>
        <div className={styles.reactionList}>
          {REACTIONS.map(({ kind, label }) => (
            <button
              key={kind}
              type="button"
              className={styles.reactionButton}
              aria-label={text('{action} {reaction} reaction ({count})', {
                action: text(summary?.mine === kind ? 'Remove' : 'Choose'),
                reaction: text(label),
                count: summary?.counts[kind] ?? 0,
              })}
              aria-pressed={summary?.mine === kind}
              disabled={!token || !eligible || !summary?.can_react || reactionBusy || summary === null}
              onClick={() => void setReaction(summary?.mine === kind ? null : kind)}
            >
              <span>{text(label)}</span>
              <span className={styles.reactionCount}>{summary?.counts[kind] ?? 0}</span>
            </button>
          ))}
        </div>
        {summary ? (
          <p className="muted">{text('{count} reactions', { count: summary.total })}</p>
        ) : summaryError ? (
          <div className={styles.inlineError} role="alert">
            <p>{text('Reaction totals are unavailable.')}</p>
            <button type="button" className="text-action" onClick={() => {
              setSummaryOverride(null);
              reactionResource.reload();
            }}>{text('Retry loading reactions')}</button>
          </div>
        ) : loadingSummary ? (
          <p className="muted" role="status">{text('Loading reaction totals…')}</p>
        ) : null}
        {reactionError && (
          <div className={styles.inlineError} role="alert">
            <p>{text(reactionError)}</p>
            {reactionPending !== undefined && (
              <button type="button" className="text-action" onClick={() => void setReaction(reactionPending)} disabled={reactionBusy}>
                {text('Retry reaction update')}
              </button>
            )}
          </div>
        )}
        {!token && <p className="muted">{text('Sign in with an eligible PLM account to react or report.')}</p>}
        {token && !eligible && <p className="muted">{text('Reactions are available to eligible PLM stakeholders.')}</p>}
      </fieldset>

      {token && eligible ? (
        <AnnouncementReportForm
          announcementId={announcement.id}
          token={token}
          receipt={receipt}
          onSubmitted={onReportSubmitted}
        />
      ) : (
        <p className={styles.reportNote}>{text('Sign in with an eligible PLM account to react or report.')}</p>
      )}
    </article>
  );
}

function AnnouncementReportForm({ announcementId, token, receipt, onSubmitted }: {
  announcementId: string;
  token: string;
  receipt: AnnouncementReportReceipt | null;
  onSubmitted: () => void;
}) {
  const text = useAnnouncementText();
  const { preferences: { language } } = usePreferences();
  const [reason, setReason] = useState<ReportReason | ''>('');
  const [submittedReceipt, setSubmittedReceipt] = useState<AnnouncementReportReceipt | null>(null);
  const [error, setError] = useState<AnnouncementMessage | null>(null);
  const [busy, setBusy] = useState(false);
  const reportController = useRef<AbortController | null>(null);
  const openReceipt = submittedReceipt ?? receipt;

  useEffect(() => () => reportController.current?.abort(), [announcementId, token]);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!reason || busy) return;
    setBusy(true);
    setError(null);
    const controller = new AbortController();
    reportController.current?.abort();
    reportController.current = controller;
    try {
      const created = await api<AnnouncementReportReceipt>(`/announcements/${encodeURIComponent(announcementId)}/reports`, {
        token,
        method: 'POST',
        body: { reason },
        signal: controller.signal,
      });
      if (controller.signal.aborted) return;
      setSubmittedReceipt(created);
      setReason('');
      onSubmitted();
    } catch (caught) {
      if (controller.signal.aborted) return;
      setError(caught instanceof ApiError && caught.status === 409
        ? { key: 'A report may already be open. Check your report receipts before trying again.' }
        : announcementApiMessage(caught, 'Report submission'));
    } finally {
      if (!controller.signal.aborted) setBusy(false);
      if (reportController.current === controller) reportController.current = null;
    }
  }

  return (
    <details className={styles.reportDetails}>
      <summary>{text('Report announcement')}</summary>
      <div className={styles.reportPanel}>
        <p className={styles.reportNote}>{text('A report does not hide this announcement automatically.')}</p>
        {openReceipt ? (
          <div className={styles.reportReceipt} role="status">
            <strong>{text('Your report receipt')}</strong>
            <span>{text('Your report is already open for this announcement.')}</span>
            <code>{openReceipt.id}</code>
            <time dateTime={openReceipt.deadline}>{text('Review deadline')}: {formatDate(openReceipt.deadline, language)} · {formatTime(openReceipt.deadline, language)}</time>
          </div>
        ) : (
          <form onSubmit={(event) => void submit(event)}>
            <label className="field">
              <span>{text('Reason')}</span>
              <select value={reason} onChange={(event) => setReason(event.target.value as ReportReason | '')} disabled={busy} required>
                <option value="">{text('Choose a reason')}</option>
                {REPORT_REASONS.map((item) => <option value={item} key={item}>{text(item[0].toUpperCase() + item.slice(1))}</option>)}
              </select>
            </label>
            {error && <p className="panel error" role="alert">{text(error.key, error.values)}</p>}
            <button type="submit" className="button button-secondary" disabled={busy || !reason}>
              {busy ? text('Sending report…') : text('Submit report')}
            </button>
          </form>
        )}
      </div>
    </details>
  );
}
