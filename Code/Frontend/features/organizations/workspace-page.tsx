'use client';

import Link from 'next/link';
import { useSearchParams } from 'next/navigation';
import { useEffect, useState, type FormEvent } from 'react';
import { api } from '@/lib/api';
import { formatDate, formatTime } from '@/lib/date';
import { useT } from '@/lib/i18n';
import { usePreferences } from '@/lib/preferences';
import { useSession } from '@/lib/session';
import { useApiResource } from '@/lib/use-api-resource';
import type { MyOrganizations, Organization, PrivateEvent, ReviewEvent, Workspace } from '@/lib/types';
import { DecisionHistory, StatusBadge } from './shared';
import styles from './workspace-page.module.css';
import { FeaturedRequestControl } from '@/features/featured/FeaturedControls';
import { FeaturedBadge } from '@/features/featured/FeaturedBadge';
import { Feedback } from '@/components/feedback';
import { EventChanges } from './EventChanges';
import { RegistrationReview } from './RegistrationReview';
import { ModerationReportQueue } from '@/features/moderation/report-queue';
import { StaffMembership } from '@/features/memberships/StaffMembership';
import { AnnouncementManager } from '@/features/announcements/AnnouncementManager';
import { MediaUploader } from '@/features/media/MediaUploader';
import { MediaImage } from '@/features/media/MediaImage';
import { OwnershipTransferPanel } from '@/features/ownership/OwnershipTransferPanel';
import { AttendancePanel } from '@/features/attendance/AttendancePanel';
import { EventSafetyControls, EventSafetyQueue, OrganizationSuspensionPanel } from '@/features/eventsafety';

function draftHref(orgId: string, eventId?: string) {
  const params = new URLSearchParams({orgId});
  if (eventId) params.set('eventId', eventId);
  return `/draft?${params.toString()}`;
}

function eventHref(eventId: string) {
  return `/events?${new URLSearchParams({eventId}).toString()}`;
}

function useCurrentTime() {
  const [currentTime, setCurrentTime] = useState<number | null>(null);
  useEffect(() => {
    const update = () => setCurrentTime(Date.now());
    const initialUpdate = window.setTimeout(update, 0);
    const interval = window.setInterval(update, 60_000);
    return () => {
      window.clearTimeout(initialUpdate);
      window.clearInterval(interval);
    };
  }, []);
  return currentTime;
}

function deadlineIsOverdue(deadline: string | null, now: number | null) {
  return deadline !== null && now !== null && Date.parse(deadline) < now;
}

function deadlineIsDueSoon(deadline: string | null, now: number | null) {
  const timestamp = deadline === null ? Number.NaN : Date.parse(deadline);
  return now !== null && timestamp >= now && timestamp <= now + 24 * 60 * 60 * 1000;
}

function deadlineTone(deadline: string | null, now: number | null) {
  if (!deadline) return '';
  if (deadlineIsOverdue(deadline, now)) return styles.deadlineOverdue;
  if (deadlineIsDueSoon(deadline, now)) return styles.deadlineSoon;
  return '';
}

function OrganizationApplicationForm({token, onCreated}: {
  token: string;
  onCreated: () => void;
}) {
  const t = useT();
  const {preferences: {language}} = usePreferences();
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [created, setCreated] = useState<Organization | null>(null);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (submitting) return;

    const trimmedName = name.trim();
    if (!trimmedName) {
      setError(t('Enter an organization name.'));
      return;
    }

    setSubmitting(true);
    setError(null);
    setCreated(null);
    try {
      const result = await api<Organization>('/organizations', {
        token,
        method: 'POST',
        body: {name: trimmedName, description},
      });
      setCreated(result);
      setName('');
      setDescription('');
      onCreated();
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : t('The application could not be submitted.'));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <section className="panel" id="organization-application" aria-labelledby="organization-application-title">
      <h2 id="organization-application-title">{t('Apply for an organization workspace')}</h2>
      <p className="muted">
        {t('Submit the organization name and optionally add a short description. Accreditation is assessed offline by a platform admin; no evidence upload is part of this flow.')}
      </p>
      <form onSubmit={submit}>
        <div className="field">
            <label htmlFor="organization-name">{t('Organization name')}</label>
          <input
            id="organization-name"
            name="name"
            value={name}
            onChange={event => setName(event.target.value)}
            maxLength={200}
            required
            autoComplete="organization"
          />
        </div>
        <div className="field">
            <label htmlFor="organization-description">{t('Description')} <span className="muted">({t('optional')})</span></label>
          <textarea
            id="organization-description"
            name="description"
            value={description}
            onChange={event => setDescription(event.target.value)}
          />
        </div>
        <div className="actions">
          <button className="button" type="submit" disabled={submitting}>
            {submitting ? t('Submitting…') : t('Submit organization')}
          </button>
        </div>
      </form>
      {error && <p className="panel error" role="alert">{error}</p>}
      {created && (
        <div className="panel" role="status">
          <p><strong>{created.name}</strong> {t('was created with status')} <StatusBadge status={created.accreditation_status} />.</p>
          <p className="muted">{t('Submitted')} {formatDate(created.created_at, language)} · {formatTime(created.created_at, language)} ({t('Manila time')}).</p>
          <div className="actions">
            <Link className="button button-secondary" href={`/workspace?orgId=${encodeURIComponent(created.id)}`}>
              {t('Open workspace')}
            </Link>
            {created.accreditation_status === 'pending' && (
              <Link className="button" href={draftHref(created.id)}>{t('Start a private draft')}</Link>
            )}
          </div>
        </div>
      )}
    </section>
  );
}

