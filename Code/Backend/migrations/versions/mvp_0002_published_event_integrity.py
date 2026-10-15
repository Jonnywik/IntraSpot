"""Require complete published events; incomplete drafts remain valid.

Revision ID: mvp_0002
Revises: mvp_0001
"""
from alembic import op

revision = 'mvp_0002'
down_revision = 'mvp_0001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Validation fails and rolls back if an existing published row is invalid.
    # Do not rewrite, delete, or silently unpublish existing events.
    op.create_check_constraint(
        'ck_events_published_complete', 'events',
        "status != 'published' OR (title IS NOT NULL AND description IS NOT NULL "
        "AND starts_at IS NOT NULL AND ends_at IS NOT NULL AND ends_at > starts_at "
        "AND venue_name IS NOT NULL AND venue_address IS NOT NULL "
        "AND capacity IS NOT NULL AND capacity > 0 AND banner_key IS NOT NULL)",
    )


def downgrade() -> None:
    op.drop_constraint('ck_events_published_complete', 'events', type_='check')
