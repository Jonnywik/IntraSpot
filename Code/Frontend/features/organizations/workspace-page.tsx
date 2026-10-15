'use client';

import Link from 'next/link';
import { useSearchParams } from 'next/navigation';
import { useState, type FormEvent } from 'react';
import { api } from '@/lib/api';
import { formatDate, formatTime } from '@/lib/date';
import { useSession } from '@/lib/session';
import { useApiResource } from '@/lib/use-api-resource';
import type { MyOrganizations, Organization, PrivateEvent, PublicEvent, Workspace } from '@/lib/types';
import { DecisionHistory, StatusBadge } from './shared';
import { Feedback } from '@/components/feedback';
import { EventChanges } from './EventChanges';
import { RegistrationReview } from './RegistrationReview';
import { ModerationReportQueue } from '@/features/moderation/report-queue';
import { StaffMembership } from '@/features/memberships/StaffMembership';

function draftHref(orgId: string, eventId?: string) {
  const params = new URLSearchParams({orgId});
  if (eventId) params.set('eventId', eventId);
  return `/draft?${params.toString()}`;
}

function eventHref(eventId: string) {
  return `/events?${new URLSearchParams({eventId}).toString()}`;
}

function OrganizationApplicationForm({token, onCreated}: {
  token: string;
  onCreated: () => void;
}) {
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
      setError('Enter an organization name.');
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
      setError(requestError instanceof Error ? requestError.message : 'The application could not be submitted.');
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <section className="panel" id="organization-application" aria-labelledby="organization-application-title">
      <h2 id="organization-application-title">Apply for an organization workspace</h2>
      <p className="muted">
        Submit the organization name and optionally add a short description. Accreditation is assessed offline by a platform admin; no evidence upload is part of this flow.
      </p>
      <form onSubmit={submit}>
        <div className="field">
          <label htmlFor="organization-name">Organization name</label>
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
          <label htmlFor="organization-description">Description <span className="muted">(optional)</span></label>
          <textarea
            id="organization-description"
            name="description"
            value={description}
            onChange={event => setDescription(event.target.value)}
          />
        </div>
        <div className="actions">
          <button className="button" type="submit" disabled={submitting}>
            {submitting ? 'Submitting…' : 'Submit organization'}
          </button>
        </div>
      </form>
      {error && <p className="panel error" role="alert">{error}</p>}
      {created && (
        <div className="panel" role="status">
          <p><strong>{created.name}</strong> was created with status <StatusBadge status={created.accreditation_status} />.</p>
          <p className="muted">Submitted {formatDate(created.created_at)} · {formatTime(created.created_at)} (Manila).</p>
          <div className="actions">
            <Link className="button button-secondary" href={`/workspace?orgId=${encodeURIComponent(created.id)}`}>
              Open workspace
            </Link>
            {created.accreditation_status === 'pending' && (
              <Link className="button" href={draftHref(created.id)}>Start a private draft</Link>
            )}
          </div>
        </div>
      )}
    </section>
  );
}