function OrganizationEvents({workspace, events, loading, error, onRetry, token, selectedEventId}: {
  workspace: Workspace;
  events: PrivateEvent[] | null;
  loading: boolean;
  error: Error | null;
  onRetry: () => void;
  token: string;
  selectedEventId: string | null;
}) {
  const t = useT();
  const {preferences: {language}, resolvedReducedMotion} = usePreferences();
  const currentTime = useCurrentTime();
  const isManager = workspace.role === 'owner' || workspace.role === 'admin';
  const canLoadReviewSummary = isManager && workspace.accreditation_status === 'approved';
  const reviewSummaries = useApiResource<ReviewEvent[]>(
    canLoadReviewSummary ? `/organizations/${encodeURIComponent(workspace.id)}/review-events` : null,
    token,
  );
  const [changedWorkspaceId, setChangedWorkspaceId] = useState<string | null>(null);
  const [activePanel, setActivePanel] = useState<string | null>(() =>
    selectedEventId ? `review:${selectedEventId}` : null,
  );
  const [filter, setFilter] = useState<'all' | 'draft' | 'published' | 'other'>('all');
  const [query, setQuery] = useState('');
  const canOpenEditor = isManager &&
    (workspace.accreditation_status === 'approved' || workspace.accreditation_status === 'pending');
  const availableEvents = events ?? [];
  const summaryById = new Map((reviewSummaries.data ?? []).map(summary => [summary.id, summary]));
  const reviewOrder = new Map((reviewSummaries.data ?? []).map((summary, index) => [summary.id, index]));
  const orderedEvents = [...availableEvents].sort((left, right) => {
    const statusRank = (status: string) => status === 'published' ? 0 : status === 'draft' ? 1 : 2;
    const rankDifference = statusRank(left.status) - statusRank(right.status);
    if (rankDifference) return rankDifference;
    if (left.status === 'published' && right.status === 'published') {
      const leftIndex = reviewOrder.get(left.id);
      const rightIndex = reviewOrder.get(right.id);
      if (leftIndex !== undefined && rightIndex !== undefined && leftIndex !== rightIndex) return leftIndex - rightIndex;
    }
    const leftStart = left.starts_at ? Date.parse(left.starts_at) : Number.POSITIVE_INFINITY;
    const rightStart = right.starts_at ? Date.parse(right.starts_at) : Number.POSITIVE_INFINITY;
    return leftStart - rightStart || left.id.localeCompare(right.id);
  });
  const eventFilters = [
    {key: 'all', label: t('All events'), count: availableEvents.length},
    {key: 'draft', label: t('Drafts'), count: availableEvents.filter(event => event.status === 'draft').length},
    {key: 'published', label: t('Published'), count: availableEvents.filter(event => event.status === 'published').length},
    {key: 'other', label: t('Other status'), count: availableEvents.filter(event => event.status !== 'draft' && event.status !== 'published').length},
  ] as const;
  const search = query.trim().toLocaleLowerCase();
  const visibleEvents = orderedEvents.filter(event => {
    const statusMatches = filter === 'all' || event.status === filter ||
      (filter === 'other' && event.status !== 'draft' && event.status !== 'published');
    const textMatches = !search || `${event.title ?? ''} ${event.summary ?? ''}`.toLocaleLowerCase().includes(search);
    return statusMatches && textMatches;
  });

  useEffect(() => {
    if (!selectedEventId || !events?.some(event => event.id === selectedEventId)) return;
    const frame = window.requestAnimationFrame(() => {
      document.getElementById(`workspace-event-${selectedEventId}`)?.scrollIntoView({behavior: resolvedReducedMotion ? 'auto' : 'smooth', block: 'center'});
    });
    return () => window.cancelAnimationFrame(frame);
  }, [workspace.id, selectedEventId, events, resolvedReducedMotion]);

  return (
    <section className={`panel ${styles.eventsPanel}`} aria-labelledby="organization-events-title">
      <header className={styles.eventsHeader}>
        <div>
          <p className={styles.eyebrow}>{t('Organization workspace')}</p>
          <h2 id="organization-events-title">{t('Organization events')}</h2>
          <p className="muted">{t('Search the event list or filter it by status. Drafts stay private until an authorized owner or admin publishes them.')}</p>
        </div>
        {canOpenEditor && (
          <Link className="button" href={draftHref(workspace.id)}>
            {workspace.accreditation_status === 'approved' ? t('Create event draft') : t('Create private draft')}
          </Link>
        )}
      </header>
      {changedWorkspaceId === workspace.id && <p className={styles.changeNotice} role="status">{t('Material changes submitted. Review the updated event and reconfirmation requests.')}</p>}
      {canLoadReviewSummary && reviewSummaries.error && (
        <p className={`panel error ${styles.summaryError}`} role="alert">
          {t('Registration counts and deadlines could not be loaded. Refresh the review summary before relying on its totals.')}
        </p>
      )}
      <Feedback loading={loading} error={error} onRetry={onRetry}>
        {!availableEvents.length ? (
          <p className="empty-state muted">{t('No events are available for this workspace yet.')}</p>
        ) : (
          <div className={styles.eventCollection}>
            <div className={styles.eventControls}>
              <label className={styles.searchField} htmlFor="workspace-event-search">
                {t('Search events')}
                <input
                  id="workspace-event-search"
                  type="search"
                  value={query}
                  onChange={event => setQuery(event.target.value)}
                  placeholder={t('Search by title or summary')}
                />
              </label>
              <div className={styles.filterGroup} role="group" aria-label={t('Filter organization events')}>
                {eventFilters.map(item => (
                  <button
                    className={styles.filterButton}
                    type="button"
                    key={item.key}
                    aria-pressed={filter === item.key}
                    onClick={() => setFilter(item.key)}
                  >
                    <span>{item.label}</span><span className={styles.filterCount}>{item.count}</span>
                  </button>
                ))}
              </div>
              <p className={styles.resultCount} role="status">{t('{count} events shown', {count: visibleEvents.length})}</p>
            </div>
            {!visibleEvents.length ? (
              <p className={styles.emptyEvents}>{t('No events match these filters.')}</p>
            ) : (
              <div className={styles.eventList}>
                {visibleEvents.map(event => (
              <article className={`event-card ${styles.eventCard} ${selectedEventId === event.id ? styles.targetEvent : ''}`} id={`workspace-event-${event.id}`} key={event.id}>
                <header className={styles.eventHeader}>
                  <div className={styles.eventTitle}>
                    <span className={styles.eventKind}>{event.status === 'draft' ? t('Private draft') : t('Organization event')}</span>
                    <h3>{event.title || t('Untitled draft')}</h3>
                    {event.is_featured && <FeaturedBadge />}
                  </div>
                  <StatusBadge status={event.status} />
                </header>
                <p className="event-summary">{event.summary || t('No summary has been added yet.')}</p>
                {event.starts_at && (
                  <p className={`muted ${styles.eventDate}`}>
                    <span>{t('Starts')}</span>
                    <time dateTime={event.starts_at}>
                      {formatDate(event.starts_at, language)} · {formatTime(event.starts_at, language)} ({t('Manila time')})
                    </time>
                  </p>
                )}
                {canLoadReviewSummary && (
                  <div className={styles.reviewSummary} aria-label={t('Registration review summary')}>
                    {reviewSummaries.loading ? (
                      <span className="muted">{t('Loading review counts and deadlines…')}</span>
                    ) : summaryById.has(event.id) ? (
                      <>
                        <span className={styles.summaryMetric}>
                          {t('{count} pending registration reviews', {count: summaryById.get(event.id)!.pending_registration_count})}
                        </span>
                        {summaryById.get(event.id)!.next_review_deadline && (
                          <span className={`${styles.deadline} ${deadlineTone(summaryById.get(event.id)!.next_review_deadline, currentTime)}`}>
                            <span className={styles.deadlineLabel}>{t('Next review deadline')}</span>
                            <time dateTime={summaryById.get(event.id)!.next_review_deadline!}>
                              {formatDate(summaryById.get(event.id)!.next_review_deadline!, language)} · {formatTime(summaryById.get(event.id)!.next_review_deadline!, language)} ({t('Manila time')})
                            </time>
                            {deadlineIsOverdue(summaryById.get(event.id)!.next_review_deadline, currentTime) && <span>{t('Overdue')}</span>}
                            {deadlineIsDueSoon(summaryById.get(event.id)!.next_review_deadline, currentTime) && <span>{t('Due within 24 hours')}</span>}
                          </span>
                        )}
                        {summaryById.get(event.id)!.pending_registration_count === 0 && !summaryById.get(event.id)!.next_review_deadline && (
                          <span className="muted">{t('No pending registration reviews.')}</span>
                        )}
                      </>
                    ) : (
                      <span className="muted">{t('No pending registration reviews.')}</span>
                    )}
                  </div>
                )}
                <div className="actions">
                  {canOpenEditor && event.status === 'draft' && (
                    <Link className="button button-secondary" href={draftHref(workspace.id, event.id)}>
                      {t('Open private draft')}
                    </Link>
                  )}
                  {isManager && workspace.accreditation_status === 'approved' && event.status === 'published' && (
                    <>
                      <Link className="button button-secondary" href={draftHref(workspace.id, event.id)}>
                        {t('Manage event')}
                      </Link>
                      <Link href={eventHref(event.id)}>{t('View published event')}</Link>
                    </>
                  )}
                </div>
                {event.status === 'published' && workspace.accreditation_status === 'approved' && <AttendancePanel key={`attendance:${token}:${event.id}`} eventId={event.id} token={token} />}
                {event.status === 'published' && workspace.accreditation_status === 'approved' && <EventSafetyControls key={`safety:${token}:${event.id}`} eventId={event.id} token={token} />}
                {event.status === 'published' && isManager && (
                  <div className={styles.eventTools}>
                    <RegistrationReview
                      eventId={event.id}
                      eventEndsAt={event.ends_at}
                      isOpen={activePanel === `review:${event.id}`}
                      onOpenChange={open => setActivePanel(open ? `review:${event.id}` : null)}
                      onReviewed={reviewSummaries.reload}
                    />
                    {isManager && workspace.accreditation_status === 'approved' && (
                      <FeaturedRequestControl key={`featured:${event.id}:${event.material_revision}`} eventId={event.id} eventStartsAt={event.starts_at} orgId={workspace.id} token={token} />
                    )}
                    {isManager && workspace.accreditation_status === 'approved' && (
                      <EventChanges
                        key={`${event.id}:${event.material_revision}`}
                        event={event}
                        isOpen={activePanel === `change:${event.id}`}
                        onOpenChange={open => setActivePanel(open ? `change:${event.id}` : null)}
                        onChanged={() => {
                          setChangedWorkspaceId(workspace.id);
                          onRetry();
                          reviewSummaries.reload();
                        }}
                      />
                    )}
                  </div>
                )}
                </article>
                ))}
              </div>
            )}
          </div>
        )}
      </Feedback>
    </section>
  );
}

