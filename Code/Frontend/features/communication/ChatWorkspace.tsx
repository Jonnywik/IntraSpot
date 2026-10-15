'use client';

import Link from 'next/link';
import { useCallback, useEffect, useRef, useState } from 'react';
import { api, ApiError } from '@/lib/api';
import { formatDate, formatTime } from '@/lib/date';
import { useSession } from '@/lib/session';
import type { ChatInboxItem, ChatThread, ContentItem } from '@/lib/types';
import { ContentSafetyControls } from './ContentSafetyControls';
import styles from './communication.module.css';

function countdown(deletesAt: string, now: number) {
  const difference = Date.parse(deletesAt) - now;
  if (!Number.isFinite(difference)) return 'Deletion time unavailable';
  if (difference <= 0) return 'Chat access has ended';
  const seconds = Math.floor(difference / 1000);
  const days = Math.floor(seconds / 86_400);
  const hours = Math.floor((seconds % 86_400) / 3_600);
  const minutes = Math.floor((seconds % 3_600) / 60);
  const remainingSeconds = seconds % 60;
  const parts = [
    days ? `${days}d` : null,
    hours || days ? `${hours}h` : null,
    minutes || hours || days ? `${minutes}m` : null,
    !days ? `${remainingSeconds}s` : null,
  ].filter(Boolean);
  return `Deletes in ${parts.join(' ')}`;
}

function inboxErrorText(error: unknown) {
  if (error instanceof ApiError && error.status === 401) return 'Your sign-in expired. Sign in again to view event chats.';
  if (error instanceof ApiError && error.status === 403) return 'The chat list is unavailable for this account.';
  return 'The chat list could not be loaded. Check your connection and retry.';
}

function threadErrorText(error: unknown) {
  if (error instanceof ApiError && error.status === 401) return 'Your sign-in expired. Sign in again, then retry.';
  if (error instanceof ApiError && error.status === 403) return 'Chat access or sending is currently restricted. Existing messages remain available.';
  if (error instanceof ApiError && error.status === 404) return 'This chat could not be refreshed. Existing messages remain available.';
  return 'Messages could not be loaded. Check your connection and retry.';
}

function clientClockNow() {
  return Date.now();
}

function mergeMessages(existing: ContentItem[], incoming: ContentItem[]) {
  const byId = new Map(existing.map((item) => [item.id, item]));
  for (const item of incoming) byId.set(item.id, item);
  return [...byId.values()].sort((left, right) => left.sequence - right.sequence);
}

function mergeRemovedIds(existing: string[] | undefined, incoming: string[] | undefined) {
  return [...new Set([...(existing ?? []), ...(incoming ?? [])])];
}

function applyRemovedIds(items: ContentItem[], removedIds: string[]) {
  if (removedIds.length === 0) return items;
  const removed = new Set(removedIds);
  return items.map((item) => removed.has(item.id) ? { ...item, body: null, removed: true } : item);
}