function OrganizationEvents({workspace, events, loading, error, onRetry}: {
  workspace: Workspace;
  events: PrivateEvent[] | null;
  loading: boolean;
  error: Error | null;
  onRetry: () => void;
}) {
  const isManager = workspace.role === 'owner' || workspace.role === 'admin';
  const [changedWorkspaceId, setChangedWorkspaceId] = useState<string | null>(null);
  const canOpenEditor = isManager &&
    (workspace.accreditation_status === 'approved' || workspace.accreditation_status === 'pending');

  return (
    <section className="panel" aria-labelledby="organization-events-title">
      <div className="actions">
        <h2 id="organization-events-title">Organization events</h2>
        {canOpenEditor && (
          <Link className="button" href={draftHref(workspace.id)}>
            {workspace.accreditation_status === 'approved' ? 'Create event draft' : 'Create private draft'}
          </Link>
        )}
      </div>
      {changedWorkspaceId === workspace.id && <p role="status">Material changes submitted. Review the updated event and reconfirmation requests.</p>}
      <Feedback loading={loading} error={error} onRetry={onRetry}>
        {!events?.length ? (
          <p className="empty-state muted">No events are available for this workspace yet.</p>
        ) : (
          <div className="feed">
            {events.map(event => (
              <article className="event-card" key={event.id}>
                <header>
                  <h3>{event.title || 'Untitled draft'}</h3>
                  <StatusBadge status={event.status} />
                </header>
                <p className="event-summary">{event.summary || 'No summary has been added yet.'}</p>
                {event.starts_at && (
                  <p className="muted">
                    <time dateTime={event.starts_at}>
                      {formatDate(event.starts_at)} · {formatTime(event.starts_at)} (Manila)
                    </time>
                  </p>
                )}
                <div className="actions">
                  {canOpenEditor && event.status === 'draft' && (
                    <Link className="button button-secondary" href={draftHref(workspace.id, event.id)}>
                      Open private draft
                    </Link>
                  )}
                  {isManager && workspace.accreditation_status === 'approved' && event.status === 'published' && (
                    <>
                      <Link className="button button-secondary" href={draftHref(workspace.id, event.id)}>
                        Manage event
                      </Link>
                      <Link href={eventHref(event.id)}>View published event</Link>
                    </>
                  )}
                </div>
                {event.status === 'published' && isManager && (
                  <div className="stack">
                    <RegistrationReview eventId={event.id} eventEndsAt={event.ends_at} />
                    {isManager && workspace.accreditation_status === 'approved' && (
                      <EventChanges
                        key={`${event.id}:${event.material_revision}`}
                        event={event}
                        onChanged={() => { setChangedWorkspaceId(workspace.id); onRetry(); }}
                      />
                    )}
                  </div>
                )}
              </article>
            ))}
          </div>
        )}
      </Feedback>
    </section>
  );
}

function ModeratorReviews({grant, token}: {
  grant: MyOrganizations['grants'][number];
  token: string;
}) {
  const events = useApiResource<PublicEvent[]>('/events', token);
  const organizationEvents = (events.data ?? []).filter(event => event.org_id === grant.org_id);

  return (
    <div className="stack">
      <section className="panel">
        <h2>{grant.org_name}</h2>
        <p className="muted">Moderators may review registration decisions for this organization. The assigned reviewer is accountable for each deadline; other authorized reviewers may decide at the initial or extended stage, while escalation excludes the first reviewer. Event editing and capacity changes remain with the owner and admins.</p>
      </section>
      {grant.accreditation_status === 'approved' && <StaffMembership orgId={grant.org_id} role={grant.role} />}
      <ModerationReportQueue key={`${token}:${grant.org_id}`} token={token} orgId={grant.org_id} />
      <section className="panel stack" aria-label="Published events for registration review">
        <h2>Published events</h2>
        <Feedback loading={events.loading} error={events.error} onRetry={events.reload}>
          {!organizationEvents.length ? (
            <p className="empty-state muted">No published events are available for review.</p>
          ) : (
            <div className="feed">
              {organizationEvents.map(event => (
                <article className="event-card stack" key={event.id}>
                  <header>
                    <h3>{event.title}</h3>
                    {event.starts_at && (
                      <p className="muted">{formatDate(event.starts_at)} · {formatTime(event.starts_at)} (Manila)</p>
                    )}
                  </header>
                  <RegistrationReview eventId={event.id} eventEndsAt={event.ends_at} />
                </article>
              ))}
            </div>
          )}
        </Feedback>
      </section>
    </div>
  );
}

function WorkspaceDetails({token, workspace, events, eventsLoading, eventsError, reloadEvents}: {
  token: string;
  workspace: Workspace;
  events: PrivateEvent[] | null;
  eventsLoading: boolean;
  eventsError: Error | null;
  reloadEvents: () => void;
}) {
  return (
    <div className="stack">
      <section className="panel" aria-labelledby="workspace-detail-title">
        <div className="actions">
          <h2 id="workspace-detail-title">{workspace.name}</h2>
          <StatusBadge status={workspace.accreditation_status} />
        </div>
        <p>{workspace.description || 'No organization description was provided.'}</p>
        <p className="muted">Workspace role: {workspace.role}</p>
        <DecisionHistory decisions={workspace.decisions} />
      </section>
      <OrganizationEvents
        workspace={workspace}
        events={events}
        loading={eventsLoading}
        error={eventsError}
        onRetry={reloadEvents}
      />
      <ModerationReportQueue key={`${workspace.id}`} token={token} orgId={workspace.id} />
      {workspace.accreditation_status === 'approved' && <StaffMembership orgId={workspace.id} role={workspace.role} />}
    </div>
  );
}