function ModeratorReviews({grant, token, selectedEventId}: {
  grant: MyOrganizations['grants'][number];
  token: string;
  selectedEventId: string | null;
}) {
  const t = useT();
  const {preferences: {language}, resolvedReducedMotion} = usePreferences();
  const currentTime = useCurrentTime();
  const eventsPath = grant.accreditation_status === 'approved'
    ? `/organizations/${encodeURIComponent(grant.org_id)}/review-events`
    : null;
  const events = useApiResource<ReviewEvent[]>(eventsPath, token);
  const organizationEvents = events.data ?? [];
  const [activeReviewEventId, setActiveReviewEventId] = useState<string | null>(() => selectedEventId);
  const [reviewFeedback, setReviewFeedback] = useState<{message: string; error: boolean} | null>(null);
  const [query, setQuery] = useState('');
  const search = query.trim().toLocaleLowerCase();
  const visibleEvents = organizationEvents.filter(event => !search ||
    `${event.title ?? ''} ${event.summary ?? ''}`.toLocaleLowerCase().includes(search));

  useEffect(() => {
    if (!selectedEventId || !events.data?.some(event => event.id === selectedEventId)) return;
    const frame = window.requestAnimationFrame(() => {
      document.getElementById(`workspace-event-${selectedEventId}`)?.scrollIntoView({behavior: resolvedReducedMotion ? 'auto' : 'smooth', block: 'center'});
    });
    return () => window.cancelAnimationFrame(frame);
  }, [grant.org_id, selectedEventId, events.data, resolvedReducedMotion]);

  return (
    <div className={styles.workspaceDetails}>
      <section className={`panel ${styles.rolePanel}`}>
        <div className={styles.organizationHeading}>
          <div>
            <p className={styles.eyebrow}>{t('Moderator workspace')}</p>
            <h2>{grant.org_name}</h2>
          </div>
          <span className={styles.roleBadge}>{t('Moderator')}</span>
        </div>
        <p className="muted">{t('Moderators may review registration decisions for this organization. The assigned reviewer is accountable for each deadline; other authorized reviewers may decide at the initial or extended stage, while escalation excludes the first reviewer. Event editing and capacity changes remain with the owner and admins.')}</p>
      </section>
      {grant.accreditation_status === 'approved' && <StaffMembership orgId={grant.org_id} role={grant.role} />}
      <ModerationReportQueue key={`${token}:${grant.org_id}`} token={token} orgId={grant.org_id} />
      {grant.accreditation_status === 'approved' && <>
        <EventSafetyQueue key={`safety:${token}:${grant.org_id}`} token={token} orgId={grant.org_id} />
        <OrganizationSuspensionPanel key={`suspension:${token}:${grant.org_id}`} token={token} orgId={grant.org_id} />
      </>}
      <section className={`panel ${styles.eventsPanel}`} aria-label={t('Published events for registration review')}>
        <header className={styles.eventsHeader}>
          <div>
            <p className={styles.eyebrow}>{t('Registration review')}</p>
            <h2>{t('Published events')}</h2>
          </div>
        </header>
        {grant.accreditation_status === 'approved' && (
          <label className={styles.searchField} htmlFor="moderator-event-search">
            {t('Search published events')}
            <input id="moderator-event-search" type="search" value={query} onChange={event => setQuery(event.target.value)} placeholder={t('Search by title or summary')} />
          </label>
        )}
        {reviewFeedback && <p className={reviewFeedback.error ? 'panel error' : 'panel success'} role={reviewFeedback.error ? 'alert' : 'status'}>{t(reviewFeedback.message)}</p>}
        <Feedback loading={events.loading} error={events.error} onRetry={events.reload}>
          {grant.accreditation_status !== 'approved' ? (
            <p className="empty-state muted">{t('Registration review is available after this organization is approved.')}</p>
          ) : !organizationEvents.length ? (
            <p className="empty-state muted">{t('No published events are available for review.')}</p>
          ) : !visibleEvents.length ? (
            <p className="empty-state muted">{t('No events match these filters.')}</p>
          ) : (
            <div className={styles.eventList}>
              {visibleEvents.map(event => (
                <article className={`event-card ${styles.eventCard} ${selectedEventId === event.id ? styles.targetEvent : ''}`} id={`workspace-event-${event.id}`} key={event.id}>
                  <header className={styles.eventHeader}>
                    <h3>{event.title}</h3>
                    {event.starts_at && (
                      <p className={`muted ${styles.eventDate}`}><span>{t('Starts')}</span>{formatDate(event.starts_at, language)} · {formatTime(event.starts_at, language)} ({t('Manila time')})</p>
                    )}
                  </header>
                  <div className={styles.reviewSummary} aria-label={t('Registration review summary')}>
                    <span className={styles.summaryMetric}>
                      {t('{count} pending registration reviews', {count: event.pending_registration_count})}
                    </span>
                    {event.next_review_deadline ? (
                      <span className={`${styles.deadline} ${deadlineTone(event.next_review_deadline, currentTime)}`}>
                        <span className={styles.deadlineLabel}>{t('Next review deadline')}</span>
                        <time dateTime={event.next_review_deadline}>
                          {formatDate(event.next_review_deadline, language)} · {formatTime(event.next_review_deadline, language)} ({t('Manila time')})
                        </time>
                        {deadlineIsOverdue(event.next_review_deadline, currentTime) && <span>{t('Overdue')}</span>}
                        {deadlineIsDueSoon(event.next_review_deadline, currentTime) && <span>{t('Due within 24 hours')}</span>}
                      </span>
                    ) : <span className="muted">{t('No pending registration reviews.')}</span>}
                  </div>
                  <RegistrationReview
                    eventId={event.id}
                    eventEndsAt={event.ends_at}
                    isOpen={activeReviewEventId === event.id}
                    onOpenChange={open => setActiveReviewEventId(open ? event.id : null)}
                    onReviewed={feedback => { setReviewFeedback(feedback); events.reload(); }}
                  />
                  <AttendancePanel key={`attendance:${token}:${event.id}`} eventId={event.id} token={token} />
                  <EventSafetyControls key={`safety:${token}:${event.id}`} eventId={event.id} token={token} />
                </article>
              ))}
            </div>
          )}
        </Feedback>
      </section>
    </div>
  );
}

