from sqlalchemy import event as sa_event

from app.db.session import engine
from app.domains.registrations import service


def test_event_batches_lock_shared_users_in_id_order_not_receipt_order(
    make_event, make_user
):
    users = [make_user(), make_user()]
    user_ids = sorted(user.id for user in users)
    low_id, high_id = user_ids
    events = [make_event(capacity=1), make_event(capacity=1)]
    receipt_orders = {
        events[0].id: [high_id, low_id],
        events[1].id: [low_id, high_id],
    }

    for event_index, event in enumerate(events):
        for order, user_id in enumerate(receipt_orders[event.id], start=1):
            service.intake_registration(
                user_id, event.id, f"s4-lock-order-{event_index}-{order:02d}"
            )

    lock_queries = {event.id: [] for event in events}
    active_event_id = None

    def flatten_parameters(value):
        if isinstance(value, dict):
            for nested in value.values():
                yield from flatten_parameters(nested)
        elif isinstance(value, (list, tuple)):
            for nested in value:
                yield from flatten_parameters(nested)
        elif isinstance(value, str):
            yield value

    def capture_user_locks(conn, cursor, statement, parameters, context, executemany):
        normalized = " ".join(statement.lower().split())
        if "users" not in normalized or "for no key update" not in normalized:
            return
        matched_ids = list(
            dict.fromkeys(
                value
                for value in flatten_parameters(parameters)
                if value in user_ids
            )
        )
        if matched_ids:
            lock_queries[active_event_id].append(
                (matched_ids, "order by users.id" in normalized)
            )

    database_engine = engine()
    sa_event.listen(database_engine, "after_cursor_execute", capture_user_locks)
    try:
        for event in events:
            active_event_id = event.id
            service.drain_event(event.id)
    finally:
        sa_event.remove(database_engine, "after_cursor_execute", capture_user_locks)

    expected_order = user_ids
    for event in events:
        observed_order = []
        for locked_ids, ordered_by_user_id in lock_queries[event.id]:
            if len(locked_ids) > 1:
                assert ordered_by_user_id, "multi-user locks must order by User.id"
                locked_ids = sorted(locked_ids)
            observed_order.extend(locked_ids)
        observed_order = list(dict.fromkeys(observed_order))
        assert observed_order == expected_order, (
            f"event {event.id} locked shared users in {observed_order}; "
            f"expected stable order {expected_order}"
        )
        # Lock acquisition order must not become admission order.
        first_user, second_user = receipt_orders[event.id]
        first_state = next(row for row in service.list_my_registrations(first_user)
                           if row['event_id'] == event.id)
        second_state = next(row for row in service.list_my_registrations(second_user)
                            if row['event_id'] == event.id)
        assert first_state['status'] == 'confirmed'
        assert second_state['status'] == 'waitlisted'
        assert second_state['waitlist_position'] == 1