function OrganizationWorkspaceContent() {
  const searchParams = useSearchParams();
  const selectedOrgId = searchParams.get('orgId');
  const {token, authLoading, error: sessionError, version} = useSession();
  const organizations = useApiResource<MyOrganizations>(token ? '/me/organizations' : null, token);
  const ownedWorkspaces = organizations.data?.owned_workspaces ?? [];
  const grants = organizations.data?.grants ?? [];
  const otherGrants = grants.filter(grant => !ownedWorkspaces.some(workspace => workspace.id === grant.org_id));
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
      {sessionError?.message || 'Choose a local account in the header to open organization workspaces.'}
    </section>;
  }

  return (
    <>
      <p className="panel desktop-required" role="note">
        Organization management is available on desktop. Open this page on a wider screen to apply or manage a workspace.
      </p>
      <div className="management-desktop stack">
        <header className="page-heading">
          <p className="eyebrow">Organization management</p>
          <h1>Workspace</h1>
          <p className="muted">Applications, access, decisions, and event links for organizations connected to your account.</p>
        </header>

        <div className="management-layout">
          <aside className="stack" aria-label="Organization workspace navigation">
            <section className="panel" aria-labelledby="my-workspaces-title">
              <h2 id="my-workspaces-title">Your workspaces</h2>
              <Link className="button button-secondary" href="#organization-application">Apply for a workspace</Link>
              <Feedback loading={organizations.loading} error={organizations.error} onRetry={organizations.reload}>
                {!ownedWorkspaces.length ? (
                  <p className="empty-state muted">No owner or admin workspaces are available for this account.</p>
                ) : (
                  <nav aria-label="Owner and admin workspaces" className="feed">
                    {ownedWorkspaces.map(item => (
                      <Link
                        className="event-card"
                        href={`/workspace?orgId=${encodeURIComponent(item.id)}`}
                        aria-current={selectedOrgId === item.id ? 'page' : undefined}
                        key={item.id}
                      >
                        <div className="actions">
                          <strong>{item.name}</strong>
                          <StatusBadge status={item.accreditation_status} />
                        </div>
                        <p className="muted">Role: {item.role}</p>
                      </Link>
                    ))}
                  </nav>
                )}
              </Feedback>
            </section>

            <section className="panel" aria-labelledby="organization-grants-title">
              <h2 id="organization-grants-title">Other organization access</h2>
              <Feedback loading={organizations.loading} error={organizations.error} onRetry={organizations.reload}>
                {!otherGrants.length ? (
                  <p className="empty-state muted">No additional organization access grants are available.</p>
                ) : (
                  <ul className="feed">
                    {otherGrants.map(grant => (
                      <li className="event-card" key={grant.org_id}>
                        <div className="actions">
                          <strong>{grant.org_name}</strong>
                          <StatusBadge status={grant.accreditation_status} />
                        </div>
                        <p className="muted">Role: {grant.role}</p>
                        {grant.role === 'moderator' && (
                          <Link className="button button-secondary" href={`/workspace?orgId=${encodeURIComponent(grant.org_id)}`}>
                            Review published event registrations
                          </Link>
                        )}
                      </li>
                    ))}
                  </ul>
                )}
              </Feedback>
            </section>
          </aside>

          <div className="stack">
            <OrganizationApplicationForm key={version} token={token} onCreated={organizations.reload} />

            {selectedOrgId && (
              <section aria-label="Selected organization workspace">
                {organizations.loading ? <Feedback loading /> : organizations.error ? (
                  <Feedback error={organizations.error} onRetry={organizations.reload} />
                ) : !canAccessSelectedWorkspace && selectedModerator ? (
                  <ModeratorReviews grant={selectedModerator} token={token} />
                ) : !canAccessSelectedWorkspace ? (
                  <p className="panel muted" role="status">This workspace is unavailable to this account.</p>
                ) : (
                  <Feedback loading={workspace.loading} error={workspace.error} onRetry={workspace.reload}>
                    {workspace.data && (
                      <WorkspaceDetails
                        token={token}
                        workspace={workspace.data}
                        events={events.data}
                        eventsLoading={events.loading}
                        eventsError={events.error}
                        reloadEvents={events.reload}
                      />
                    )}
                  </Feedback>
                )}
              </section>
            )}
          </div>
        </div>
      </div>
    </>
  );
}

export function OrganizationWorkspacePage() {
  return <OrganizationWorkspaceContent />;
}
