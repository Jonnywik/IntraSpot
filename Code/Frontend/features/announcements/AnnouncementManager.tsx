'use client';

import { useEffect, useRef, useState, type FormEvent } from 'react';
import { ApiError, api } from '@/lib/api';
import { formatDate, formatTime } from '@/lib/date';
import { usePreferences } from '@/lib/preferences';
import { useApiResource } from '@/lib/use-api-resource';
import type { Announcement, AnnouncementRevision } from '@/lib/types';
import { announcementApiMessage, type AnnouncementMessage, useAnnouncementText } from './messages';
import styles from './announcements.module.css';

type Audience = Announcement['audience'];
type AudienceChoice = Audience | '';
type AnnouncementForm = { title: string; body: string; audience: AudienceChoice };
type EditTarget = { id: string; version: number; state: Announcement['state'] };
type CreateAttempt = {
  client_key: string;
  title: string;
  body: string;
  audience: Audience;
};
type AnnouncementPayload = { title: string; body: string; audience: Audience };
type Conflict = { id: string; action: 'edit' | 'remove'; latest?: Announcement };

const EMPTY_FORM: AnnouncementForm = { title: '', body: '', audience: '' };
const MANAGE_PAGE_SIZE = 100;

export function AnnouncementManager({ organizationId, token, sessionVersion, role, approved }: {
  organizationId: string;
  token: string;
  sessionVersion: number;
  role: string;
  approved: boolean;
}) {
  const text = useAnnouncementText();
  const { preferences: { language } } = usePreferences();
  const canManage = role === 'owner' || role === 'admin';
  const listPath = approved && canManage
    ? `/organizations/${encodeURIComponent(organizationId)}/announcements/manage?limit=100&offset=0`
    : null;
  const announcements = useApiResource<Announcement[]>(listPath, token);
  const [form, setForm] = useState<AnnouncementForm>(EMPTY_FORM);
  const [creating, setCreating] = useState(false);
  const [editing, setEditing] = useState<EditTarget | null>(null);
  const [createAttempt, setCreateAttempt] = useState<CreateAttempt | null>(null);
  const [createUncertain, setCreateUncertain] = useState(false);
  const [saving, setSaving] = useState(false);
  const savingRef = useRef(false);
  const [error, setError] = useState<AnnouncementMessage | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [conflict, setConflict] = useState<Conflict | null>(null);
  const [removeConfirmId, setRemoveConfirmId] = useState<string | null>(null);
  const [historyId, setHistoryId] = useState<string | null>(null);
  const [history, setHistory] = useState<AnnouncementRevision[] | null>(null);
  const [historyError, setHistoryError] = useState(false);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [older, setOlder] = useState<Announcement[]>([]);
  const [olderError, setOlderError] = useState(false);
  const [olderLoading, setOlderLoading] = useState(false);
  const [hasMoreOlder, setHasMoreOlder] = useState<boolean | null>(null);
  const [nextOlderOffset, setNextOlderOffset] = useState<number | null>(null);
  const mutationController = useRef<AbortController | null>(null);
  const conflictController = useRef<AbortController | null>(null);
  const historyController = useRef<AbortController | null>(null);
  const olderController = useRef<AbortController | null>(null);

  useEffect(() => () => {
    mutationController.current?.abort();
    conflictController.current?.abort();
    historyController.current?.abort();
    olderController.current?.abort();
    olderController.current = null;
  }, [sessionVersion, token, organizationId]);

  function reloadAnnouncements() {
    olderController.current?.abort();
    olderController.current = null;
    setOlder([]);
    setOlderError(false);
    setOlderLoading(false);
    setHasMoreOlder(null);
    setNextOlderOffset(null);
    announcements.reload();
  }

  function beginCreate() {
    if (saving || createAttempt) return;
    setCreating(true);
    setEditing(null);
    setForm(EMPTY_FORM);
    setError(null);
    setSuccess(null);
    setConflict(null);
  }

  function beginEdit(post: Announcement) {
    if (saving || post.state !== 'visible' || post.body === null) return;
    setCreating(false);
    setEditing({ id: post.id, version: post.version, state: post.state });
    setForm({ title: post.title, body: post.body, audience: post.audience });
    setCreateAttempt(null);
    setCreateUncertain(false);
    setError(null);
    setSuccess(null);
    setConflict(null);
  }

  function validateForm(): AnnouncementPayload | null {
    const title = form.title.trim();
    const body = form.body.trim();
    if (!title || title.length > 200) {
      setError({ key: 'Title is required and must be 200 characters or fewer.' });
      return null;
    }
    if (!body || body.length > 5000) {
      setError({ key: 'Body is required and must be 5000 characters or fewer.' });
      return null;
    }
    if (!form.audience) {
      setError({ key: 'Choose an audience before publishing.' });
      return null;
    }
    return { title, body, audience: form.audience };
  }

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (savingRef.current) return;
    setError(null);
    setSuccess(null);
    if (editing) {
      const payload = validateForm();
      if (!payload) return;
      await saveEdit(payload);
      return;
    }
    const payload = createUncertain && createAttempt
      ? { title: createAttempt.title, body: createAttempt.body, audience: createAttempt.audience }
      : validateForm();
    if (!payload) return;
    const attempt = { ...payload, client_key: createAttempt?.client_key ?? window.crypto.randomUUID() };
    setCreateAttempt(attempt);
    await create(attempt);
  }

  async function create(attempt: CreateAttempt) {
    if (savingRef.current) return;
    const controller = new AbortController();
    mutationController.current?.abort();
    mutationController.current = controller;
    savingRef.current = true;
    setSaving(true);
    setError(null);
    try {
      await api<Announcement>(`/organizations/${encodeURIComponent(organizationId)}/announcements`, {
        token,
        method: 'POST',
        body: attempt,
        signal: controller.signal,
      });
      if (controller.signal.aborted) return;
      setCreateAttempt(null);
      setCreateUncertain(false);
      setCreating(false);
      setForm(EMPTY_FORM);
      setSuccess('Announcement published.');
      reloadAnnouncements();
    } catch (caught) {
      if (controller.signal.aborted) return;
      setError(announcementApiMessage(caught, 'Create announcement'));
      setCreateUncertain(!(caught instanceof ApiError) || caught.status === 0 || caught.status === 408 || caught.status >= 500 || caught.status === 409);
    } finally {
      if (!controller.signal.aborted) setSaving(false);
      savingRef.current = false;
      if (mutationController.current === controller) mutationController.current = null;
    }
  }

  async function saveEdit(payload: AnnouncementPayload) {
    if (!editing || savingRef.current) return;
    const target = editing;
    const controller = new AbortController();
    mutationController.current?.abort();
    mutationController.current = controller;
    savingRef.current = true;
    setSaving(true);
    setError(null);
    try {
      await api<Announcement>(`/announcements/${encodeURIComponent(target.id)}`, {
        token,
        method: 'PATCH',
        body: payload,
        ifMatch: String(target.version),
        signal: controller.signal,
      });
      if (controller.signal.aborted) return;
      setEditing(null);
      setCreating(false);
      setForm(EMPTY_FORM);
      setConflict(null);
      setSuccess('Announcement updated.');
      reloadAnnouncements();
    } catch (caught) {
      if (controller.signal.aborted) return;
      if (caught instanceof ApiError && caught.status === 409) {
        setError(null);
        setConflict({ id: target.id, action: 'edit' });
      } else {
        setError(announcementApiMessage(caught, 'Save changes'));
      }
    } finally {
      if (!controller.signal.aborted) setSaving(false);
      savingRef.current = false;
      if (mutationController.current === controller) mutationController.current = null;
    }
  }

  async function remove(post: Announcement) {
    if (savingRef.current) return;
    const controller = new AbortController();
    mutationController.current?.abort();
    mutationController.current = controller;
    savingRef.current = true;
    setSaving(true);
    setError(null);
    try {
      await api<unknown>(`/announcements/${encodeURIComponent(post.id)}`, {
        token,
        method: 'DELETE',
        ifMatch: String(post.version),
        signal: controller.signal,
      });
      if (controller.signal.aborted) return;
      setRemoveConfirmId(null);
      if (editing?.id === post.id) {
        setEditing(null);
        setForm(EMPTY_FORM);
      }
      setConflict(null);
      setSuccess('Announcement removed.');
      reloadAnnouncements();
    } catch (caught) {
      if (controller.signal.aborted) return;
      if (caught instanceof ApiError && caught.status === 409) {
        setError(null);
        setConflict({ id: post.id, action: 'remove' });
      } else {
        setError(announcementApiMessage(caught, 'Remove announcement'));
      }
    } finally {
      if (!controller.signal.aborted) setSaving(false);
      savingRef.current = false;
      if (mutationController.current === controller) mutationController.current = null;
    }
  }

  async function reloadConflict() {
    if (!conflict || saving) return;
    const target = conflict;
    const controller = new AbortController();
    conflictController.current?.abort();
    conflictController.current = controller;
    savingRef.current = true;
    setSaving(true);
    setError(null);
    try {
      const latest = await findManagedAnnouncement(target.id, controller.signal);
      if (controller.signal.aborted) return;
      if (!latest) {
        setError({ key: 'The current announcement could not be reloaded. Your text is preserved.' });
        return;
      }
      if (target.action === 'edit' && editing?.id === target.id) {
        setEditing({ id: target.id, version: latest.version, state: latest.state });
      }
      setConflict({ ...target, latest });
      setError(null);
      reloadAnnouncements();
    } catch {
      if (controller.signal.aborted) return;
      setError({ key: 'The current announcement could not be reloaded. Your text is preserved.' });
    } finally {
      if (!controller.signal.aborted) setSaving(false);
      savingRef.current = false;
      if (conflictController.current === controller) conflictController.current = null;
    }
  }

  async function findManagedAnnouncement(id: string, signal: AbortSignal) {
    let offset = 0;
    while (true) {
      const page = await api<Announcement[]>(
        `/organizations/${encodeURIComponent(organizationId)}/announcements/manage?limit=${MANAGE_PAGE_SIZE}&offset=${offset}`,
        { token, signal },
      );
      const latest = page.find((post) => post.id === id);
      if (latest) return latest;
      if (page.length < MANAGE_PAGE_SIZE) return null;
      offset += page.length;
    }
  }

  async function loadOlderAnnouncements() {
    const firstPage = announcements.data;
    const hasMore = hasMoreOlder ?? (firstPage?.length === MANAGE_PAGE_SIZE);
    if (!hasMore || olderLoading || olderController.current || !firstPage) return;
    setOlderLoading(true);
    setOlderError(false);
    const offset = nextOlderOffset ?? firstPage.length;
    const controller = new AbortController();
    olderController.current = controller;
    try {
      const page = await api<Announcement[]>(
        `/organizations/${encodeURIComponent(organizationId)}/announcements/manage?limit=${MANAGE_PAGE_SIZE}&offset=${offset}`,
        { token, signal: controller.signal },
      );
      if (controller.signal.aborted) return;
      setOlder((current) => {
        const seen = new Set([...firstPage, ...current].map((post) => post.id));
        return [...current, ...page.filter((post) => {
          if (seen.has(post.id)) return false;
          seen.add(post.id);
          return true;
        })];
      });
      setNextOlderOffset(offset + page.length);
      setHasMoreOlder(page.length === MANAGE_PAGE_SIZE);
    } catch {
      if (!controller.signal.aborted) setOlderError(true);
    } finally {
      if (!controller.signal.aborted) setOlderLoading(false);
      if (olderController.current === controller) olderController.current = null;
    }
  }

  async function loadHistory(postId: string) {
    if (historyLoading) return;
    if (historyId === postId && history !== null) {
      setHistoryId(null);
      setHistory(null);
      setHistoryError(false);
      return;
    }
    setHistoryId(postId);
    setHistory(null);
    setHistoryError(false);
    setHistoryLoading(true);
    const controller = new AbortController();
    historyController.current?.abort();
    historyController.current = controller;
    try {
      const revisions = await api<AnnouncementRevision[]>(`/announcements/${encodeURIComponent(postId)}/history`, { token, signal: controller.signal });
      if (!controller.signal.aborted) setHistory(revisions);
    } catch {
      if (!controller.signal.aborted) setHistoryError(true);
    } finally {
      if (!controller.signal.aborted) setHistoryLoading(false);
      if (historyController.current === controller) historyController.current = null;
    }
  }

  if (!approved) {
    return <p className={`panel muted ${styles.desktopManager}`}>{text('This organization must be approved before announcements can be managed.')}</p>;
  }
  if (!canManage) {
    return <p className={`panel muted ${styles.desktopManager}`}>{text('You do not have organization management access for announcements.')}</p>;
  }

  const seenPostIds = new Set<string>();
  const posts = [...(announcements.data ?? []), ...older].filter((post) => {
    if (seenPostIds.has(post.id)) return false;
    seenPostIds.add(post.id);
    return true;
  });
  const hasMore = hasMoreOlder ?? (announcements.data?.length === MANAGE_PAGE_SIZE);
  const hasPendingCreate = createAttempt !== null;
  const showEditor = editing !== null || creating || hasPendingCreate ||
    (!announcements.loading && !announcements.error && posts.length === 0);

  return (
    <section className={`panel ${styles.desktopManager}`} aria-labelledby={`announcement-manager-${organizationId}`}>
      <header className={styles.sectionHeading}>
        <div>
          <h2 id={`announcement-manager-${organizationId}`}>{text('Announcement management')}</h2>
          <p className="muted">{text('Only organization owners and admins can publish and manage announcements.')}</p>
        </div>
        {!showEditor && !hasPendingCreate && (
          <button type="button" className="button button-secondary" onClick={beginCreate}>
            {text('Create announcement')}
          </button>
        )}
      </header>

      {error && <p className="panel error" role="alert">{text(error.key, error.values)}</p>}
      {success && <p className="panel success" role="status">{text(success)}</p>}
      {conflict && (
        <div className={styles.conflict} role="alert">
          <p>{text('The announcement changed since you loaded it. Your edits are still here. Reload the latest version to continue.')}</p>
          {conflict.latest ? (
            conflict.action === 'remove' && conflict.latest.state !== 'removed' ? (
              <button type="button" className="button button-danger" onClick={() => void remove(conflict.latest!)} disabled={saving}>
                {text('Confirm removal')}
              </button>
            ) : conflict.action === 'edit' && conflict.latest.state === 'visible' ? (
              <p className="muted">{text('Latest version loaded. Your edit fields were preserved; save again when ready.')}</p>
            ) : (
              <p className="muted">{text(conflict.latest.state === 'removed' ? 'This announcement has been removed.' : 'This announcement is hidden and cannot be edited.')}</p>
            )
          ) : (
            <button type="button" className="button button-secondary" onClick={() => void reloadConflict()} disabled={saving}>
              {saving ? text('Saving…') : text('Reload latest version and keep my edits')}
            </button>
          )}
        </div>
      )}

      {showEditor && (
        <form className={styles.editor} onSubmit={(event) => void save(event)}>
          <h3>{text(editing ? 'Edit announcement' : 'Create announcement')}</h3>
          <label className="field">
            <span>{text('Title')}</span>
            <input
              value={form.title}
              maxLength={200}
              onChange={(event) => setForm((current) => ({ ...current, title: event.target.value }))}
              disabled={saving || createUncertain || (editing !== null && editing.state !== 'visible')}
              required
            />
          </label>
          <label className="field">
            <span>{text('Body')}</span>
            <textarea
              value={form.body}
              maxLength={5000}
              onChange={(event) => setForm((current) => ({ ...current, body: event.target.value }))}
              disabled={saving || createUncertain || (editing !== null && editing.state !== 'visible')}
              required
            />
          </label>
          <label className="field">
            <span>{text('Audience')}</span>
            <select
              value={form.audience}
              onChange={(event) => setForm((current) => ({ ...current, audience: event.target.value as AudienceChoice }))}
              disabled={saving || createUncertain || (editing !== null && editing.state !== 'visible')}
              required
            >
              <option value="">{text('Choose who can read this announcement')}</option>
              <option value="public">{text('Public')}</option>
              <option value="members">{text('Members only')}</option>
            </select>
          </label>
          <div className={styles.editorActions}>
            <button type="submit" className="button" disabled={saving || (editing !== null && editing.state !== 'visible')}>
              {saving ? text('Saving…') : createUncertain ? text('Retry same announcement') : text(editing ? 'Save changes' : 'Create')}
            </button>
            {(editing || creating) && !saving && !hasPendingCreate && (
              <button type="button" className="button button-secondary" onClick={() => {
                setEditing(null);
                setCreating(false);
                setForm(EMPTY_FORM);
                setError(null);
              }}>{text('Cancel editor')}</button>
            )}
          </div>
          {createUncertain && <p className="muted">{text('The create result is uncertain. Retrying sends the same content with the same request key.')}</p>}
          {editing && editing.state !== 'visible' && (
            <p className="muted">{text(editing.state === 'removed' ? 'This announcement has been removed.' : 'This announcement is hidden and cannot be edited.')}</p>
          )}
        </form>
      )}

      <div className={styles.managedList}>
        {announcements.loading && announcements.data === null ? (
          <p className="muted" role="status">{text('Loading announcements…')}</p>
        ) : announcements.error ? (
          <div className="panel error" role="alert">
            <p>{text('The announcement list could not be refreshed.')}</p>
            <button type="button" className="button button-secondary" onClick={reloadAnnouncements}>{text('Reload announcement list')}</button>
          </div>
        ) : posts.length === 0 ? (
          <p className="empty-state muted">{text('No announcements are available for management.')}</p>
        ) : posts.map((post) => (
          <article className={styles.managedPost} key={post.id}>
            <header className={styles.postHeading}>
              <div>
                <h3>{post.title}</h3>
                <div className={styles.postMeta}>
                  <span className={styles.audience} data-audience={post.audience}>{text(post.audience === 'public' ? 'Public' : 'Members only')}</span>
                  <span className={styles.stateBadge}>{text(post.state === 'visible' ? 'Visible' : post.state === 'hidden' ? 'Hidden' : 'Removed')}</span>
                  <span>{text('Version {version}', { version: post.version })}</span>
                  <time dateTime={post.updated_at}>{formatDate(post.updated_at, language)} · {formatTime(post.updated_at, language)}</time>
                  {post.edited_at && <span className={styles.edited}>{text('Edited')}</span>}
                </div>
              </div>
            </header>
            {post.body && <p className={styles.postBody}>{post.body}</p>}
            <div className={styles.editorActions}>
              {post.state === 'visible' && post.body !== null && (
                <button type="button" className="button button-secondary" onClick={() => beginEdit(post)} disabled={saving || hasPendingCreate}>
                  {text('Edit announcement')}
                </button>
              )}
              {post.state !== 'removed' && (
                removeConfirmId === post.id ? (
                  <div className={styles.removeConfirm} role="group" aria-label={text('Remove announcement')}>
                    <p>{text('Remove this announcement? Readers will no longer be able to open it. Its report and revision records remain available to authorized reviewers.')}</p>
                    <button type="button" className="button button-danger" onClick={() => void remove(post)} disabled={saving}>{text('Confirm removal')}</button>
                    <button type="button" className="button button-secondary" onClick={() => setRemoveConfirmId(null)} disabled={saving}>{text('Keep announcement')}</button>
                  </div>
                ) : (
                  <button type="button" className="button button-secondary" onClick={() => setRemoveConfirmId(post.id)} disabled={saving || hasPendingCreate}>
                    {text('Remove announcement')}
                  </button>
                )
              )}
              <button type="button" className="text-action" onClick={() => void loadHistory(post.id)} disabled={historyLoading}>
                {historyId === post.id ? text('Hide history') : text('View history')}
              </button>
            </div>

            {conflict?.id === post.id && conflict.action === 'remove' && conflict.latest && conflict.latest.state !== 'removed' && (
              <p className="muted">{text('Reload the current announcement before trying again.')}</p>
            )}
            {historyId === post.id && (
              <section className={styles.history} aria-label={text('Announcement history')}>
                <h4>{text('Announcement history')}</h4>
                {historyLoading ? (
                  <p className="muted" role="status">{text('Loading announcement history…')}</p>
                ) : historyError ? (
                  <div className={styles.inlineError} role="alert">
                    <p>{text('The announcement history could not be loaded.')}</p>
                    <button type="button" className="text-action" onClick={() => void loadHistory(post.id)}>{text('Retry loading history')}</button>
                  </div>
                ) : history?.length ? (
                  <ol className={styles.revisionList}>
                    {history.map((revision) => (
                      <li key={revision.id}>
                        <strong>{text('Version {version} · {action} · {date}', {
                          version: revision.version,
                          action: text(revision.action[0].toUpperCase() + revision.action.slice(1)),
                          date: `${formatDate(revision.created_at, language)} · ${formatTime(revision.created_at, language)}`,
                        })}</strong>
                        <span>{text('Actor ID: {id}', { id: revision.actor_id })}</span>
                        <h5>{revision.title}</h5>
                        <p>{revision.body ?? text('No body after removal.')}</p>
                        <span className={styles.audience}>{text(revision.audience === 'public' ? 'Public' : 'Members only')}</span>
                      </li>
                    ))}
                  </ol>
                ) : (
                  <p className="muted">{text('No revisions are available.')}</p>
                )}
              </section>
            )}
          </article>
        ))}
      </div>
      {olderError && (
        <div className="panel error" role="alert">
          <p>{text('The announcement list could not be refreshed.')}</p>
          <button type="button" className="button button-secondary" onClick={() => void loadOlderAnnouncements()} disabled={olderLoading}>
            {text('Retry loading older announcements')}
          </button>
        </div>
      )}
      {hasMore && !announcements.error && (
        <button type="button" className="button button-secondary" onClick={() => void loadOlderAnnouncements()} disabled={olderLoading}>
          {olderLoading ? text('Loading older announcements…') : text('Load older announcements')}
        </button>
      )}
    </section>
  );
}
