"""Expand existing event types and add a private default-visible feed preference."""
from alembic import op
import sqlalchemy as sa

revision = "mvp_0009"
down_revision = "mvp_0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("ck_events_event_type", "events", type_="check")
    op.create_check_constraint("ck_events_event_type", "events", "event_type IN ('scheduled', 'flash')")
    op.create_check_constraint(
        "ck_events_flash_instant", "events",
        "event_type != 'flash' OR (registration_mode = 'instant' AND review_window_minutes IS NULL)",
    )
    op.create_check_constraint(
        "ck_events_flash_published_window", "events",
        "status != 'published' OR event_type != 'flash' OR "
        "(starts_at > published_at AND starts_at <= published_at + INTERVAL '24 hours')",
    )
    op.add_column("user_preferences", sa.Column(
        "show_flash", sa.Boolean(), nullable=False, server_default=sa.text("true"),
    ))


def downgrade() -> None:
    if op.get_bind().scalar(sa.text(
        "SELECT EXISTS (SELECT 1 FROM events WHERE event_type = 'flash') OR "
        "EXISTS (SELECT 1 FROM user_preferences WHERE show_flash = false)"
    )):
        raise RuntimeError("Sprint 13 Flash data or hidden-Flash preferences exist; archive before deliberate rollback.")
    op.drop_column("user_preferences", "show_flash")
    op.drop_constraint("ck_events_flash_published_window", "events", type_="check")
    op.drop_constraint("ck_events_flash_instant", "events", type_="check")
    op.drop_constraint("ck_events_event_type", "events", type_="check")
    op.create_check_constraint("ck_events_event_type", "events", "event_type = 'scheduled'")
