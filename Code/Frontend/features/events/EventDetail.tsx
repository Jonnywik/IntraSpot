"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useState } from "react";
import { api } from "@/lib/api";
import { EventArtwork } from "@/app/event-artwork";
import { Feedback } from "@/components/feedback";
import { RegistrationAction } from "@/features/registrations/RegistrationAction";
import { useApiResource } from "@/lib/use-api-resource";
import { useSession } from "@/lib/session";
import { formatDate, formatTime } from "@/lib/date";
import type { PublicEvent } from "@/lib/types";
import { EventSocial } from "@/features/communication/EventSocial";

export function EventDetail() {
  const searchParams = useSearchParams();
  const eventId = searchParams.get("eventId");
  const { token, version } = useSession();
  const eventResource = useApiResource<PublicEvent>(
    eventId ? "/events/" + encodeURIComponent(eventId) : null,
    token,
  );
  const [updatedEvent, setUpdatedEvent] = useState<PublicEvent | null>(null);
  const [countsError, setCountsError] = useState(false);
  const event = updatedEvent?.id === eventId ? updatedEvent : eventResource.data;
  async function refreshCounts() {
    if (!eventId) return;
    try {
      const current = await api<PublicEvent>("/events/" + encodeURIComponent(eventId), {token});
      setUpdatedEvent(current);
      setCountsError(false);
    } catch { setCountsError(true); }
  }

  return (
    <div className="stack">
      <header className="page-heading">
        <Link href="/" className="text-action">← Discover</Link>
        <p className="eyebrow">Public event</p>
        <h1>{event?.title ?? "Event details"}</h1>
      </header>

      {!eventId ? (
        <div className="panel" role="alert">
          <p>Select an event from Discover to view its details.</p>
          <Link className="button button-secondary" href="/">Back to Discover</Link>
        </div>
      ) : (
        <Feedback loading={eventResource.loading} error={eventResource.error} onRetry={eventResource.reload}>
          {event && (
            <article className="panel stack">
              <div>
                <p className="eyebrow"><Link href={`/organizations?orgId=${encodeURIComponent(event.org_id)}`}>{event.organization_name}</Link></p>
                <h2>{event.title}</h2>
              </div>
              <EventArtwork event={event} />
              <p>{event.description}</p>
              <div className="event-facts">
                <span>{formatDate(event.starts_at)} · {formatTime(event.starts_at)}</span>
                <span>{event.venue_name}</span>
                <span>{event.venue_address}</span>
                <span>{event.cost_label}</span>
              </div>
              <div className="event-facts" role="group" aria-label="Event counts">
                <span><span className="muted">Interested</span> <strong>{event.interest_count}</strong></span>
                <span><span className="muted">Confirmed</span> <strong>{event.confirmed_count}</strong></span>
                <span><span className="muted">Reserved</span> <strong>{event.reserved_count ?? "Unavailable"}</strong></span>
                <span><span className="muted">Remaining</span> <strong>{event.remaining_spots}</strong></span>
              </div>
              <div className="event-facts" role="group" aria-label="Registration mode">
                <span><span className="muted">Registration</span> <strong>
                  {event.registration_mode === "approval" ? "Organizer approval" : "Instant confirmation"}
                </strong></span>
              </div>
              <EventSocial
                key={`${event.id}:${version}`}
                eventId={event.id}
                startsAt={event.starts_at}
                onReactionChanged={refreshCounts}
              />
              {countsError && <p className="muted" role="status">Attendance counts could not refresh. <button className="text-action" onClick={() => void refreshCounts()}>Refresh counts</button></p>}
              <RegistrationAction key={`${event.id}:${version}`} event={event} onOutcome={() => void refreshCounts()} />
            </article>
          )}
        </Feedback>
      )}
    </div>
  );
}
