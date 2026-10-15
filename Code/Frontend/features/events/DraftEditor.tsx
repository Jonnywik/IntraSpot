"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useRef, useState, type FormEvent } from "react";
import { EventArtwork } from "@/app/event-artwork";
import { Feedback } from "@/components/feedback";
import { api } from "@/lib/api";
import { fromUtcToManila, formatDate, formatTime, toUtcFromManila } from "@/lib/date";
import { useApiResource } from "@/lib/use-api-resource";
import { useSession } from "@/lib/session";
import type { EventDraftInput, PrivateEvent, PublicEvent, Workspace } from "@/lib/types";

type BannerKey = NonNullable<EventDraftInput["banner_key"]>;
type RegistrationMode = EventDraftInput["registration_mode"];
type DraftForm = {
  title: string;
  summary: string;
  description: string;
  startsAt: string;
  endsAt: string;
  venueName: string;
  venueAddress: string;
  capacity: string;
  bannerKey: BannerKey | "";
  costLabel: string;
  registrationMode: RegistrationMode;
  reviewWindowMinutes: string;
};

const EMPTY_FORM: DraftForm = {
  title: "",
  summary: "",
  description: "",
  startsAt: "",
  endsAt: "",
  venueName: "",
  venueAddress: "",
  capacity: "",
  bannerKey: "",
  costLabel: "Free",
  registrationMode: "instant",
  reviewWindowMinutes: "",
};

const EMPTY_DRAFT_INPUT: EventDraftInput = {
  summary: "",
  cost_label: "Free",
  registration_mode: "instant",
  review_window_minutes: null,
  event_type: "scheduled",
};

function formFromDraft(draft: PrivateEvent): DraftForm {
  return {
    title: draft.title ?? "",
    summary: draft.summary,
    description: draft.description ?? "",
    startsAt: fromUtcToManila(draft.starts_at),
    endsAt: fromUtcToManila(draft.ends_at),
    venueName: draft.venue_name ?? "",
    venueAddress: draft.venue_address ?? "",
    capacity: draft.capacity === null ? "" : String(draft.capacity),
    bannerKey: draft.banner_key ?? "",
    costLabel: draft.cost_label,
    registrationMode: draft.registration_mode ?? "instant",
    reviewWindowMinutes: draft.review_window_minutes == null ? "" : String(draft.review_window_minutes),
  };
}

function inputFromForm(form: DraftForm): EventDraftInput {
  return {
    title: form.title.trim() || null,
    summary: form.summary,
    description: form.description.trim() ? form.description : null,
    starts_at: form.startsAt ? toUtcFromManila(form.startsAt) : null,
    ends_at: form.endsAt ? toUtcFromManila(form.endsAt) : null,
    venue_name: form.venueName.trim() || null,
    venue_address: form.venueAddress.trim() || null,
    capacity: form.capacity.trim() ? Number(form.capacity) : null,
    banner_key: form.bannerKey || null,
    cost_label: form.costLabel,
    registration_mode: form.registrationMode,
    review_window_minutes:
      form.registrationMode === "approval" && form.reviewWindowMinutes.trim()
        ? Number(form.reviewWindowMinutes)
        : null,
    event_type: "scheduled",
  };
}

function formatPreviewDate(value: string, formatter: (date: string) => string) {
  if (!value) return "";
  try {
    return formatter(toUtcFromManila(value));
  } catch {
    return "Enter a valid Manila date and time.";
  }
}

export function DraftEditor() {
  const searchParams = useSearchParams();
  const requestedOrgId = searchParams.get("orgId") ?? "";
  const eventId = searchParams.get("eventId") ?? "";

  return (
    <DraftEditorContent
      key={eventId}
      eventId={eventId}
      requestedOrgId={requestedOrgId}
    />
  );
}

