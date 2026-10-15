"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { EventArtwork } from "@/app/event-artwork";
import { Feedback } from "@/components/feedback";
import { Icon } from "@/components/icon";
import { useApiResource } from "@/lib/use-api-resource";
import { useSession } from "@/lib/session";
import { formatDate, formatTime } from "@/lib/date";
import type { MyOrganizations, PublicEvent } from "@/lib/types";
import { EventSocialPreview } from "@/features/communication/EventSocial";

type EventSort = "upcoming" | "newest";

export function DiscoverFeed() {
  const { actor, token } = useSession();
  const [query, setQuery] = useState("");
  const [sort, setSort] = useState<EventSort>("upcoming");
  const [myClubsSelected, setMyClubsSelected] = useState(false);

  const organizations = useApiResource<MyOrganizations>(
    actor?.eligible && token ? "/me/organizations" : null,
    token,
  );
  const myClubOrganizationIds = useMemo(
    () =>
      new Set(
        actor?.eligible
          ? (organizations.data?.grants ?? [])
              .map((grant) => grant.org_id)
          : [],
      ),
    [actor?.eligible, organizations.data],
  );
  const myClubsAvailable = myClubOrganizationIds.size > 0;
  const myClubsActive = myClubsSelected && myClubsAvailable;

  const eventsPath = useMemo(() => {
    const parameters = new URLSearchParams();
    const search = query.trim();
    if (search) parameters.set("q", search);
    parameters.set("sort", sort);
    if (myClubsActive) parameters.set("my_clubs", "true");
    return "/events?" + parameters.toString();
  }, [myClubsActive, query, sort]);
  const events = useApiResource<PublicEvent[]>(eventsPath, token);

  const visibleEvents = useMemo(() => {
    const result = events.data ?? [];
    if (!myClubsActive) return result;
    return result.filter((event) => myClubOrganizationIds.has(event.org_id));
  }, [events.data, myClubOrganizationIds, myClubsActive]);

  return (
    <div className="stack discovery-stack">
      <header className="page-heading">
        <p className="eyebrow">Discover IntraSpot</p>
        <h1>Find your next campus event</h1>
        <p className="muted">Browse public events from PLM organizations.</p>
      </header>

      <section className="filters" aria-label="Event discovery filters">
        <label className="field">
          Search events or organizations
          <input
            type="search"
            value={query}
            maxLength={200}
            placeholder="Search by event or organization"
            onChange={(event) => setQuery(event.target.value)}
          />
        </label>
        <label className="field">
          Sort by
          <select aria-label="Sort by" value={sort} onChange={(event) => setSort(event.target.value as EventSort)}>
            <option value="upcoming">Upcoming</option>
            <option value="newest">Newest</option>
          </select>
        </label>
        {myClubsAvailable && (
          <button
            className="button button-secondary"
            type="button"
            aria-pressed={myClubsActive}
            onClick={() => setMyClubsSelected((selected) => !selected)}
          >
            <Icon name="filter" /> My Clubs
          </button>
        )}
      </section>

      {actor?.eligible && token && organizations.error && (
        <Feedback error={organizations.error} onRetry={organizations.reload} />
      )}

      <Feedback loading={events.loading} error={events.error} onRetry={events.reload}>
        {visibleEvents.length === 0 ? (
          <div className="panel empty-state">
            <h2>No events found</h2>
            <p className="muted">
              {query.trim() || myClubsActive
                ? "No public events match these filters."
                : "There are no public events to show right now."}
            </p>
          </div>
        ) : (
          <section className="feed" aria-label="Public events">
            {visibleEvents.map((event) => {
              return (
                <article className="event-card" key={event.id}>
                  <Link
                    className="event-card-link"
                    href={"/events?eventId=" + encodeURIComponent(event.id)}
                    aria-label={"View " + event.title + " by " + event.organization_name}
                  >
                    <header>
                      <div>
                        <p className="eyebrow">{event.organization_name}</p>
                        <h2>{event.title}</h2>
                      </div>
                    </header>
                    <EventArtwork event={event} />
                    {event.summary && <p className="event-summary">{event.summary}</p>}
                    <p className="muted">
                      {event.registration_mode === "approval" ? "Organizer approval required" : "Instant confirmation"}
                    </p>
                    <div className="event-facts">
                      <span>{formatDate(event.starts_at)} · {formatTime(event.starts_at)}</span>
                      <span>{event.venue_name}</span>
                    </div>
                    <div className="event-facts" role="group" aria-label="Event counts">
                      <span><span className="muted">Interested</span> <strong>{event.interest_count}</strong></span>
                      <span><span className="muted">Confirmed</span> <strong>{event.confirmed_count}</strong></span>
                      <span><span className="muted">Reserved</span> <strong>{event.reserved_count ?? "Unavailable"}</strong></span>
                      <span><span className="muted">Remaining</span> <strong>{event.remaining_spots}</strong></span>
                    </div>
                    <span className="text-action">View details <span aria-hidden="true">↗</span></span>
                  </Link>
                  <EventSocialPreview eventId={event.id} />
                </article>
              );
            })}
          </section>
        )}
      </Feedback>
    </div>
  );
}
