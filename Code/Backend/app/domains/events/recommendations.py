"""SQL ranking and private match reasons for the event discovery feed."""

from collections.abc import Sequence
from datetime import datetime, timedelta

from sqlalchemy import and_, case, desc, extract, func, literal, or_, select, true

from app.core.discovery import WEEK_MINUTES, normalized_label, weekly_intervals
from app.db.models import now
from app.domains.events.models import Event


def normalized_profile_tags(tags: Sequence[str] | None) -> set[str]:
    return {
        normalized
        for tag in tags or ()
        if isinstance(tag, str) and (normalized := normalized_label(tag))
    }


def _merge_ranges(ranges: Sequence[tuple[int, int]]) -> list[tuple[int, int]]:
    merged: list[tuple[int, int]] = []
    for start, end in sorted(ranges):
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(end, merged[-1][1]))
        else:
            merged.append((start, end))
    return merged


def whole_event_availability_score(windows: Sequence[dict]):
    """Return a SQL integer score after strict validation and weekly wrap merging."""
    intervals = weekly_intervals(windows)
    if not intervals:
        return literal(0)
    if intervals == [(0, WEEK_MINUTES)]:
        return literal(1)

    repeated = _merge_ranges(
        intervals + [(start + WEEK_MINUTES, end + WEEK_MINUTES) for start, end in intervals]
    )
    local_start = func.timezone("Asia/Manila", Event.starts_at)
    start_week_minute = (
        (extract("isodow", local_start) - 1) * 1440
        + extract("hour", local_start) * 60
        + extract("minute", local_start)
        + extract("second", local_start) / 60
    )
    duration_minutes = extract("epoch", Event.ends_at - Event.starts_at) / 60
    fits = or_(
        *(
            and_(
                start_week_minute >= start,
                start_week_minute + duration_minutes <= end,
            )
            for start, end in repeated
        )
    )
    return case(
        (and_(duration_minutes <= WEEK_MINUTES, fits), 1),
        else_=0,
    )


def for_you_statement(
    statement,
    *,
    active_clubs: Sequence[str],
    profile_tags: set[str],
    coarse_area: str | None,
    availability: Sequence[dict],
    request_now: datetime | None = None,
):
    request_now = request_now or now()
    club_score = (
        case((Event.org_id.in_(active_clubs), 1), else_=0)
        if active_clubs
        else literal(0)
    )

    if profile_tags:
        event_tags = (
            func.jsonb_array_elements_text(Event.tags)
            .table_valued("tag")
            .render_derived()
            .lateral("event_tags")
        )
        interest_counts = (
            select(
                Event.id.label("event_id"),
                func.count(func.distinct(event_tags.c.tag)).label("matched_interest_count"),
            )
            .select_from(Event)
            .join(event_tags, true())
            .where(event_tags.c.tag.in_(sorted(profile_tags)))
            .group_by(Event.id)
            .subquery()
        )
        statement = statement.outerjoin(interest_counts, interest_counts.c.event_id == Event.id)
        interest_score = func.coalesce(interest_counts.c.matched_interest_count, 0)
    else:
        interest_score = literal(0)

    area_score = (
        case((Event.coarse_area == normalized_label(coarse_area), 1), else_=0)
        if coarse_area
        else literal(0)
    )
    availability_score = whole_event_availability_score(availability)
    flash_score = (
        case(
            (
                and_(
                    Event.status == "published",
                    Event.event_type == "flash",
                    Event.coarse_area == normalized_label(coarse_area),
                    Event.published_at.is_not(None),
                    Event.published_at <= request_now,
                    Event.published_at + timedelta(hours=3) > request_now,
                    Event.starts_at > request_now,
                ),
                1,
            ),
            else_=0,
        )
        if coarse_area and normalized_label(coarse_area)
        else literal(0)
    )

    return (
        statement.add_columns(
            club_score.label("recommendation_club"),
            interest_score.label("recommendation_interests"),
            area_score.label("recommendation_area"),
            availability_score.label("recommendation_availability"),
            flash_score.label("recommendation_flash"),
        )
        .order_by(
            desc(club_score),
            desc(flash_score),
            desc(interest_score),
            desc(area_score),
            desc(availability_score),
            Event.starts_at.asc().nulls_last(),
            Event.id.asc(),
        )
    )


def matched_reason_codes(
    club_score: int,
    interest_count: int,
    area_score: int,
    availability_score: int,
    flash_score: int = 0,
) -> list[str]:
    reasons = []
    if club_score:
        reasons.append("club")
    if flash_score:
        reasons.append("flash")
    if interest_count:
        reasons.append("interests")
    if area_score:
        reasons.append("area")
    if availability_score:
        reasons.append("availability")
    return reasons
