"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { EventArtwork } from "@/app/event-artwork";
import { Feedback } from "@/components/feedback";
import { Icon } from "@/components/icon";
import { useApiResource } from "@/lib/use-api-resource";
import { useSession } from "@/lib/session";
import { useT } from "@/lib/i18n";
import { usePreferences } from "@/lib/preferences";
import { formatDate, formatTime } from "@/lib/date";
import type { MyOrganizations, PublicEvent } from "@/lib/types";
import { EventSocialPreview } from "@/features/communication/EventSocial";
import { FeaturedBadge } from "@/features/featured/FeaturedBadge";
import { HeritageDecoration } from "@/components/heritage-decoration";
import styles from "./attendee-events.module.css";

const EVENT_SORTS = ["for_you", "upcoming", "newest"] as const;
type EventSort = (typeof EVENT_SORTS)[number];
type RecommendationReason = "club" | "flash" | "interests" | "area" | "availability";

const RECOMMENDATION_REASONS: readonly RecommendationReason[] = [
  "club",
  "flash",
  "interests",
  "area",
  "availability",
];

const RECOMMENDATION_LABELS: Record<RecommendationReason, string> = {
  club: "From one of your clubs",
  flash: "Flash priority in your area",
  interests: "Matches your interests",
  area: "Matches your broad area",
  availability: "Fits your free time",
};

function isEventSort(value: string): value is EventSort {
  return EVENT_SORTS.some((sort) => sort === value);
}

function isRecommendationReason(value: unknown): value is RecommendationReason {
  return RECOMMENDATION_REASONS.some((reason) => reason === value);
}

function recommendationReasons(event: PublicEvent): RecommendationReason[] {
  if (!("recommendation_reasons" in event) || !Array.isArray(event.recommendation_reasons)) return [];
  const supplied: readonly unknown[] = event.recommendation_reasons;
  const matched = new Set(supplied.filter(isRecommendationReason));
  return RECOMMENDATION_REASONS.filter((reason) => matched.has(reason));
}

