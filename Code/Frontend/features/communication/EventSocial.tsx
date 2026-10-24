'use client';

import Link from 'next/link';
import { useCallback, useEffect, useRef, useState } from 'react';
import { api, ApiError } from '@/lib/api';
import { formatDate, formatTime } from '@/lib/date';
import { useT } from '@/lib/i18n';
import { usePreferences } from '@/lib/preferences';
import { useSession } from '@/lib/session';
import type { Actor, ContentItem, ContentPage, ReactionSummary } from '@/lib/types';
import { ContentSafetyControls } from './ContentSafetyControls';
import { applyAuthorLabels, clearAuthorLabels } from '@/lib/content-labels';
import { PERSONA_ACCESS_CHANGED_EVENT } from '@/features/personas/access-events';
import styles from './communication.module.css';

type ReactionKind = NonNullable<ReactionSummary['mine']>;
type LocalizedMessage = { literal: string; values?: Record<string, string | number> };
type Translate = ReturnType<typeof useT>;

const REACTIONS: { kind: ReactionKind; label: string; icon: string }[] = [
  { kind: 'interested' as ReactionKind, label: 'Interested', icon: '⭐' },
  { kind: 'excited' as ReactionKind, label: 'Excited', icon: '🎉' },
  { kind: 'support' as ReactionKind, label: 'Support', icon: '💛' },
  { kind: 'kudos' as ReactionKind, label: 'Kudos', icon: '👏' },
  { kind: 'wow' as ReactionKind, label: 'Wow', icon: '😮' },
  { kind: 'relate' as ReactionKind, label: 'Relate', icon: '🤗' },
];

function requestMessage(error: unknown, action: string): LocalizedMessage {
  if (error instanceof ApiError && error.status === 401) return { literal: 'Your sign-in expired. Sign in again, then retry.' };
  if (error instanceof ApiError && error.status === 403) return { literal: 'This action is unavailable for this account.' };
  if (error instanceof ApiError && error.status === 404) return { literal: 'This event is no longer available.' };
  return { literal: '{action} could not be completed. Check your connection and retry.', values: { action } };
}

function translateMessage(message: LocalizedMessage, t: Translate) {
  const values = message.values && { ...message.values };
  if (values && typeof values.action === 'string') values.action = t(values.action);
  return t(message.literal, values);
}

function mergeComments(existing: ContentItem[], added: ContentItem[]) {
  const byId = new Map(existing.map((item) => [item.id, item]));
  for (const item of added) byId.set(item.id, item);
  return [...byId.values()].sort((left, right) => right.sequence - left.sequence);
}

function clientClockNow() {
  return Date.now();
}

export function EventSocial(props: {
  eventId: string;
  startsAt: string;
  onReactionChanged?: () => void;
}) {
  const { actor, token, version } = useSession();
  const requestKey = `${props.eventId}:${props.startsAt}:${version}:${token ?? 'guest'}`;
  return (
    <EventSocialSession
      key={requestKey}
      eventId={props.eventId}
      startsAt={props.startsAt}
      actor={actor}
      token={token}
      onReactionChanged={props.onReactionChanged}
    />
  );
}

