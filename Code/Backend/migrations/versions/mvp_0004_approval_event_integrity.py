"""Enforce approval settings after the additive Sprint 6 schema expansion.

Revision ID: mvp_0004
Revises: mvp_0003
"""
from alembic import op

revision = 'mvp_0004'
down_revision = 'mvp_0003'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Some local scratch runs applied these checks during the draft mvp_0003.
    # Normalize their definitions atomically; never rewrite existing event rows.
    for name in ('ck_events_review_window_range', 'ck_events_published_review_settings', 'ck_events_material_revision_nonnegative'):
        op.execute(f'ALTER TABLE events DROP CONSTRAINT IF EXISTS {name}')
    op.create_check_constraint('ck_events_review_window_range', 'events',
                               'review_window_minutes IS NULL OR review_window_minutes BETWEEN 15 AND 2880')
    op.create_check_constraint('ck_events_published_review_settings', 'events',
        "status != 'published' OR (registration_mode = 'instant' AND review_window_minutes IS NULL) OR "
        "(registration_mode = 'approval' AND review_window_minutes IS NOT NULL AND review_window_minutes BETWEEN 15 AND 2880)")
    op.create_check_constraint('ck_events_material_revision_nonnegative', 'events', 'material_revision >= 0')


def downgrade() -> None:
    for name in ('ck_events_review_window_range', 'ck_events_published_review_settings', 'ck_events_material_revision_nonnegative'):
        op.drop_constraint(name, 'events', type_='check')
