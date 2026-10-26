"""Bounded, in-process maintenance for durable deadline work."""
from __future__ import annotations

import asyncio
import threading
import time
from contextlib import asynccontextmanager, suppress
from dataclasses import dataclass

from sqlalchemy import func, select, text, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.core.config import get_settings
from app.db.models import now
from app.db.session import engine, session_factory
from app.domains.events.models import Event
from app.domains.organizations.models import Organization
from app.operations_models import MaintenanceState

_STATE_NAME = "deadline-maintenance"
_MAX_TARGETS = 100
_MAX_SECONDS = 20.0
_MAX_STATEMENT_MS = 2_500
_MAX_LOCK_MS = 500
_RETRY_SECONDS = (30, 60, 120, 300)
_monotonic = time.monotonic

# Retry timing is process-local; the cursor and sanitized error code survive restarts.
_retry_lock = threading.Lock()
_retries: dict[tuple[str, str], tuple[int, float]] = {}
_pass_retry: tuple[int, float] = (0, 0.0)


@dataclass(frozen=True)
class _Target:
    scope: str
    target_id: str

    @property
    def token(self) -> str:
        return f"{self.scope}:{self.target_id}"

    @property
    def lock_name(self) -> str:
        return f"intraspot.maintenance.{self.scope}.{self.target_id}"


class _BudgetExpired(Exception):
    pass


class _CursorMoved(Exception):
    pass


class _PoolBusy(Exception):
    pass


def _session(factory):
    pool = engine().pool
    if hasattr(pool, "checkedout") and hasattr(pool, "size") and pool.checkedout() >= pool.size():
        raise _PoolBusy
    return factory()


def _decode_cursor(cursor: str | None) -> tuple[str | None, str | None, str]:
    if not cursor:
        return None, None, "e"
    try:
        event_cursor, org_cursor, next_scope = cursor.split(",")
        if not event_cursor.startswith("e") or not org_cursor.startswith("o") or next_scope not in {"e", "o"}:
            raise ValueError
        return event_cursor[1:] or None, org_cursor[1:] or None, next_scope
    except ValueError:
        return None, None, "e"


def _encode_cursor(event_cursor: str | None, org_cursor: str | None, next_scope: str) -> str:
    cursor = f"e{event_cursor or ''},o{org_cursor or ''},{next_scope}"
    if len(cursor) > 80:
        raise ValueError("Maintenance cursor exceeds its database column.")
    return cursor


def _cursor_after(cursor: str | None, target: _Target) -> str:
    event_cursor, org_cursor, _ = _decode_cursor(cursor)
    if target.scope == "e":
        return _encode_cursor(target.target_id, org_cursor, "o")
    return _encode_cursor(event_cursor, target.target_id, "e")


def _set_timeouts(db, deadline: float) -> None:
    remaining_ms = int((deadline - _monotonic()) * 1000)
    if remaining_ms <= 0:
        raise _BudgetExpired
    statement_ms = max(1, min(_MAX_STATEMENT_MS, remaining_ms))
    lock_ms = max(1, min(_MAX_LOCK_MS, statement_ms))
    db.execute(text("SELECT set_config('lock_timeout', :value, true)"), {"value": f"{lock_ms}ms"})
    db.execute(text("SELECT set_config('statement_timeout', :value, true)"), {"value": f"{statement_ms}ms"})
    db.execute(text("SELECT set_config('transaction_timeout', :value, true)"), {"value": f"{remaining_ms}ms"})


def _first_id(db, scope: str, after: str | None) -> str | None:
    model = Event if scope == "e" else Organization
    query = select(model.id)
    if scope == "e":
        query = query.where(Event.status == "published")
    if after is not None:
        candidate = db.scalar(query.where(model.id > after).order_by(model.id).limit(1))
        if candidate is not None:
            return candidate
    return db.scalar(query.order_by(model.id).limit(1))


def _next_target(factory, cursor: str | None, deadline: float) -> _Target | None:
    event_cursor, org_cursor, next_scope = _decode_cursor(cursor)
    with _session(factory) as db, db.begin():
        _set_timeouts(db, deadline)
        for scope in (next_scope, "o" if next_scope == "e" else "e"):
            after = event_cursor if scope == "e" else org_cursor
            target_id = _first_id(db, scope, after)
            if target_id is not None:
                return _Target(scope, target_id)
    return None


def _move_cursor(
    db,
    expected: str | None,
    following: str,
    *,
    processed: bool = False,
    error_code: str | None = None,
) -> None:
    conditions = [MaintenanceState.name == _STATE_NAME]
    conditions.append(
        MaintenanceState.cursor.is_(None) if expected is None else MaintenanceState.cursor == expected
    )
    values = {"cursor": following}
    if processed:
        values["processed_count"] = MaintenanceState.processed_count + 1
    if error_code is not None:
        values["last_error_code"] = error_code
    result = db.execute(update(MaintenanceState).where(*conditions).values(**values))
    if result.rowcount != 1:
        raise _CursorMoved