function EventSocialSession({
  eventId,
  startsAt,
  actor,
  token,
  onReactionChanged,
}: {
  eventId: string;
  startsAt: string;
  actor: Actor | null;
  token: string | null;
  onReactionChanged?: () => void;
}) {
  const t = useT();
  const { preferences } = usePreferences();
  const startsAtMs = Date.parse(startsAt);
  const [now, setNow] = useState<number | null>(null);
  const [summary, setSummary] = useState<ReactionSummary | null>(null);
  const [reactionError, setReactionError] = useState<LocalizedMessage | null>(null);
  const [reactionPending, setReactionPending] = useState<ReactionKind | null | undefined>(undefined);
  const [reactionBusy, setReactionBusy] = useState(false);
  const [comments, setComments] = useState<ContentItem[]>([]);
  const [commentsLoading, setCommentsLoading] = useState(true);
  const [commentsError, setCommentsError] = useState<LocalizedMessage | null>(null);
  const [nextBefore, setNextBefore] = useState<number | null>(null);
  const [loadingOlder, setLoadingOlder] = useState(false);
  const [draft, setDraft] = useState('');
  const [pendingComment, setPendingComment] = useState<{ body: string; clientKey: string } | null>(null);
  const [commentError, setCommentError] = useState<LocalizedMessage | null>(null);
  const [commentBusy, setCommentBusy] = useState(false);
  const reactionController = useRef<AbortController | null>(null);
  const commentsController = useRef<AbortController | null>(null);
  const commentMutation = useRef<AbortController | null>(null);
  const reactionMutation = useRef<AbortController | null>(null);
  const deleteMutation = useRef<AbortController | null>(null);
  const labelsController = useRef<AbortController | null>(null);

  useEffect(() => {
    const first = window.setTimeout(() => setNow(Date.now()), 0);
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => {
      window.clearTimeout(first);
      window.clearInterval(timer);
    };
  }, []);

  const loadComments = useCallback(async (beforeSequence?: number) => {
    const controller = new AbortController();
    commentsController.current?.abort();
    commentsController.current = controller;
    if (beforeSequence === undefined) {
      setCommentsLoading(true);
      setCommentsError(null);
    } else {
      setLoadingOlder(true);
      setCommentsError(null);
    }
    const query = new URLSearchParams({ limit: '50' });
    if (beforeSequence !== undefined) query.set('before_sequence', String(beforeSequence));
    try {
      const page = await api<ContentPage>(`/events/${encodeURIComponent(eventId)}/comments?${query}`, {
        token,
        signal: controller.signal,
      });
      if (controller.signal.aborted) return;
      setComments((current) => applyAuthorLabels(
        beforeSequence === undefined ? page.items : mergeComments(current, page.items), page.author_labels,
      ));
      setNextBefore(page.next_before ?? null);
    } catch (error) {
      if (!controller.signal.aborted) setCommentsError(requestMessage(error, 'Comments'));
    } finally {
      if (!controller.signal.aborted) {
        setCommentsLoading(false);
        setLoadingOlder(false);
      }
      if (commentsController.current === controller) commentsController.current = null;
    }
  }, [eventId, token]);

  useEffect(() => {
    const controller = new AbortController();
    reactionController.current?.abort();
    reactionController.current = controller;
    api<ReactionSummary>(`/events/${encodeURIComponent(eventId)}/reactions`, { token, signal: controller.signal })
      .then((result) => { if (!controller.signal.aborted) setSummary(result); })
      .catch((error: unknown) => {
        if (!controller.signal.aborted) setReactionError(requestMessage(error, 'Reactions'));
      });
    const commentLoad = window.setTimeout(() => {
      if (!controller.signal.aborted) void loadComments();
    }, 0);
    return () => {
      window.clearTimeout(commentLoad);
      controller.abort();
      if (reactionController.current === controller) reactionController.current = null;
      commentsController.current?.abort();
      commentMutation.current?.abort();
      reactionMutation.current?.abort();
      deleteMutation.current?.abort();
    };
  }, [eventId, token, loadComments]);

  useEffect(() => {
    if (!token || !actor?.eligible) return;
    async function refreshLabels() {
      const controller = new AbortController();
      labelsController.current?.abort();
      labelsController.current = controller;
      try {
        const page = await api<ContentPage>(`/events/${encodeURIComponent(eventId)}/comments?limit=1`, {
          token, signal: controller.signal,
        });
        if (!controller.signal.aborted) setComments(current => applyAuthorLabels(current, page.author_labels));
      } catch {
        if (!controller.signal.aborted) setComments(current => clearAuthorLabels(current));
      }
    }
    const onAccessChange = (event: Event) => {
      const userId = (event as CustomEvent<{ userId?: string }>).detail?.userId;
      commentsController.current?.abort();
      setComments(current => clearAuthorLabels(current, userId));
      setLoadingOlder(false);
      void refreshLabels();
    };
    const onFocus = () => {
      if (document.visibilityState === 'visible') void refreshLabels();
    };
    const timer = window.setInterval(onFocus, 30_000);
    window.addEventListener(PERSONA_ACCESS_CHANGED_EVENT, onAccessChange);
    window.addEventListener('focus', onFocus);
    document.addEventListener('visibilitychange', onFocus);
    return () => {
      window.clearInterval(timer);
      window.removeEventListener(PERSONA_ACCESS_CHANGED_EVENT, onAccessChange);
      window.removeEventListener('focus', onFocus);
      document.removeEventListener('visibilitychange', onFocus);
      labelsController.current?.abort();
    };
  }, [actor?.eligible, eventId, token]);

  useEffect(() => {
    if (!Number.isFinite(startsAtMs)) return;
    const cutoff = window.setTimeout(() => {
      setNow(clientClockNow());
      reactionMutation.current?.abort();
      commentMutation.current?.abort();
      setReactionBusy(false);
      setCommentBusy(false);
    }, Math.max(0, startsAtMs - clientClockNow()));
    return () => window.clearTimeout(cutoff);
  }, [startsAtMs]);

  const beforeStart = now !== null && Number.isFinite(startsAtMs) && now < startsAtMs;
  const eligible = Boolean(actor?.eligible && token);
  const canReact = eligible && beforeStart && summary?.can_react !== false;
  const canComment = eligible && beforeStart && !actor?.communication_restricted;

  async function setReaction(desired: ReactionKind | null) {
    if (!token || !canReact || reactionBusy) return;
    if (!Number.isFinite(startsAtMs) || clientClockNow() >= startsAtMs) {
      setNow(clientClockNow());
      setReactionError({ literal: 'Reactions close when the event starts.' });
      return;
    }
    const controller = new AbortController();
    reactionMutation.current?.abort();
    reactionMutation.current = controller;
    setReactionBusy(true);
    setReactionPending(desired);
    setReactionError(null);
    try {
      const next = await api<ReactionSummary>(`/events/${encodeURIComponent(eventId)}/reactions`, {
        token,
        method: 'POST',
        body: { reaction: desired },
        signal: controller.signal,
      });
      if (!controller.signal.aborted) {
        setSummary(next);
        setReactionPending(undefined);
        onReactionChanged?.();
      }
    } catch (error) {
      if (!controller.signal.aborted) setReactionError(requestMessage(error, 'Reaction update'));
    } finally {
      if (!controller.signal.aborted) setReactionBusy(false);
      if (reactionMutation.current === controller) reactionMutation.current = null;
    }
  }

  async function sendComment(payload = pendingComment) {
    if (!token || !canComment || commentMutation.current) return;
    if (!Number.isFinite(startsAtMs) || clientClockNow() >= startsAtMs) {
      setNow(clientClockNow());
      setCommentError({ literal: 'Comments close when the event starts.' });
      return;
    }
    const request = payload ?? (draft.trim()
      ? { body: draft.trim(), clientKey: crypto.randomUUID() }
      : null);
    if (!request) return;
    setPendingComment(request);
    const controller = new AbortController();
    commentMutation.current = controller;
    setCommentBusy(true);
    setCommentError(null);
    try {
      const created = await api<ContentItem>(`/events/${encodeURIComponent(eventId)}/comments`, {
        token,
        method: 'POST',
        body: { body: request.body, client_key: request.clientKey },
        signal: controller.signal,
      });
      if (!controller.signal.aborted) {
        setComments((current) => mergeComments(current, [created]));
        setPendingComment(null);
        setDraft('');
      }
    } catch (error) {
      if (!controller.signal.aborted) setCommentError(requestMessage(error, 'Comment'));
    } finally {
      if (!controller.signal.aborted) setCommentBusy(false);
      if (commentMutation.current === controller) commentMutation.current = null;
    }
  }

  async function removeComment(item: ContentItem) {
    if (!token || !item.mine || !beforeStart || deleteMutation.current) return;
    const controller = new AbortController();
    deleteMutation.current = controller;
    setCommentError(null);
    try {
      const removed = await api<ContentItem>(
        `/events/${encodeURIComponent(eventId)}/comments/${encodeURIComponent(item.id)}`,
        { token, method: 'DELETE', signal: controller.signal },
      );
      if (!controller.signal.aborted) {
        setComments((current) => current.map((candidate) => candidate.id === removed.id ? removed : candidate));
      }
    } catch (error) {
      if (!controller.signal.aborted) setCommentError(requestMessage(error, 'Comment removal'));
    } finally {
      if (deleteMutation.current === controller) deleteMutation.current = null;
    }
  }

  async function restoreComment(item: ContentItem, signal: AbortSignal) {
    const query = new URLSearchParams({ before_sequence: String(item.sequence + 1), limit: '100' });
    try {
      const page = await api<ContentPage>(`/events/${encodeURIComponent(eventId)}/comments?${query}`, { token, signal });
      return page.items.find((candidate) => candidate.id === item.id) ?? null;
    } catch {
      return null;
    }
  }

  function updateComment(updated: ContentItem) {
    setComments((current) => current.map((candidate) => candidate.id === updated.id ? updated : candidate));
  }

  return (
    <section className={styles.social} aria-labelledby={`social-heading-${eventId}`}>
      <div className={styles.sectionHeading}>
        <p className={styles.muted}>{t('Event conversation')}</p>
        <h2 id={`social-heading-${eventId}`}>{t('Reactions and comments')}</h2>
      </div>

      <fieldset className={styles.reactionGroup}>
        <legend>{t('React to this event')}</legend>
        <div className={styles.reactionPicker}>
          {REACTIONS.map(({ kind, label, icon }) => (
            <button
              key={kind}
              className={styles.reactionButton}
              type="button"
              aria-label={t('{action} {reaction} reaction ({count})', {
                action: t(summary?.mine === kind ? 'Remove' : 'Choose'),
                reaction: t(label),
                count: summary?.counts[kind] ?? 0,
              })}
              aria-pressed={summary?.mine === kind}
              disabled={!canReact || reactionBusy || reactionPending !== undefined}
              onClick={() => void setReaction(summary?.mine === kind ? null : kind)}
            >
              <span className={styles.reactionIcon} aria-hidden="true">{icon}</span>
              <span>{t(label)}</span>
              <span>{summary?.counts[kind] ?? 0}</span>
            </button>
          ))}
        </div>
        <p className={styles.muted}>
          {summary
            ? t('{count} reactions. Reactions show interest and do not reserve a seat.', { count: summary.total })
            : t('Loading reactions…')}
        </p>
        {reactionError ? (
          <div>
            <p className={styles.errorText} role="alert">{translateMessage(reactionError, t)}</p>
            {reactionPending !== undefined ? (
              <button className={styles.smallButton} type="button" onClick={() => void setReaction(reactionPending)} disabled={reactionBusy}>
                {t('Retry reaction update')}
              </button>
            ) : null}
          </div>
        ) : null}
        {!beforeStart && now !== null ? <p className={styles.muted}>{t('Reactions are read-only after the event starts.')}</p> : null}
        {!actor && beforeStart ? <p className={styles.muted}>{t('Sign in with an eligible PLM account to react.')}</p> : null}
        {actor && !actor.eligible ? <p className={styles.muted}>{t('Reactions are available to eligible PLM stakeholders.')}</p> : null}
      </fieldset>

      <div className={styles.sectionHeading}>
        <h3>{t('Comments')}</h3>
        <p className={styles.muted}>{t('Comments are public to visitors of this published event.')}</p>
      </div>
      {commentsError ? (
        <div>
          <p className={styles.errorText} role="alert">{translateMessage(commentsError, t)}</p>
          <button className={styles.smallButton} type="button" onClick={() => void loadComments()} disabled={commentsLoading}>
            {t('Retry loading comments')}
          </button>
        </div>
      ) : null}
      {commentsLoading && comments.length === 0 ? <p className={styles.muted} role="status">{t('Loading comments…')}</p> : null}
      {!commentsLoading && comments.length === 0 && !commentsError ? <p className={styles.muted}>{t('No comments yet.')}</p> : null}

      <div className={styles.commentList} aria-label={t('Event comments')}>
        {comments.map((item) => (
          <article className={styles.comment} key={item.id}>
            <header className={styles.itemHeader}>
              <strong>{item.author_label}</strong>
              <time dateTime={item.created_at}>{formatDate(item.created_at, preferences.language)} · {formatTime(item.created_at, preferences.language)}</time>
            </header>
            {item.removed
              ? <p className={`${styles.itemBody} ${styles.muted}`}>{t('This comment was removed.')}</p>
              : item.locally_hidden
                ? <p className={`${styles.itemBody} ${styles.muted}`}>{t('This comment is hidden for you.')}</p>
                : item.body !== null
                  ? <p className={styles.itemBody}>{item.body}</p>
                  : <p className={`${styles.itemBody} ${styles.muted}`}>{t('This comment is unavailable.')}</p>}
            {!item.removed ? (
              <>
                {item.mine && beforeStart && token ? (
                  <button className={styles.smallButton} type="button" onClick={() => void removeComment(item)}>
                    {t('Remove my comment')}
                  </button>
                ) : null}
                <ContentSafetyControls
                  eventId={eventId}
                  kind="comment"
                  item={item}
                  actor={actor}
                  token={token}
                  onChange={updateComment}
                  onRestore={restoreComment}
                />
              </>
            ) : null}
          </article>
        ))}
      </div>
      {nextBefore !== null ? (
        <button className={styles.secondaryButton} type="button" onClick={() => void loadComments(nextBefore)} disabled={loadingOlder || commentsLoading}>
          {loadingOlder ? t('Loading older comments…') : t('Load older comments')}
        </button>
      ) : null}

      {canComment ? (
        <form className={styles.form} onSubmit={(event) => { event.preventDefault(); void sendComment(); }}>
          <label htmlFor={`comment-input-${eventId}`}>{t('Add a comment')}</label>
          <textarea
            className={styles.textarea}
            id={`comment-input-${eventId}`}
            value={pendingComment?.body ?? draft}
            maxLength={2000}
            required
            disabled={pendingComment !== null || commentBusy}
            onChange={(event) => setDraft(event.target.value)}
          />
          <div className={styles.formFooter}>
            <span className={styles.muted}>{(pendingComment?.body ?? draft).trim().length}/2000</span>
            {pendingComment ? (
              <button className={styles.primaryButton} type="button" onClick={() => void sendComment(pendingComment)} disabled={commentBusy}>
                {commentBusy ? t('Sending…') : t('Retry unchanged comment')}
              </button>
            ) : (
              <button className={styles.primaryButton} type="submit" disabled={commentBusy || !draft.trim()}>
                {commentBusy ? t('Sending…') : t('Post comment')}
              </button>
            )}
          </div>
          {commentError ? <p className={styles.errorText} role="alert">{translateMessage(commentError, t)}</p> : null}
          {pendingComment ? <p className={styles.muted}>{t('The pending comment is locked so a retry sends the same text with the same request key.')}</p> : null}
        </form>
      ) : !beforeStart && now !== null ? (
        <p className={styles.muted}>{t('Comments remain readable, but new comments close when the event starts.')}</p>
      ) : actor?.communication_restricted ? (
        <p className={styles.muted}>{t('Posting comments is temporarily unavailable for this account. Existing registrations remain unchanged.')}</p>
      ) : !actor && beforeStart ? (
        <p className={styles.muted}>{t('Sign in with an eligible PLM account to comment.')}</p>
      ) : actor && !actor.eligible ? (
        <p className={styles.muted}>{t('Comments are available to eligible PLM stakeholders.')}</p>
      ) : null}
    </section>
  );
}

