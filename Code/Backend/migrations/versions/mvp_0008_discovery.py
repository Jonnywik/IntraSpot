"""Add optional event metadata and private discovery inputs without inference."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "mvp_0008"
down_revision = "mvp_0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("events", sa.Column("tags", postgresql.JSONB(), nullable=False,
                                       server_default=sa.text("'[]'::jsonb")))
    op.add_column("events", sa.Column("coarse_area", sa.String(80), nullable=True))
    op.create_check_constraint("ck_events_tags_array", "events",
                               "jsonb_typeof(tags) = 'array' AND jsonb_array_length(tags) <= 16")
    op.create_table(
        "user_discovery_preferences",
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), primary_key=True),
        sa.Column("coarse_area", sa.String(80), nullable=True),
        sa.Column("availability", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("jsonb_typeof(availability) = 'array' AND jsonb_array_length(availability) <= 28",
                           name="ck_discovery_availability_array"),
    )


def downgrade() -> None:
    connection = op.get_bind()
    has_data = connection.scalar(sa.text(
        "SELECT EXISTS (SELECT 1 FROM user_discovery_preferences) OR "
        "EXISTS (SELECT 1 FROM events WHERE tags != '[]'::jsonb OR coarse_area IS NOT NULL)"
    ))
    if has_data:
        raise RuntimeError("Sprint 12 discovery data exists; archive it before a deliberate rollback.")
    op.drop_table("user_discovery_preferences")
    op.drop_constraint("ck_events_tags_array", "events", type_="check")
    op.drop_column("events", "coarse_area")
    op.drop_column("events", "tags")