def _process_target(factory, target: _Target, cursor: str | None, following: str, deadline: float) -> tuple[str, int]:
    receipts = 0
    with _session(factory) as db, db.begin():
        _set_timeouts(db, deadline)
        locked = db.scalar(select(func.pg_try_advisory_xact_lock(func.hashtextextended(target.lock_name, 0))))
        if not locked:
            return "busy", 0
        _set_timeouts(db, deadline)
        if target.scope == "e":
            org_id = db.scalar(select(Event.org_id).where(Event.id == target.target_id))
            if org_id is not None:
                _set_timeouts(db, deadline)
                organization = db.scalar(
                    select(Organization).where(Organization.id == org_id).with_for_update()
                )
                if organization is not None:
                    _set_timeouts(db, deadline)
                    event = db.scalar(
                        select(Event).where(Event.id == target.target_id, Event.org_id == org_id).with_for_update()
                        .execution_options(populate_existing=True)
                    )
                else:
                    event = None
            else:
                event = None
            if event is not None:
                from app.domains.chat.service import purge_event_chat_locked
                from app.domains.moderation.service import catch_up_reports_locked
                from app.domains.registrations.service import DRAIN_BATCH_SIZE, _drain_event_locked, catch_up_locked

                boundary = now()
                _set_timeouts(db, deadline)
                receipts = _drain_event_locked(db, event, limit=DRAIN_BATCH_SIZE)
                if receipts < DRAIN_BATCH_SIZE:
                    _set_timeouts(db, deadline)
                    catch_up_locked(db, event, boundary)
                _set_timeouts(db, deadline)
                catch_up_reports_locked(db, event, boundary)
                _set_timeouts(db, deadline)
                purge_event_chat_locked(db, event, boundary)
        else:
            organization = db.scalar(
                select(Organization).where(Organization.id == target.target_id).with_for_update()
                .execution_options(populate_existing=True)
            )
            if organization is not None:
                from app.domains.announcements.report_service import catch_up_announcement_reports_locked
                from app.domains.eventsafety.service import sweep_expired_reports, sweep_expired_suspensions
                from app.domains.memberships.applications import catch_up_invitations_locked

                boundary = now()
                _set_timeouts(db, deadline)
                sweep_expired_suspensions(db, org_id=organization.id, at=boundary)
                _set_timeouts(db, deadline)
                sweep_expired_reports(db, org_id=organization.id, at=boundary)
                _set_timeouts(db, deadline)
                catch_up_invitations_locked(db, organization.id, boundary)
                _set_timeouts(db, deadline)
                catch_up_announcement_reports_locked(db, organization.id, boundary)
        _set_timeouts(db, deadline)
        _move_cursor(db, cursor, following, processed=True)
    return "processed", receipts


def _advance_after_failure(factory, cursor: str | None, following: str, deadline: float) -> None:
    with _session(factory) as db, db.begin():
        _set_timeouts(db, deadline)
        _move_cursor(db, cursor, following, error_code="maintenance_target_failed")


def _retry_due(target: _Target, current: float) -> bool:
    with _retry_lock:
        entry = _retries.get((target.scope, target.target_id))
    return entry is None or current >= entry[1]


def _schedule_retry(target: _Target, current: float) -> None:
    key = (target.scope, target.target_id)
    with _retry_lock:
        attempt = _retries.get(key, (0, 0.0))[0] + 1
        delay = _RETRY_SECONDS[min(attempt - 1, len(_RETRY_SECONDS) - 1)]
        _retries[key] = (attempt, current + delay)


def _clear_retry(target: _Target) -> None:
    with _retry_lock:
        _retries.pop((target.scope, target.target_id), None)


def _pass_due(current: float) -> bool:
    with _retry_lock:
        return current >= _pass_retry[1]


def _schedule_pass_retry(current: float) -> None:
    global _pass_retry
    with _retry_lock:
        attempt = _pass_retry[0] + 1
        delay = _RETRY_SECONDS[min(attempt - 1, len(_RETRY_SECONDS) - 1)]
        _pass_retry = (attempt, current + delay)


def _clear_pass_retry() -> None:
    global _pass_retry
    with _retry_lock:
        _pass_retry = (0, 0.0)


def _start_pass(factory, deadline: float) -> tuple[str | None, object]:
    started_at = now()
    with _session(factory) as db, db.begin():
        _set_timeouts(db, deadline)
        db.execute(pg_insert(MaintenanceState).values(name=_STATE_NAME).on_conflict_do_nothing(
            index_elements=[MaintenanceState.name]
        ))
        db.execute(update(MaintenanceState).where(MaintenanceState.name == _STATE_NAME).values(
            last_started_at=started_at, processed_count=0, duration_ms=0,
        ))
        state = db.scalar(
            select(MaintenanceState).where(MaintenanceState.name == _STATE_NAME)
            .execution_options(populate_existing=True)
        )
        return state.cursor, started_at