export function ChatWorkspace({ eventId }: { eventId: string | null }) {
  const { actor, token, authLoading, version } = useSession();
  const requestKey = `${version}:${token ?? 'guest'}`;
  const [now, setNow] = useState<number | null>(null);
  const [inboxState, setInboxState] = useState<{ key: string; items: ChatInboxItem[] } | null>(null);
  const [inboxError, setInboxError] = useState<{ key: string; message: string } | null>(null);
  const [inboxLoadingKey, setInboxLoadingKey] = useState<string | null>(null);
  const [refreshInbox, setRefreshInbox] = useState(0);

  useEffect(() => {
    const initial = window.setTimeout(() => setNow(Date.now()), 0);
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => {
      window.clearTimeout(initial);
      window.clearInterval(timer);
    };
  }, []);

  useEffect(() => {
    if (!token) {
      return;
    }
    let disposed = false;
    let controller: AbortController | null = null;
    let inFlight = false;
    const load = async (showLoading: boolean) => {
      if (disposed || inFlight || document.visibilityState !== 'visible') return;
      inFlight = true;
      controller = new AbortController();
      if (showLoading) setInboxLoadingKey(requestKey);
      setInboxError((current) => current?.key === requestKey ? null : current);
      try {
        const items = await api<ChatInboxItem[]>('/me/chats', { token, signal: controller.signal });
        if (!disposed && !controller.signal.aborted) setInboxState({ key: requestKey, items });
      } catch (error) {
        if (!disposed && !controller.signal.aborted) setInboxError({ key: requestKey, message: inboxErrorText(error) });
      } finally {
        if (!disposed && !controller?.signal.aborted) setInboxLoadingKey(null);
        inFlight = false;
        controller = null;
      }
    };
    const onVisibilityChange = () => {
      if (document.visibilityState === 'visible') void load(false);
    };
    void load(true);
    const timer = window.setInterval(() => {
      if (document.visibilityState === 'visible') void load(false);
    }, 30_000);
    document.addEventListener('visibilitychange', onVisibilityChange);
    return () => {
      disposed = true;
      controller?.abort();
      document.removeEventListener('visibilitychange', onVisibilityChange);
      window.clearInterval(timer);
    };
  }, [token, requestKey, refreshInbox]);

  const inboxItems = inboxState?.key === requestKey ? inboxState.items : null;
  const currentInboxError = inboxError?.key === requestKey ? inboxError.message : null;
  const inboxLoading = Boolean(token && inboxItems === null && (inboxLoadingKey === requestKey || !currentInboxError));
  const selected = eventId ? inboxItems?.find((item) => item.event_id === eventId) ?? null : null;
  const selectedExpired = Boolean(selected && now !== null && Date.parse(selected.deletes_at) <= now);
  const visibleItems = (inboxItems ?? []).filter((item) => now === null || Date.parse(item.deletes_at) > now);

  useEffect(() => {
    if (!inboxItems?.length) return;
    const reference = clientClockNow();
    const nextBoundary = inboxItems
      .flatMap((item) => [Date.parse(item.ends_at), Date.parse(item.deletes_at)])
      .filter((timestamp) => Number.isFinite(timestamp) && timestamp > reference)
      .reduce<number | null>((nearest, timestamp) => nearest === null || timestamp < nearest ? timestamp : nearest, null);
    if (nextBoundary === null) return;
    const timer = window.setTimeout(() => setNow(clientClockNow()), Math.max(0, nextBoundary - reference));
    return () => window.clearTimeout(timer);
  }, [inboxItems, now]);

  return (
    <section className="stack">
      <header className="page-heading">
        <p className="eyebrow">YOUR EVENTS</p>
        <h1>Event chats</h1>
      </header>
      {authLoading && !actor ? <p className="panel muted" role="status">Checking your account…</p> : null}
      {!authLoading && (!actor || !token) ? <p className="panel muted">Sign in with an eligible PLM account to view confirmed event chats.</p> : null}
      {actor && token ? (
        <div className={styles.chatLayout} data-has-selection={Boolean(eventId)}>
          <aside className={styles.inbox} id="chat-inbox" aria-labelledby="chat-inbox-heading">
            <div className={styles.chatHeading}>
              <div>
                <h2 id="chat-inbox-heading">All event chats</h2>
                <p className={styles.muted}>Active and archived chats appear together.</p>
              </div>
              <button className={styles.smallButton} type="button" onClick={() => setRefreshInbox((value) => value + 1)} disabled={inboxLoading}>
                Refresh
              </button>
            </div>
            {inboxLoading ? <p className={styles.muted} role="status">Loading chats…</p> : null}
            {currentInboxError ? (
              <div>
                <p className={styles.errorText} role="alert">{currentInboxError}</p>
                <button className={styles.smallButton} type="button" onClick={() => setRefreshInbox((value) => value + 1)}>
                  Retry chat list
                </button>
              </div>
            ) : null}
            {inboxItems && visibleItems.length === 0 && !inboxLoading && !currentInboxError ? (
              <p className={styles.muted}>No confirmed event chats are available.</p>
            ) : null}
            {inboxItems && visibleItems.length > 0 ? (
              <nav className={styles.inboxList} aria-label="Event chat list">
                {visibleItems.map((item) => {
                  const ended = item.status === 'archived' || (now !== null && Date.parse(item.ends_at) <= now);
                  return (
                    <Link
                      key={item.event_id}
                      className={styles.inboxItem}
                      href={`/chat?eventId=${encodeURIComponent(item.event_id)}`}
                      aria-current={item.event_id === eventId ? 'page' : undefined}
                    >
                      <span className={styles.inboxItemHeader}>
                        <strong>{item.organization_name}</strong>
                        {ended ? <span className={styles.archivedBadge}>Archived</span> : null}
                      </span>
                      <h3>{item.event_title}</h3>
                      {ended ? (
                        <span className={styles.muted} role="status">{now === null ? 'Calculating retention window…' : countdown(item.deletes_at, now)}</span>
                      ) : (
                        <span className={styles.muted}>Event ends {formatDate(item.ends_at)} · {formatTime(item.ends_at)}</span>
                      )}
                      {item.latest_at ? (
                        <span className={styles.muted}>Latest activity {formatDate(item.latest_at)} · {formatTime(item.latest_at)}</span>
                      ) : <span className={styles.muted}>No messages yet</span>}
                    </Link>
                  );
                })}
              </nav>
            ) : null}
          </aside>

          {eventId ? selected && !selectedExpired ? (
            <ChatThreadView key={`${requestKey}:${eventId}`} item={selected} actor={actor} token={token} version={version} now={now} />
          ) : selectedExpired ? (
            <section className={styles.thread} aria-labelledby="chat-expired-heading">
              <h2 id="chat-expired-heading">Chat access ended</h2>
              <p className={styles.muted}>Access ends 72 hours after the event’s scheduled end.</p>
            </section>
          ) : inboxItems ? (
            <section className={styles.thread} aria-labelledby="chat-unavailable-heading">
              <h2 id="chat-unavailable-heading">Chat unavailable</h2>
              <p className={styles.muted}>This event chat is not available to this account. Confirmed registration is required.</p>
            </section>
          ) : (
            <section className={styles.thread} aria-live="polite">
              <p className={styles.muted}>{inboxLoading ? 'Checking chat access…' : 'Refresh the chat list to check access.'}</p>
            </section>
          ) : (
            <section className={styles.thread} aria-labelledby="chat-prompt-heading">
              <h2 id="chat-prompt-heading">Choose an event chat</h2>
              <p className={styles.muted}>Open a chat from your confirmed event registrations. Chats become read-only at the scheduled event end and remain available for 72 hours.</p>
            </section>
          )}
        </div>
      ) : null}
    </section>
  );
}