function DraftEditorContent({
  eventId,
  requestedOrgId,
}: {
  eventId: string;
  requestedOrgId: string;
}) {
  const router = useRouter();
  const { token, authLoading } = useSession();
  const draftResource = useApiResource<PrivateEvent>(
    eventId && token ? "/events/" + encodeURIComponent(eventId) + "/draft" : null,
    token,
  );
  const [draft, setDraft] = useState<PrivateEvent | null>(null);
  const [formState, setFormState] = useState<DraftForm | null>(null);
  const [dirty, setDirty] = useState(false);
  const [creating, setCreating] = useState(false);
  const [saving, setSaving] = useState(false);
  const [publishing, setPublishing] = useState(false);
  const [mutationError, setMutationError] = useState<Error | null>(null);
  const [message, setMessage] = useState("");
  const [publishedEvent, setPublishedEvent] = useState<PublicEvent | null>(null);
  const mutationInFlight = useRef(false);

  const currentDraft = draft ?? draftResource.data;
  const form = formState ?? (currentDraft ? formFromDraft(currentDraft) : EMPTY_FORM);
  const orgId = currentDraft?.org_id || requestedOrgId;
  const workspaceResource = useApiResource<Workspace>(
    orgId && token ? "/organizations/" + encodeURIComponent(orgId) + "/workspace" : null,
    token,
  );
  const workspace = workspaceResource.data;
  const readOnly =
    currentDraft?.status === "published" ||
    workspace?.accreditation_status === "rejected" ||
    publishedEvent !== null;

  function updateField<K extends keyof DraftForm>(field: K, value: DraftForm[K]) {
    setFormState((previous) => ({ ...(previous ?? form), [field]: value }));
    setDirty(true);
    setMessage("");
    setMutationError(null);
  }

  async function createDraft() {
    if (!token || !orgId || !workspace || workspace.accreditation_status === "rejected" || mutationInFlight.current) return;
    mutationInFlight.current = true;
    setCreating(true);
    setMutationError(null);
    setMessage("");
    try {
      const created = await api<PrivateEvent>(
        "/organizations/" + encodeURIComponent(orgId) + "/events",
        { token, method: "POST", body: EMPTY_DRAFT_INPUT },
      );
      setDraft(created);
      setFormState(formFromDraft(created));
      setDirty(false);
      router.replace(
        "/draft?" +
          new URLSearchParams({ orgId, eventId: created.id }).toString(),
      );
      setMessage("Draft created.");
    } catch (error) {
      setMutationError(error instanceof Error ? error : new Error("The draft could not be created."));
    } finally {
      mutationInFlight.current = false;
      setCreating(false);
    }
  }

  async function saveDraft(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!token || !currentDraft || readOnly || mutationInFlight.current) return;
    mutationInFlight.current = true;
    setSaving(true);
    setMutationError(null);
    setMessage("");
    try {
      const updated = await api<PrivateEvent>(
        "/events/" + encodeURIComponent(currentDraft.id) + "/draft",
        { token, method: "PATCH", body: inputFromForm(form) },
      );
      setDraft(updated);
      setDirty(false);
      setMessage("Draft saved.");
    } catch (error) {
      setMutationError(error instanceof Error ? error : new Error("The draft could not be saved."));
    } finally {
      mutationInFlight.current = false;
      setSaving(false);
    }
  }

  async function publishDraft() {
    if (!token || !currentDraft || readOnly || dirty || workspace?.accreditation_status !== "approved" || mutationInFlight.current) return;
    mutationInFlight.current = true;
    setPublishing(true);
    setMutationError(null);
    setMessage("");
    try {
      const published = await api<PublicEvent>(
        "/events/" + encodeURIComponent(currentDraft.id) + "/publish",
        { token, method: "POST" },
      );
      setPublishedEvent(published);
      setDraft({
        ...currentDraft,
        status: "published",
        published_at: published.published_at,
      });
      setMessage("Event published.");
    } catch (error) {
      setMutationError(error instanceof Error ? error : new Error("The event could not be published."));
    } finally {
      mutationInFlight.current = false;
      setPublishing(false);
    }
  }

  if (authLoading) {
    return <p className="panel muted" role="status">Checking the selected local account…</p>;
  }
  if (!token) {
    return (
      <div className="panel">
        <h1>Sign in to edit an event</h1>
        <p className="muted">Choose a fictional local account in the header to continue.</p>
      </div>
    );
  }

  const loading =
    Boolean(eventId && draftResource.loading) ||
    Boolean(orgId && workspaceResource.loading);
  if (loading) return <p className="panel muted" role="status">Loading your event workspace…</p>;
  if (eventId && draftResource.error) {
    return <Feedback error={draftResource.error} onRetry={draftResource.reload} />;
  }
  if (orgId && workspaceResource.error) {
    return <Feedback error={workspaceResource.error} onRetry={workspaceResource.reload} />;
  }
  if (!orgId) {
    return (
      <div className="panel">
        <h1>Choose an organization</h1>
        <p className="muted">Open the event editor from an organization workspace.</p>
      </div>
    );
  }
  if (!workspace) return <p className="panel muted" role="status">Loading your organization workspace…</p>;

  const accreditationLabel =
    workspace.accreditation_status === "approved"
      ? "Organization approved"
      : workspace.accreditation_status === "pending"
        ? "Organization pending"
        : "Organization rejected";

  if (!currentDraft && workspace.accreditation_status === "rejected") {
    return (
      <div className="stack">
        <header className="page-heading">
          <p className="eyebrow">Event authoring</p>
          <h1>Organization workspace</h1>
        </header>
        <section className="panel">
          <p className="status-chip">{accreditationLabel}</p>
          <p>This workspace is read-only after the organization review was rejected.</p>
        </section>
      </div>
    );
  }

  if (!currentDraft) {
    return (
      <>
        <p className="panel desktop-required" role="note">
          Event draft management is available on desktop. Open this page on a wider screen to create or edit a draft.
        </p>
        <div className="management-desktop stack">
          <header className="page-heading">
            <p className="eyebrow">Event authoring</p>
            <h1>Create an event draft</h1>
            <p className="muted">Drafts may be prepared while organization review is pending.</p>
          </header>
          <section className="panel stack">
            <p className="status-chip">{accreditationLabel}</p>
            {mutationError && <p className="error" role="alert">{mutationError.message}</p>}
            {message && <p role="status">{message}</p>}
            <div className="actions">
              <button className="button" type="button" disabled={creating} onClick={createDraft}>
                {creating ? "Creating draft…" : "Create draft"}
              </button>
            </div>
          </section>
        </div>
      </>
    );
  }

  const reviewWindowValue = Number(form.reviewWindowMinutes);
  const reviewWindowValid = form.registrationMode === "instant" ||
    (form.reviewWindowMinutes.trim() !== "" && Number.isInteger(reviewWindowValue) && reviewWindowValue >= 15 && reviewWindowValue <= 2880);
  const canPublish =
    workspace.accreditation_status === "approved" &&
    currentDraft.status === "draft" &&
    reviewWindowValid &&
    !dirty &&
    !saving &&
    !publishing;

  return (
    <div className="stack">
      <header className="page-heading">
        <p className="eyebrow">Event authoring</p>
        <h1>{readOnly ? "Event preview" : "Edit event draft"}</h1>
        <p className="actions">
          <span className="status-chip">{accreditationLabel}</span>
          <span className="status-chip">{currentDraft.status === "published" ? "Published" : "Draft"}</span>
        </p>
      </header>

      {readOnly && (
        <div className="panel">
          <p className="muted">
            {workspace.accreditation_status === "rejected"
              ? "This event is read-only because the organization review was rejected."
              : "Published events cannot be edited here."}
          </p>
          {currentDraft.status === "published" && (
            <Link href={"/events?eventId=" + encodeURIComponent(currentDraft.id)} className="text-action">
              View published event
            </Link>
          )}
        </div>
      )}

      {mutationError && <p className="panel error" role="alert">{mutationError.message}</p>}
      {message && <p className="panel" role="status">{message}</p>}

      {!readOnly && (
        <>
          <p className="panel desktop-required" role="note">
            Event draft management is available on desktop. Open this page on a wider screen to edit or publish.
          </p>
          <div className="management-desktop stack">
          <form className="panel stack" onSubmit={saveDraft} noValidate>
          <h2>Event details</h2>
          <div className="form-grid">
            <label className="field">
              Event title
              <input disabled={saving || publishing} value={form.title} onChange={(event) => updateField("title", event.target.value)} />
            </label>
            <label className="field">
              Short summary
              <input disabled={saving || publishing} value={form.summary} onChange={(event) => updateField("summary", event.target.value)} />
            </label>
            <label className="field">
              Starts at (Manila time)
              <input
                disabled={saving || publishing}
                type="datetime-local"
                value={form.startsAt}
                onChange={(event) => updateField("startsAt", event.target.value)}
              />
            </label>
            <label className="field">
              Ends at (Manila time)
              <input
                disabled={saving || publishing}
                type="datetime-local"
                value={form.endsAt}
                onChange={(event) => updateField("endsAt", event.target.value)}
              />
            </label>
            <label className="field">
              Venue name
              <input disabled={saving || publishing} value={form.venueName} onChange={(event) => updateField("venueName", event.target.value)} />
            </label>
            <label className="field">
              Venue address
              <input disabled={saving || publishing} value={form.venueAddress} onChange={(event) => updateField("venueAddress", event.target.value)} />
            </label>
            <label className="field">
              Capacity
              <input
                disabled={saving || publishing}
                type="number"
                value={form.capacity}
                onChange={(event) => updateField("capacity", event.target.value)}
              />
            </label>
            <label className="field">
              Artwork theme
              <select
                aria-label="Artwork theme"
                disabled={saving || publishing}
                value={form.bannerKey}
                onChange={(event) => updateField("bannerKey", event.target.value as BannerKey | "")}
              >
                <option value="">Choose a theme</option>
                <option value="heritage">Heritage</option>
                <option value="design">Design</option>
                <option value="garden">Garden</option>
                <option value="music">Music</option>
              </select>
            </label>
            <label className="field">
              Cost label
              <input disabled={saving || publishing} value={form.costLabel} onChange={(event) => updateField("costLabel", event.target.value)} />
            </label>
            <label className="field">
              Registration mode
              <select
                disabled={saving || publishing}
                value={form.registrationMode}
                onChange={(event) => updateField("registrationMode", event.target.value as RegistrationMode)}
              >
                <option value="instant">Instant acceptance</option>
                <option value="approval">Organization approval</option>
              </select>
            </label>
            {form.registrationMode === "approval" && (
              <label className="field">
                Review window (15–2,880 minutes)
                <input
                  disabled={saving || publishing}
                  type="number"
                  min={15}
                  max={2880}
                  step={1}
                  value={form.reviewWindowMinutes}
                  onChange={(event) => updateField("reviewWindowMinutes", event.target.value)}
                  aria-describedby="review-window-help"
                />
                <span className="muted" id="review-window-help">
                  The saved draft can be incomplete. Set a valid window before publishing; review deadlines are capped at the event start.
                </span>
              </label>
            )}
          </div>
          <label className="field">
            Description
            <textarea disabled={saving || publishing} value={form.description} onChange={(event) => updateField("description", event.target.value)} />
          </label>
          <div className="actions">
            <button className="button button-secondary" type="submit" disabled={saving || publishing}>
              {saving ? "Saving…" : "Save draft"}
            </button>
            {workspace.accreditation_status === "pending" && (
              <button className="button" type="button" disabled aria-describedby="publish-reason">
                Publish
              </button>
            )}
            {workspace.accreditation_status === "approved" && (
              <button className="button" type="button" disabled={!canPublish} onClick={publishDraft}>
                {publishing ? "Publishing…" : "Publish"}
              </button>
            )}
          </div>
          {workspace.accreditation_status === "pending" && (
            <p id="publish-reason" className="muted">
              Publishing is disabled until a platform administrator approves this organization.
            </p>
          )}
          {workspace.accreditation_status === "approved" && dirty && (
            <p className="muted">Save your changes before publishing.</p>
          )}
          {workspace.accreditation_status === "approved" && form.registrationMode === "approval" && !reviewWindowValid && (
            <p className="muted" role="status">Enter a whole number from 15 to 2,880 minutes before publishing.</p>
          )}
          </form>
          <section className="panel stack" aria-label="Event preview">
          <div>
            <p className="eyebrow">Preview</p>
            <p className="muted">{currentDraft.organization_name}</p>
            <h2>{form.title || "Untitled event"}</h2>
          </div>
          <EventArtwork event={{ banner_key: form.bannerKey || null, title: form.title || "Untitled event" }} />
          <p>{form.summary || "No summary added yet."}</p>
          <p>{form.description || "No description added yet."}</p>
          <div className="event-facts">
            <span>
              {form.startsAt
                ? formatPreviewDate(form.startsAt, formatDate) + " · " + formatPreviewDate(form.startsAt, formatTime)
                : "Date and time not set"}
            </span>
            <span>{form.venueName || "Venue not set"}</span>
            <span>{form.costLabel || "Cost not set"}</span>
            <span>
              {form.registrationMode === "approval"
                ? `Approval required · ${form.reviewWindowMinutes || "No review window"} minutes`
                : "Instant acceptance"}
            </span>
          </div>
          </section>
          </div>
        </>
      )}

      {readOnly && (
        <section className="panel stack" aria-label="Read-only event preview">
          <div>
            <p className="eyebrow">{currentDraft.organization_name}</p>
            <h2>{currentDraft.title || "Untitled draft"}</h2>
          </div>
          <EventArtwork event={currentDraft} />
          <p>{currentDraft.summary || "No summary added yet."}</p>
          {currentDraft.description && <p>{currentDraft.description}</p>}
          <div className="event-facts">
            {currentDraft.starts_at && (
              <span>{formatDate(currentDraft.starts_at)} · {formatTime(currentDraft.starts_at)}</span>
            )}
            {currentDraft.venue_name && <span>{currentDraft.venue_name}</span>}
            {currentDraft.venue_address && <span>{currentDraft.venue_address}</span>}
            <span>{currentDraft.cost_label}</span>
            <span>
              {currentDraft.registration_mode === "approval"
                ? `Approval required · ${currentDraft.review_window_minutes ?? "No review window"} minutes`
                : "Instant acceptance"}
            </span>
          </div>
        </section>
      )}

      {publishedEvent && (
        <div className="panel">
          <p>The backend published this event.</p>
          <Link className="button button-secondary" href={"/events?eventId=" + encodeURIComponent(publishedEvent.id)}>
            View published event
          </Link>
        </div>
      )}
    </div>
  );
}