def _finish_pass(factory, started_at, duration_ms: int, summary: dict, deadline: float) -> None:
    if _monotonic() >= deadline:
        return
    with _session(factory) as db, db.begin():
        _set_timeouts(db, deadline)
        values = {"duration_ms": duration_ms}
        if summary["error_code"]:
            values["last_error_code"] = summary["error_code"]
        elif not summary["skipped_busy"] and not summary["skipped_backoff"]:
            values.update(last_error_code=None, last_success_at=now())
        db.execute(update(MaintenanceState).where(
            MaintenanceState.name == _STATE_NAME,
            MaintenanceState.last_started_at == started_at,
        ).values(**values))


def run_pass() -> dict:
    """Run one fair, bounded pass and return counts without exception details."""
    started = _monotonic()
    if not _pass_due(started):
        return {
            "status": "backoff", "processed": 0, "events_processed": 0, "organizations_processed": 0,
            "receipts_processed": 0, "failed": 0, "skipped_busy": 0, "skipped_backoff": 0,
            "error_code": "maintenance_unavailable", "duration_ms": 0,
        }
    # Leave two seconds for connection establishment and final bookkeeping.
    finish_deadline = started + _MAX_SECONDS
    deadline = started + max(0.1, _MAX_SECONDS - 2.0)
    summary = {
        "status": "ok", "processed": 0, "events_processed": 0, "organizations_processed": 0,
        "receipts_processed": 0, "failed": 0, "skipped_busy": 0, "skipped_backoff": 0,
        "error_code": None, "duration_ms": 0,
    }
    factory = session_factory()
    state_started_at = None
    try:
        cursor, state_started_at = _start_pass(factory, deadline)
        visited: set[str] = set()
        for _ in range(_MAX_TARGETS):
            if _monotonic() >= deadline:
                break
            target = _next_target(factory, cursor, deadline)
            if target is None or target.token in visited:
                break
            visited.add(target.token)
            following = _cursor_after(cursor, target)
            current = _monotonic()
            if not _retry_due(target, current):
                try:
                    with _session(factory) as db, db.begin():
                        _set_timeouts(db, deadline)
                        _move_cursor(db, cursor, following)
                except (_BudgetExpired, _CursorMoved):
                    break
                cursor = following
                summary["skipped_backoff"] += 1
                continue
            try:
                result, receipts = _process_target(factory, target, cursor, following, deadline)
            except _BudgetExpired:
                _advance_after_failure(factory, cursor, following, finish_deadline)
                _schedule_retry(target, _monotonic())
                summary.update(status='partial', error_code='maintenance_budget_exhausted')
                summary['failed'] += 1
                break
            except _PoolBusy:
                summary.update(status="unavailable", error_code="maintenance_pool_busy")
                break
            except _CursorMoved:
                summary["skipped_busy"] += 1
                break
            except Exception:
                if _monotonic() >= deadline:
                    _advance_after_failure(factory, cursor, following, finish_deadline)
                    _schedule_retry(target, _monotonic())
                    summary.update(status='partial', error_code='maintenance_budget_exhausted')
                    summary['failed'] += 1
                    break
                try:
                    _advance_after_failure(factory, cursor, following, deadline)
                except (_BudgetExpired, _CursorMoved):
                    break
                _schedule_retry(target, _monotonic())
                cursor = following
                summary["failed"] += 1
                summary["error_code"] = "maintenance_target_failed"
                continue
            if result == "busy":
                summary["skipped_busy"] += 1
                break
            cursor = following
            _clear_retry(target)
            summary["processed"] += 1
            summary["receipts_processed"] += receipts
            if target.scope == "e":
                summary["events_processed"] += 1
            else:
                summary["organizations_processed"] += 1
        if summary["status"] == "ok" and (summary["failed"] or summary["skipped_busy"] or summary["skipped_backoff"]):
            summary["status"] = "partial"
        summary["duration_ms"] = max(0, int((_monotonic() - started) * 1000))
        _finish_pass(factory, state_started_at, summary["duration_ms"], summary, finish_deadline)
        if summary["status"] == "unavailable":
            _schedule_pass_retry(_monotonic())
        else:
            _clear_pass_retry()
    except Exception:
        summary.update(status="unavailable", error_code="maintenance_unavailable")
        summary["duration_ms"] = max(0, int((_monotonic() - started) * 1000))
        _schedule_pass_retry(_monotonic())
    return summary


async def _run_scheduler() -> None:
    interval = get_settings().maintenance_interval_seconds
    while True:
        await asyncio.sleep(interval)
        await asyncio.to_thread(run_pass)


@asynccontextmanager
async def lifespan(app):
    if get_settings().maintenance_enabled:
        await asyncio.to_thread(run_pass)
        task = asyncio.create_task(_run_scheduler())
        try:
            yield
        finally:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task
    else:
        yield