export function DiscoverFeed() {
  const { actor, token } = useSession();
  const t = useT();
  const {
    preferences,
    setPreference,
    ready: preferencesReady,
    status: preferencesStatus,
    error: preferencesError,
    retry: retryPreferences,
  } = usePreferences();
  const [query, setQuery] = useState("");
  const [sortSelection, setSortSelection] = useState<{ token: string | null; sort: EventSort }>({
    token: null,
    sort: "upcoming",
  });
  const [myClubsSelected, setMyClubsSelected] = useState(false);
  const defaultSort: EventSort = token ? "for_you" : "upcoming";
  const sort = sortSelection.token === token ? sortSelection.sort : defaultSort;

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
    if (!preferences.show_flash) parameters.set("include_flash", "false");
    return "/events?" + parameters.toString();
  }, [myClubsActive, preferences.show_flash, query, sort]);
  const pollInterval = token && sort === "for_you" ? 30_000 : 0;
  const events = useApiResource<PublicEvent[]>(eventsPath, token, pollInterval);

  const visibleEvents = useMemo(() => {
    const result = events.data ?? [];
    if (!myClubsActive) return result;
    return result.filter((event) => myClubOrganizationIds.has(event.org_id));
  }, [events.data, myClubOrganizationIds, myClubsActive]);

  return (
    <div className={`stack discovery-stack ${styles.discoverFeed} ${styles.compactStack}`}>
      <header className={`page-heading discovery-heading ${styles.discoveryHeading}`} aria-labelledby="discovery-title">
        <p className="eyebrow">{t("Discover IntraSpot")}</p>
        <h1 id="discovery-title">{t("Find your next campus event")}</h1>
        <p className="muted">{t("Browse public events from PLM organizations.")}</p>
        <HeritageDecoration />
      </header>

      <section className={`filters ${styles.discoveryFilters}`} aria-label={t("Event discovery filters")}>
        <div className={styles.searchField}>
          <label className={`field ${styles.searchLabel}`} htmlFor="event-search">{t("Search events or organizations")}</label>
          <div className={styles.searchInputRow}>
            <input
              id="event-search"
              type="search"
              value={query}
              maxLength={200}
              placeholder={t("Search by event or organization")}
              aria-describedby="event-search-help"
              onChange={(event) => setQuery(event.target.value)}
            />
            {query && (
              <button
                className={styles.clearSearch}
                type="button"
                aria-label={t("Clear search")}
                onClick={() => setQuery("")}
              >
                {t("Clear")}
              </button>
            )}
          </div>
          <span className={styles.searchHint} id="event-search-help">
            {t("Search event titles and organization names.")}
          </span>
        </div>
        <label className={`field ${styles.sortField}`}>
          <span className={styles.sortLabel}>{t("Sort by")}</span>
          <select
            aria-label={t("Sort by")}
            value={sort}
            onChange={(event) => {
              const value = event.currentTarget.value;
              if (isEventSort(value)) setSortSelection({ token, sort: value });
            }}
          >
            {token && <option value="for_you">{t("For You")}</option>}
            <option value="upcoming">{t("Upcoming")}</option>
            <option value="newest">{t("Newest")}</option>
          </select>
        </label>
        {myClubsAvailable && (
          <button
            className={`button button-secondary ${styles.myClubsToggle}`}
            type="button"
            aria-pressed={myClubsActive}
            aria-controls="public-event-results"
            onClick={() => setMyClubsSelected((selected) => !selected)}
          >
            <Icon name="filter" /> {t("My Clubs")}
          </button>
        )}
        <label className={styles.flashToggle}>
          <input
            type="checkbox"
            role="switch"
            aria-label={t("Show Flash events")}
            aria-controls="public-event-results"
            aria-describedby={preferencesStatus === "error" && preferencesError ? "flash-preference-error" : undefined}
            checked={preferences.show_flash}
            disabled={!preferencesReady}
            onChange={(event) => setPreference("show_flash", event.currentTarget.checked)}
          />
          <span>{t("Show Flash events")}</span>
        </label>
        {preferencesStatus === "saving" && (
          <p className={styles.flashPreferenceStatus} role="status" aria-live="polite">{t("Saving…")}</p>
        )}
        {preferencesStatus === "error" && preferencesError && (
          <div id="flash-preference-error" className={styles.flashPreferenceError} role="alert">
            <p>{t(preferencesError)}</p>
            <button className="button button-secondary" type="button" onClick={retryPreferences}>
              {t("Retry")}
            </button>
          </div>
        )}
        {token && sort === "for_you" && (
          <details className={styles.rankingHint}>
            <summary>{t("How For You works")}</summary>
            <p>{t("Your clubs come first, then active Flash events in your area, followed by distinct tag matches, your broad area, and full-event free-time fit.")}</p>
            <p>{t("Tags and area names match exactly, ignoring capitalization and extra spaces.")}</p>
            <Link href="/settings" className="text-action">{t("Manage optional preferences in Settings")}</Link>
          </details>
        )}
        {Array.isArray(events.data) && !events.loading && !events.error && (
          <p className={styles.resultsCount} role="status" aria-live="polite" aria-atomic="true">
            {t("Events shown: {count}", { count: visibleEvents.length })}
          </p>
        )}
      </section>

      {actor?.eligible && token && organizations.error && (
        <Feedback error={organizations.error} onRetry={organizations.reload} />
      )}

      <div id="public-event-results">
        <Feedback loading={events.loading} error={events.error} onRetry={events.reload}>
          {visibleEvents.length === 0 ? (
            <div className={`panel empty-state ${styles.emptyState}`}>
              <h2>{t("No events found")}</h2>
              <p className="muted">
                {query.trim() || myClubsActive || !preferences.show_flash
                  ? t("No public events match these filters.")
                  : t("There are no public events to show right now.")}
              </p>
            </div>
          ) : (
            <section className={`feed ${styles.eventList}`} aria-label={t("Public events")}>
              {visibleEvents.map((event, index) => {
                const reasons = token && sort === "for_you" ? recommendationReasons(event) : [];
                return (
                  <article className={`event-card ${styles.eventCard}`} key={event.id}>
                    <Link
                      className="event-card-link"
                      href={"/events?eventId=" + encodeURIComponent(event.id)}
                      aria-label={t("View {event} by {organization}", {
                        event: event.title,
                        organization: event.organization_name,
                      })}
                    >
                      <header>
                        <div>
                          <p className="eyebrow">{event.organization_name}</p>
                          {event.event_type === "flash" && (
                            <span className={styles.eventTypeBadge}>{t("Flash event")}</span>
                          )}
                          {event.is_featured && <FeaturedBadge />}
                          <h2 id={`event-${event.id}-title`}>{event.title}</h2>
                        </div>
                      </header>
                      <EventArtwork event={event} priority={index === 0} />
                      {event.summary && <p className="event-summary">{event.summary}</p>}
                      {reasons.length > 0 && (
                        <ul className={styles.reasonChips} aria-label={t("Why this event appears")}>
                          {reasons.map((reason) => <li key={reason}>{t(RECOMMENDATION_LABELS[reason])}</li>)}
                        </ul>
                      )}
                      <p className={`muted ${styles.registrationMode}`}>
                        {event.registration_mode === "approval"
                          ? t("Organizer approval required")
                          : t("Instant confirmation")}
                      </p>
                      <div className={`event-facts ${styles.eventFacts}`}>
                        <span>{formatDate(event.starts_at, preferences.language)} · {formatTime(event.starts_at, preferences.language)}</span>
                        <span>{event.venue_name}</span>
                      </div>
                      <dl className={styles.eventCounts} aria-label={t("Event counts")}>
                        <div><dt>{t("Interested")}</dt><dd>{event.interest_count}</dd></div>
                        <div><dt>{t("Confirmed")}</dt><dd>{event.confirmed_count}</dd></div>
                        <div><dt>{t("Reserved")}</dt><dd>{event.reserved_count ?? t("Unavailable")}</dd></div>
                        <div><dt>{t("Remaining")}</dt><dd>{event.remaining_spots}</dd></div>
                      </dl>
                      <span className={`button ${styles.eventCardCta}`}>
                        {t("View event")} <span aria-hidden="true">↗</span>
                      </span>
                    </Link>
                    <EventSocialPreview eventId={event.id} />
                  </article>
                );
              })}
            </section>
          )}
        </Feedback>
      </div>
    </div>
  );
}
