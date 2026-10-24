"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useState } from "react";
import { api } from "@/lib/api";
import { EventArtwork } from "@/app/event-artwork";
import { FeaturedBadge } from "@/features/featured/FeaturedBadge";
import { Feedback } from "@/components/feedback";
import { RegistrationAction } from "@/features/registrations/RegistrationAction";
import { useApiResource } from "@/lib/use-api-resource";
import { useSession } from "@/lib/session";
import { useT } from "@/lib/i18n";
import { usePreferences } from "@/lib/preferences";
import { formatDate, formatTime } from "@/lib/date";
import type { PublicEvent } from "@/lib/types";
import { EventSocial } from "@/features/communication/EventSocial";
import { SaveEventButton } from "@/features/planning/SaveEventButton";
import { ConflictWarning } from "@/features/planning/ConflictWarning";
import { EventReportButton } from "@/features/eventsafety";
import styles from "./attendee-events.module.css";

function publicEventTags(event: PublicEvent): string[] {
  if (!("tags" in event) || !Array.isArray(event.tags)) return [];
  const tags: readonly unknown[] = event.tags;
  return tags
    .filter((tag): tag is string => typeof tag === "string")
    .map((tag) => tag.trim())
    .filter(Boolean);
}

function publicEventArea(event: PublicEvent): string | null {
  if (!("coarse_area" in event) || typeof event.coarse_area !== "string") return null;
  return event.coarse_area.trim() || null;
}

export function EventDetail() {
  const t = useT();
  const { preferences } = usePreferences();
  const searchParams = useSearchParams();
  const eventId = searchParams.get("eventId");
  const { token, version } = useSession();
  const eventResource = useApiResource<PublicEvent>(
    eventId ? "/events/" + encodeURIComponent(eventId) : null,
    token,
  );
  const [updatedEvent, setUpdatedEvent] = useState<PublicEvent | null>(null);
  const [countsError, setCountsError] = useState(false);
  const [planningRevision, setPlanningRevision] = useState(0);
  const event = updatedEvent?.id === eventId ? updatedEvent : eventResource.data;
  const tags = event ? publicEventTags(event) : [];
  const coarseArea = event ? publicEventArea(event) : null;
  async function refreshCounts() {
    if (!eventId) return;
    try {
      const current = await api<PublicEvent>("/events/" + encodeURIComponent(eventId), {token});
      setUpdatedEvent(current);
      setPlanningRevision(value => value + 1);
      setCountsError(false);
    } catch { setCountsError(true); }
  }

  return (
    <div className={`stack ${styles.eventDetail}`}>
      <header className="page-heading">
        <nav className={styles.detailNavigation} aria-label={t("Event navigation")}>
          <Link href="/" className="text-action">{t("← Discover")}</Link>
        </nav>
        <p className="eyebrow">{t("Public event")}</p>
        <h1>{event?.title ?? t("Event details")}</h1>
      </header>

      {!eventId ? (
        <div className={`panel ${styles.missingEvent}`} role="alert">
          <p>{t("Select an event from Discover to view its details.")}</p>
          <Link className="button button-secondary" href="/">{t("Back to Discover")}</Link>
        </div>
      ) : (
        <Feedback loading={eventResource.loading} error={eventResource.error} onRetry={eventResource.reload}>
          {event && (
            <article className={`panel stack ${styles.detailPanel}`}>
              <div>
                <p className="eyebrow"><Link href={`/organizations?orgId=${encodeURIComponent(event.org_id)}`}>{event.organization_name}</Link></p>
                {event.event_type === "flash" && (
                  <span className={styles.eventTypeBadge}>{t("Flash event")}</span>
                )}
                {event.is_featured && <FeaturedBadge />}
                <h2>{event.title}</h2>
              </div>
              <EventArtwork event={event} priority />
              <SaveEventButton key={`${event.id}:${version}`} eventId={event.id} />
              {token && <EventReportButton key={`safety:${version}:${event.id}`} eventId={event.id} token={token} />}
              <p>{event.description}</p>
              <dl className={styles.detailFacts}>
                <div><dt>{t("Date and time")}</dt><dd>{formatDate(event.starts_at, preferences.language)} · {formatTime(event.starts_at, preferences.language)}</dd></div>
                <div><dt>{t("Venue")}</dt><dd>{event.venue_name}</dd></div>
                <div><dt>{t("Address")}</dt><dd>{event.venue_address}</dd></div>
                <div><dt>{t("Cost")}</dt><dd>{event.cost_label}</dd></div>
                {coarseArea && <div><dt>{t("Broad area")}</dt><dd>{coarseArea}</dd></div>}
                {tags.length > 0 && <div><dt>{t("Tags")}</dt><dd>{tags.join(", ")}</dd></div>}
              </dl>
              <dl className={styles.eventCounts} aria-label={t("Event counts")}>
                <div><dt>{t("Interested")}</dt><dd>{event.interest_count}</dd></div>
                <div><dt>{t("Confirmed")}</dt><dd>{event.confirmed_count}</dd></div>
                <div><dt>{t("Reserved")}</dt><dd>{event.reserved_count ?? t("Unavailable")}</dd></div>
                <div><dt>{t("Remaining")}</dt><dd>{event.remaining_spots}</dd></div>
              </dl>
              <dl className={styles.registrationModeFacts} aria-label={t("Registration mode")}>
                <div><dt>{t("Registration")}</dt><dd>
                  {event.registration_mode === "approval" ? t("Organizer approval") : t("Instant confirmation")}
                </dd></div>
              </dl>
              <EventSocial
                key={`${event.id}:${version}`}
                eventId={event.id}
                startsAt={event.starts_at}
                onReactionChanged={refreshCounts}
              />
              {countsError && (
                <div className={styles.refreshNotice} role="status" aria-live="polite">
                  <p>{t("Attendance counts could not refresh.")}</p>
                  <button
                    className="text-action"
                    type="button"
                    aria-label={t("Refresh attendance counts")}
                    onClick={() => void refreshCounts()}
                  >
                    {t("Refresh counts")}
                  </button>
                </div>
              )}
              <ConflictWarning key={`${event.id}:${version}`} eventId={event.id} revision={planningRevision} />
              <RegistrationAction key={`${event.id}:${version}`} event={event} onOutcome={() => void refreshCounts()} />
            </article>
          )}
          {!eventResource.loading && !eventResource.error && !event && (
            <div className={`panel ${styles.missingEvent}`} role="status">
              <h2>{t("Event details unavailable")}</h2>
              <p>{t("This event may have ended or is no longer available.")}</p>
              <Link className="button button-secondary" href="/">{t("Back to Discover")}</Link>
            </div>
          )}
        </Feedback>
      )}
    </div>
  );
}