function WorkspaceDetails({token, sessionVersion, workspace, events, eventsLoading, eventsError, reloadEvents, reloadWorkspace, selectedEventId, onOwnershipChanged}: {
  token: string;
  sessionVersion: number;
  workspace: Workspace;
  events: PrivateEvent[] | null;
  eventsLoading: boolean;
  eventsError: Error | null;
  reloadEvents: () => void;
  reloadWorkspace: () => void;
  selectedEventId: string | null;
  onOwnershipChanged: () => Promise<void>;
}) {
  const t = useT();
  return (
    <div className={styles.workspaceDetails}>
      <section className={`panel ${styles.organizationCard}`} aria-labelledby="workspace-detail-title">
        <div className={styles.organizationHeading}>
          {workspace.logo_url && <MediaImage mediaUrl={workspace.logo_url} token={token} alt="" className={styles.logoPreview} />}
          <div>
            <p className={styles.eyebrow}>{t('Organization workspace')}</p>
            <h2 id="workspace-detail-title">{workspace.name}</h2>
          </div>
          <StatusBadge status={workspace.accreditation_status} />
        </div>
        <p>{workspace.description || t('No organization description was provided.')}</p>
        <p className={styles.contextLine}>{t('Workspace role: {role}', {role: t(workspace.role)})}</p>
        <DecisionHistory decisions={workspace.decisions} />
        {workspace.accreditation_status !== 'rejected' && (
          <div className="stack">
            <h3>{t('Club logo')}</h3>
            <MediaUploader key={`${token}:${workspace.id}`} endpoint={`/organizations/${encodeURIComponent(workspace.id)}/logo`}
              token={token} currentUrl={workspace.logo_url} onChanged={reloadWorkspace} />
          </div>
        )}
      </section>
      <OrganizationEvents
        key={`${workspace.id}:${selectedEventId ?? ''}`}
        workspace={workspace}
        events={events}
        loading={eventsLoading}
        error={eventsError}
        onRetry={reloadEvents}
        token={token}
        selectedEventId={selectedEventId}
      />
      {workspace.accreditation_status === 'approved' && (
        <AnnouncementManager
          key={`${sessionVersion}:${token}:${workspace.id}`}
          organizationId={workspace.id}
          token={token}
          sessionVersion={sessionVersion}
          role={workspace.role}
          approved
        />
      )}
      <ModerationReportQueue key={`${workspace.id}`} token={token} orgId={workspace.id} />
      {workspace.accreditation_status === 'approved' && <>
        <EventSafetyQueue key={`safety:${token}:${workspace.id}`} token={token} orgId={workspace.id} />
        <OrganizationSuspensionPanel key={`suspension:${token}:${workspace.id}`} token={token} orgId={workspace.id} />
      </>}
      {workspace.accreditation_status === 'approved' && <StaffMembership orgId={workspace.id} role={workspace.role} />}
      {workspace.accreditation_status === 'approved' && (
        <OwnershipTransferPanel key={`${token}:${workspace.id}`} orgId={workspace.id}
          role={workspace.role} onChanged={onOwnershipChanged} />
      )}
    </div>
  );
}