export function EventSocialPreview({ eventId }: { eventId: string }) {
  const { token, version } = useSession();
  const requestKey = `${eventId}:${version}:${token ?? 'guest'}`;
  return <EventSocialPreviewSession key={requestKey} eventId={eventId} token={token} />;
}

function EventSocialPreviewSession({ eventId, token }: { eventId: string; token: string | null }) {
  const t = useT();
  const [state, setState] = useState<{
    preview: { summary: ReactionSummary; comments: ContentItem[] } | null;
    failed: boolean;
    loading: boolean;
  }>({ preview: null, failed: false, loading: true });

  useEffect(() => {
    const controller = new AbortController();
    const query = new URLSearchParams({ limit: '1' });
    Promise.all([
      api<ReactionSummary>(`/events/${encodeURIComponent(eventId)}/reactions`, { token, signal: controller.signal }),
      api<ContentPage>(`/events/${encodeURIComponent(eventId)}/comments?${query}`, { token, signal: controller.signal }),
    ]).then(([summary, page]) => {
      if (!controller.signal.aborted) {
        setState({ preview: { summary, comments: page.items.slice(0, 1) }, failed: false, loading: false });
      }
    }).catch(() => {
      if (!controller.signal.aborted) setState({ preview: null, failed: true, loading: false });
    });
    return () => controller.abort();
  }, [eventId, token]);

  return (
    <section className={`${styles.social} ${styles.socialCompact}`} aria-label={t('Event social preview')}>
      {state.failed ? <p className={styles.muted}>{t('Event conversation preview is unavailable.')}</p> : null}
      {state.loading ? <p className={styles.muted} role="status">{t('Loading event conversation…')}</p> : null}
      {state.preview ? (
        <>
          <div className={styles.previewCounts} role="group" aria-label={t('Reaction counts')}>
            {REACTIONS.map(({ kind, label, icon }) => (
              <span key={kind} role="img" aria-label={t('{reaction}: {count}', { reaction: t(label), count: state.preview?.summary.counts[kind] ?? 0 })}>
                <span aria-hidden="true">{icon}</span> {state.preview?.summary.counts[kind] ?? 0}
              </span>
            ))}
          </div>
          {state.preview.comments.map((item) => (
            <article className={styles.previewComment} key={item.id}>
              <strong>{item.author_label}</strong>
              <p>{item.removed
                ? t('This comment was removed.')
                : item.locally_hidden
                  ? t('This comment is hidden for you.')
                  : item.body ?? t('This comment is unavailable.')}</p>
            </article>
          ))}
          <Link className={styles.linkButton} href={`/events?eventId=${encodeURIComponent(eventId)}`}>
            {t('Open event comments')}
          </Link>
        </>
      ) : null}
    </section>
  );
}