function ChatThreadView({
  item,
  actor,
  token,
  version,
  now,
}: {
  item: ChatInboxItem;
  actor: NonNullable<ReturnType<typeof useSession>['actor']>;
  token: string;
  version: number;
  now: number | null;
}) {
  const [thread, setThread] = useState<ChatThread | null>(null);
  const [threadLoading, setThreadLoading] = useState(true);
  const [threadError, setThreadError] = useState<string | null>(null);
  const [accessDenied, setAccessDenied] = useState(false);
  const [loadingOlder, setLoadingOlder] = useState(false);
  const [draft, setDraft] = useState('');
  const [pendingMessage, setPendingMessage] = useState<{ body: string; clientKey: string } | null>(null);
  const [sendError, setSendError] = useState<string | null>(null);
  const [personalReviewPending, setPersonalReviewPending] = useState(false);
  const [sending, setSending] = useState(false);
  const [refreshThread, setRefreshThread] = useState(0);
  const threadRef = useRef<ChatThread | null>(null);
  const pollController = useRef<AbortController | null>(null);
  const olderController = useRef<AbortController | null>(null);
  const sendController = useRef<AbortController | null>(null);
  const polling = useRef(false);
  const olderLoadingRef = useRef(false);
  const endAt = Date.parse(item.ends_at);
  const deleteAt = Date.parse(item.deletes_at);
  const ended = item.status === 'archived' || now !== null && Number.isFinite(endAt) && now >= endAt;
  const expired = now !== null && Number.isFinite(deleteAt) && now >= deleteAt;
  const canSend = Boolean(
    thread?.can_send && now !== null && !ended && !expired &&
    Number.isFinite(endAt) && now < endAt && Number.isFinite(deleteAt) && now < deleteAt,
  );

  const replaceThread = useCallback((next: ChatThread | null) => {
    threadRef.current = next;
    setThread(next);
  }, []);

  const revokeAccess = useCallback((error: unknown) => {
    if (!(error instanceof ApiError) || error.code !== 'chat_access_forbidden') return false;
    replaceThread(null);
    setAccessDenied(true);
    setThreadError(threadErrorText(error));
    pollController.current?.abort();
    olderController.current?.abort();
    sendController.current?.abort();
    setSending(false);
    setPendingMessage(null);
    setDraft('');
    setLoadingOlder(false);
    return true;
  }, [replaceThread]);

  useEffect(() => {
    let disposed = false;
    let pollTimer: number | null = null;
    let initial: AbortController | null = null;
    const deletion = Date.parse(item.deletes_at);

    const loadInitial = async () => {
      initial = new AbortController();
      try {
        const result = await api<ChatThread>(`/events/${encodeURIComponent(item.event_id)}/chat?limit=50`, {
          token,
          signal: initial.signal,
        });
        if (!disposed && !initial.signal.aborted) {
          setPersonalReviewPending(false);
          const removedIds = result.removed_ids ?? [];
          replaceThread({ ...result, removed_ids: removedIds, items: applyRemovedIds(result.items, removedIds) });
        }
      } catch (error) {
        if (!disposed && !initial?.signal.aborted) {
          if (!revokeAccess(error)) setThreadError(threadErrorText(error));
        }
      } finally {
        if (!disposed && !initial?.signal.aborted) setThreadLoading(false);
      }
    };

    const poll = async () => {
      if (disposed || !threadRef.current || polling.current || document.visibilityState !== 'visible' || Date.now() >= deletion) return;
      polling.current = true;
      const controller = new AbortController();
      pollController.current = controller;
      const current = threadRef.current;
      const newest = current?.items.reduce<number | null>((latest, message) => latest === null || message.sequence > latest ? message.sequence : latest, null) ?? null;
      const query = new URLSearchParams({ limit: '50' });
      if (newest !== null) query.set('after_sequence', String(newest));
      try {
        const result = await api<ChatThread>(`/events/${encodeURIComponent(item.event_id)}/chat?${query}`, {
          token,
          signal: controller.signal,
        });
        if (!disposed && !controller.signal.aborted) {
          setThread((previous) => {
            const removedIds = mergeRemovedIds(previous?.removed_ids, result.removed_ids);
            const merged = mergeMessages(previous?.items ?? [], result.items);
            const next = previous
              ? {
                  ...result,
                  removed_ids: removedIds,
                  items: applyRemovedIds(merged, removedIds),
                  next_before: previous.next_before,
                }
              : { ...result, removed_ids: removedIds, items: applyRemovedIds(merged, removedIds) };
            threadRef.current = next;
            return next;
          });
          setThreadError(null);
        }
      } catch (error) {
        if (!disposed && !controller.signal.aborted && !revokeAccess(error)) {
          setThreadError('Messages could not be refreshed. The conversation remains available; retry if updates stop.');
        }
      } finally {
        if (pollController.current === controller) pollController.current = null;
        polling.current = false;
      }
    };

    const onVisibilityChange = () => {
      if (document.visibilityState === 'visible') void poll();
    };
    void loadInitial();
    pollTimer = window.setInterval(() => void poll(), 5000);
    document.addEventListener('visibilitychange', onVisibilityChange);
    return () => {
      disposed = true;
      initial?.abort();
      pollController.current?.abort();
      olderController.current?.abort();
      sendController.current?.abort();
      document.removeEventListener('visibilitychange', onVisibilityChange);
      if (pollTimer !== null) window.clearInterval(pollTimer);
      polling.current = false;
      olderLoadingRef.current = false;
    };
  }, [item.event_id, item.ends_at, item.deletes_at, token, version, refreshThread, replaceThread, revokeAccess]);

  useEffect(() => {
    if (now !== null && Number.isFinite(endAt) && now >= endAt && sendController.current) {
      sendController.current.abort();
      setSending(false);
    }
  }, [now, endAt]);

  async function loadOlder() {
    const cursor = thread?.next_before;
    if (!token || !thread || cursor === null || cursor === undefined || olderLoadingRef.current) return;
    const controller = new AbortController();
    olderController.current?.abort();
    olderController.current = controller;
    olderLoadingRef.current = true;
    setLoadingOlder(true);
    setThreadError(null);
    const query = new URLSearchParams({ before_sequence: String(cursor), limit: '50' });
    try {
      const page = await api<ChatThread>(`/events/${encodeURIComponent(item.event_id)}/chat?${query}`, { token, signal: controller.signal });
      if (!controller.signal.aborted) {
        setThread((current) => {
          const removedIds = mergeRemovedIds(current?.removed_ids, page.removed_ids);
          const merged = mergeMessages(current?.items ?? [], page.items);
          const next = current
            ? { ...page, removed_ids: removedIds, items: applyRemovedIds(merged, removedIds) }
            : { ...page, removed_ids: removedIds, items: applyRemovedIds(merged, removedIds) };
          threadRef.current = next;
          return next;
        });
      }
    } catch (error) {
      if (!controller.signal.aborted && !revokeAccess(error)) setThreadError(threadErrorText(error));
    } finally {
      if (!controller.signal.aborted) setLoadingOlder(false);
      if (olderController.current === controller) olderController.current = null;
      olderLoadingRef.current = false;
    }
  }

  async function sendMessage(payload = pendingMessage) {
    if (!token || !canSend || sendController.current) return;
    if (!Number.isFinite(endAt) || clientClockNow() >= endAt || !Number.isFinite(deleteAt) || clientClockNow() >= deleteAt) return;
    const request = payload ?? (draft.trim() ? { body: draft.trim(), clientKey: crypto.randomUUID() } : null);
    if (!request) return;
    setPendingMessage(request);
    const controller = new AbortController();
    sendController.current = controller;
    setSending(true);
    setSendError(null);
    try {
      const created = await api<ContentItem>(`/events/${encodeURIComponent(item.event_id)}/chat/messages`, {
        token,
        method: 'POST',
        body: { body: request.body, client_key: request.clientKey },
        signal: controller.signal,
      });
      if (!controller.signal.aborted) {
        setThread((current) => {
          if (!current) return current;
          const next = {
            ...current,
            items: applyRemovedIds(mergeMessages(current.items, [created]), current.removed_ids ?? []),
          };
          threadRef.current = next;
          return next;
        });
        setPendingMessage(null);
        setDraft('');
      }
    } catch (error) {
      if (!controller.signal.aborted) {
        if (error instanceof ApiError && error.code === 'personal_review_pending') {
          const current = threadRef.current;
          if (current) replaceThread({ ...current, can_send: false });
          setPersonalReviewPending(true);
          setSendError(null);
        } else if (!revokeAccess(error)) setSendError(threadErrorText(error));
      }
    } finally {
      if (!controller.signal.aborted) setSending(false);
      if (sendController.current === controller) sendController.current = null;
    }
  }

  async function restoreMessage(itemToRestore: ContentItem, signal: AbortSignal) {
    const query = new URLSearchParams({ before_sequence: String(itemToRestore.sequence + 1), limit: '100' });
    try {
      const page = await api<ChatThread>(`/events/${encodeURIComponent(item.event_id)}/chat?${query}`, { token, signal });
      return page.items.find((candidate) => candidate.id === itemToRestore.id) ?? null;
    } catch {
      return null;
    }
  }

  function updateMessage(updated: ContentItem) {
    setThread((current) => {
      if (!current) return current;
      const next = { ...current, items: current.items.map((candidate) => candidate.id === updated.id ? updated : candidate) };
      threadRef.current = next;
      return next;
    });
  }

  const readOnly = Boolean(ended || expired || thread && !thread.can_send);
  const localCutoff = ended || expired;

  return (
    <section className={styles.thread} aria-labelledby="chat-thread-heading">
      <header className={styles.chatHeading}>
        <div>
          <Link href="#chat-inbox" className={styles.linkButton}>All event chats</Link>
          <p className={styles.muted}>{item.organization_name}</p>
          <h2 id="chat-thread-heading">{item.event_title}</h2>
        </div>
        {ended || item.status === 'archived' ? <span className={styles.archivedBadge}>Archived</span> : null}
      </header>
      <div className={styles.chatMeta}>
        <p>Scheduled end: <time dateTime={item.ends_at}>{formatDate(item.ends_at)} · {formatTime(item.ends_at)}</time></p>
        <p role="status">{now === null ? 'Calculating retention window…' : countdown(item.deletes_at, now)}</p>
      </div>
      {threadLoading && !thread ? <p className={styles.muted} role="status">Loading conversation…</p> : null}
      {threadError ? (
        <div>
          <p className={styles.errorText} role={accessDenied ? 'alert' : 'status'}>{threadError}</p>
          <button className={styles.smallButton} type="button" onClick={() => {
            setThreadError(null);
            setAccessDenied(false);
            setThreadLoading(true);
            setRefreshThread((value) => value + 1);
          }} disabled={threadLoading}>
            Retry conversation
          </button>
        </div>
      ) : null}
      {expired ? <p className={styles.readOnlyNotice} role="status">Chat access has ended. Messages are no longer available.</p> : null}
      {ended && !expired ? <p className={styles.readOnlyNotice} role="status">This chat is archived and read-only after its scheduled end.</p> : null}
      {thread && !thread.can_send && !localCutoff ? (
        <p className={styles.readOnlyNotice} role="status">
          {personalReviewPending
            ? 'Sending is paused while this account is under personal review. Existing messages remain readable.'
            : actor.communication_restricted
            ? 'Sending is temporarily paused for this account. Existing registrations remain unchanged.'
            : 'Sending is currently unavailable. Messages remain readable while this chat is active.'}
        </p>
      ) : null}
      {thread?.next_before !== null && thread?.next_before !== undefined && !expired ? (
        <button className={styles.secondaryButton} type="button" onClick={() => void loadOlder()} disabled={loadingOlder || threadLoading}>
          {loadingOlder ? 'Loading older messages…' : 'Load older messages'}
        </button>
      ) : null}
      {thread && !expired ? (
        <div className={styles.chatItems} role="log" aria-label="Messages in this event chat" aria-live="polite" aria-relevant="additions text">
          {thread.items.length === 0 ? <p className={styles.muted}>No messages yet.</p> : null}
          {thread.items.map((message) => (
            <article className={`${styles.chatMessage} ${message.mine ? styles.mine : ''}`} key={message.id}>
              <header className={styles.itemHeader}>
                <strong>{message.mine ? 'You' : ended ? 'PLM member' : message.author_label}</strong>
                <time dateTime={message.created_at}>{formatDate(message.created_at)} · {formatTime(message.created_at)}</time>
              </header>
              {message.removed
                ? <p className={`${styles.itemBody} ${styles.muted}`}>This message was removed.</p>
                : message.locally_hidden
                  ? <p className={`${styles.itemBody} ${styles.muted}`}>This message is hidden for you.</p>
                  : message.body !== null
                    ? <p className={styles.itemBody}>{message.body}</p>
                    : <p className={`${styles.itemBody} ${styles.muted}`}>This message is unavailable.</p>}
              {!message.removed ? (
                <ContentSafetyControls
                  eventId={item.event_id}
                  kind="message"
                  item={message}
                  actor={actor}
                  token={token}
                  onChange={updateMessage}
                  onRestore={restoreMessage}
                />
              ) : null}
            </article>
          ))}
        </div>
      ) : null}
      {canSend ? (
        <form className={styles.form} onSubmit={(event) => { event.preventDefault(); void sendMessage(); }}>
          <label htmlFor={`chat-message-${item.event_id}`}>Write a message</label>
          <textarea
            className={styles.textarea}
            id={`chat-message-${item.event_id}`}
            value={pendingMessage?.body ?? draft}
            maxLength={2000}
            required
            disabled={pendingMessage !== null || sending}
            onChange={(event) => setDraft(event.target.value)}
          />
          <div className={styles.formFooter}>
            <span className={styles.muted}>{(pendingMessage?.body ?? draft).trim().length}/2000</span>
            {pendingMessage ? (
              <button className={styles.primaryButton} type="button" onClick={() => void sendMessage(pendingMessage)} disabled={sending || !canSend}>
                {sending ? 'Sending…' : 'Retry unchanged message'}
              </button>
            ) : (
              <button className={styles.primaryButton} type="submit" disabled={sending || !draft.trim()}>
                {sending ? 'Sending…' : 'Send message'}
              </button>
            )}
          </div>
          {sendError ? <p className={styles.errorText} role="alert">{sendError}</p> : null}
          {pendingMessage ? <p className={styles.muted}>The pending message is locked so a retry uses the same text and request key.</p> : null}
        </form>
      ) : null}
      {readOnly && pendingMessage ? <p className={styles.muted}>This chat is read-only, so the pending message cannot be retried.</p> : null}
    </section>
  );
}