function OrganizationWorkspaceContent() {
  const t = useT();
  const searchParams = useSearchParams();
  const selectedOrgId = searchParams.get('orgId');
  const selectedEventId = searchParams.get('eventId');
  const {token, authLoading, error: sessionError, version, refreshActor} = useSession();
  const organizations = useApiResource<MyOrganizations>(token ? '/me/organizations' : null, token);
  const ownedWorkspaces = organizations.data?.owned_workspaces ?? [];
  const grants = organizations.data?.grants ?? [];
  const otherGrants = grants.filter(grant => !ownedWorkspaces.some(workspace => workspace.id === grant.org_id));
  const moderatorGrants = otherGrants.filter(grant => grant.role === 'moderator');
  const memberGrants = otherGrants.filter(grant => grant.role === 'member');
  const selectedModerator = grants.find(grant => grant.org_id === selectedOrgId && grant.role === 'moderator') ?? null;
  const canAccessSelectedWorkspace = ownedWorkspaces.some(workspace => workspace.id === selectedOrgId);
  const workspacePath = token && selectedOrgId && canAccessSelectedWorkspace
    ? `/organizations/${encodeURIComponent(selectedOrgId)}/workspace`
    : null;
  const workspace = useApiResource<Workspace>(workspacePath, token);
  const eventsPath = token && selectedOrgId && canAccessSelectedWorkspace && workspace.data
    ? `/organizations/${encodeURIComponent(selectedOrgId)}/events`
    : null;
  const events = useApiResource<PrivateEvent[]>(eventsPath, token);

  if (authLoading) return <Feedback loading />;
  if (!token) {
    return <section className="panel" role={sessionError ? 'alert' : undefined}>
      {sessionError?.message || t('Sign in using the site header to open organization workspaces.')}
    </section>;
  }

  return (
    <>
      <p className={`panel desktop-required ${styles.mobileNote}`} role="note">
        {t('Organization management is available on desktop. Open this page on a wider screen to apply or manage a workspace.')}
      </p>
      <div className={`management-desktop ${styles.desktopOnly}`}>
        <header className={`page-heading ${styles.pageHeading}`}>
          <div>
            <p className={styles.eyebrow}>{t('Organization management')}</p>
            <h1>{t('Workspace')}</h1>
            <p className="muted">{t('Applications, access, decisions, and event links for organizations connected to your account.')}</p>
          </div>
          <span className={styles.contextBadge}>{t('Organizations: {count}', {count: ownedWorkspaces.length + otherGrants.length})}</span>
        </header>

        <div className={`management-layout ${styles.layout}`}>
          <aside className={`stack ${styles.sidebar}`} aria-label={t('Organization workspace navigation')}>
            <section className={`panel ${styles.sidebarCard}`} aria-labelledby="my-workspaces-title">
              <div className={styles.sidebarHeading}>
                <h2 id="my-workspaces-title">{t('Management workspaces')}</h2>
                <span className={styles.sidebarCount}>{ownedWorkspaces.length}</span>
              </div>
              <Link className="text-action" href="/workspace">{t('Apply for a workspace')}</Link>
              <Feedback loading={organizations.loading} error={organizations.error} onRetry={organizations.reload}>
                {!ownedWorkspaces.length ? (
                  <p className={styles.sidebarEmpty}>{t('No owner or admin workspaces are available for this account.')}</p>
                ) : (
                  <nav aria-label={t('Owner and admin workspaces')} className={styles.navList}>
                    {ownedWorkspaces.map(item => (
                      <Link
                        className={styles.navLink}
                        href={`/workspace?orgId=${encodeURIComponent(item.id)}`}
                        aria-current={selectedOrgId === item.id ? 'page' : undefined}
                        key={item.id}
                      >
                        <div className={styles.navLinkHeader}>
                          <strong>{item.name}</strong>
                          <StatusBadge status={item.accreditation_status} />
                        </div>
                        <span className={styles.navMeta}>{t('Role: {role}', {role: t(item.role)})}</span>
                      </Link>
                    ))}
                  </nav>
                )}
              </Feedback>
            </section>

            <section className={`panel ${styles.sidebarCard}`} aria-labelledby="organization-grants-title">
              <div className={styles.sidebarHeading}>
                <h2 id="organization-grants-title">{t('Review workspaces')}</h2>
                <span className={styles.sidebarCount}>{moderatorGrants.length}</span>
              </div>
              <Feedback loading={organizations.loading} error={organizations.error} onRetry={organizations.reload}>
                {!moderatorGrants.length ? (
                  <p className={styles.sidebarEmpty}>{t('No moderator review workspaces are available.')}</p>
                ) : (
                  <nav className={styles.navList} aria-label={t('Moderator review workspaces')}>
                    {moderatorGrants.map(grant => (
                      <Link
                        className={styles.navLink}
                        href={`/workspace?orgId=${encodeURIComponent(grant.org_id)}`}
                        aria-current={selectedOrgId === grant.org_id ? 'page' : undefined}
                        key={grant.org_id}
                      >
                        <div className={styles.navLinkHeader}>
                          <strong>{grant.org_name}</strong>
                          <StatusBadge status={grant.accreditation_status} />
                        </div>
                        <span className={styles.navMeta}>{t('Moderator · registration and report review')}</span>
                      </Link>
                    ))}
                  </nav>
                )}
              </Feedback>
            </section>

            {!!memberGrants.length && (
              <section className={`panel ${styles.sidebarCard}`} aria-labelledby="organization-memberships-title">
                <div className={styles.sidebarHeading}>
                  <h2 id="organization-memberships-title">{t('Your memberships')}</h2>
                  <span className={styles.sidebarCount}>{memberGrants.length}</span>
                </div>
                <ul className={styles.membershipList}>
                  {memberGrants.map(grant => (
                    <li key={grant.org_id}>
                      <strong>{grant.org_name}</strong>
                      <span>{t('Member')} · {t(grant.accreditation_status)}</span>
                    </li>
                  ))}
                </ul>
                <p className={styles.sidebarHint}>{t('Member access does not include the staff roster or management controls.')}</p>
              </section>
            )}
          </aside>

          <section className={styles.main} aria-label={t('Organization workspace content')}>
            {!selectedOrgId && <OrganizationApplicationForm key={version} token={token} onCreated={organizations.reload} />}

            {!selectedOrgId && (
              <section className={`panel ${styles.selectPrompt}`}>
                <span className={styles.promptMark} aria-hidden="true">✳</span>
                <div>
                  <h2>{t('Choose a workspace')}</h2>
                  <p className="muted">{t('Select one of your management or review workspaces from the left to get started.')}</p>
                </div>
              </section>
            )}

            {selectedOrgId && (
              <section className={styles.selectedWorkspace} aria-label={t('Selected organization workspace')}>
                {organizations.loading ? <Feedback loading /> : organizations.error ? (
                  <Feedback error={organizations.error} onRetry={organizations.reload} />
                ) : !canAccessSelectedWorkspace && selectedModerator ? (
                  <ModeratorReviews key={`${selectedModerator.org_id}:${selectedEventId ?? ''}`} grant={selectedModerator} token={token} selectedEventId={selectedEventId} />
                ) : !canAccessSelectedWorkspace ? (
                  <p className={`panel muted ${styles.unavailable}`} role="status">{t('This workspace is unavailable to this account.')}</p>
                ) : (
                  <Feedback loading={workspace.loading} error={workspace.error} onRetry={workspace.reload}>
                    {workspace.data && (
                      <WorkspaceDetails
                        token={token}
                        sessionVersion={version}
                        workspace={workspace.data}
                        events={events.data}
                        eventsLoading={events.loading}
                        eventsError={events.error}
                        reloadEvents={events.reload}
                        reloadWorkspace={workspace.reload}
                        selectedEventId={selectedEventId}
                        onOwnershipChanged={async () => {
                          organizations.reload();
                          workspace.reload();
                          events.reload();
                          await refreshActor();
                        }}
                      />
                    )}
                  </Feedback>
                )}
              </section>
            )}
            {selectedOrgId && (
              <details className="panel">
                <summary className={styles.applicationSummary}>{t('Apply for another workspace')}</summary>
                <OrganizationApplicationForm key={version} token={token} onCreated={organizations.reload} />
              </details>
            )}
          </section>
        </div>
      </div>
    </>
  );
}

export function OrganizationWorkspacePage() {
  return <OrganizationWorkspaceContent />;
}
