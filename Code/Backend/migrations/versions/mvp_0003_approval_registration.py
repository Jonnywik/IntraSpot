"""Expand local registration review and reconfirmation state without rewriting outcomes.

Revision ID: mvp_0003
Revises: mvp_0002
"""
from alembic import op
import sqlalchemy as sa

revision = 'mvp_0003'
down_revision = 'mvp_0002'
branch_labels = None
depends_on = None

ACTIVE = "status IN ('confirmed', 'waitlisted', 'pending', 'reconfirmation_required')"


def upgrade() -> None:
    op.add_column('events', sa.Column('review_window_minutes', sa.Integer(), nullable=True))
    op.add_column('events', sa.Column('material_revision', sa.Integer(), server_default='0', nullable=False))
    op.drop_constraint('ck_events_registration_mode', 'events', type_='check')
    op.create_check_constraint('ck_events_registration_mode', 'events', "registration_mode IN ('instant', 'approval')")
    op.add_column('registration_receipts', sa.Column('persona_shared', sa.Boolean(), server_default=sa.text('false'), nullable=False))
    op.alter_column('registrations', 'status', existing_type=sa.String(16), type_=sa.String(32))
    for name in ('review_deadline', 'reconfirm_deadline'):
        op.add_column('registrations', sa.Column(name, sa.DateTime(timezone=True), nullable=True))
    op.add_column('registrations', sa.Column('review_stage', sa.SmallInteger(), nullable=True))
    for name in ('reviewer_id', 'first_reviewer_id'):
        op.add_column('registrations', sa.Column(name, sa.String(36), nullable=True))
        op.create_foreign_key(f'fk_registrations_{name}', 'registrations', 'users', [name], ['id'])
    op.add_column('registrations', sa.Column('timeout_count', sa.Integer(), server_default='0', nullable=False))
    for name in ('from_waitlist', 'persona_shared'):
        op.add_column('registrations', sa.Column(name, sa.Boolean(), server_default=sa.text('false'), nullable=False))
    op.add_column('registrations', sa.Column('reconfirm_revision', sa.Integer(), nullable=True))
    op.drop_constraint('ck_registrations_status', 'registrations', type_='check')
    op.create_check_constraint('ck_registrations_status', 'registrations',
                               "status IN ('confirmed', 'waitlisted', 'pending', 'reconfirmation_required', 'cancelled', 'rejected')")
    op.create_check_constraint('ck_registrations_review_stage', 'registrations', 'review_stage IS NULL OR review_stage IN (0, 1, 2)')
    op.create_check_constraint('ck_registrations_timeout_count_nonnegative', 'registrations', 'timeout_count >= 0')
    op.create_check_constraint('ck_registrations_reconfirm_revision_positive', 'registrations', 'reconfirm_revision IS NULL OR reconfirm_revision > 0')
    op.drop_index('uq_registrations_active_user_event', table_name='registrations')
    op.create_index('uq_registrations_active_user_event', 'registrations', ['user_id', 'event_id'], unique=True, postgresql_where=sa.text(ACTIVE))
    op.create_index('ix_registrations_pending_deadline', 'registrations', ['review_deadline', 'event_id'],
                    postgresql_where=sa.text("status = 'pending' AND review_deadline IS NOT NULL"))
    op.create_index('ix_registrations_reconfirmation_deadline', 'registrations', ['reconfirm_deadline', 'event_id'],
                    postgresql_where=sa.text("status = 'reconfirmation_required' AND reconfirm_deadline IS NOT NULL"))
    op.alter_column('notifications', 'registration_id', existing_type=sa.String(36), nullable=True)


def downgrade() -> None:
    # Refuse a lossy rollback; never rewrite approval history into instant outcomes.
    connection = op.get_bind()
    used = connection.scalar(sa.text("""
        SELECT EXISTS(SELECT 1 FROM events WHERE registration_mode != 'instant' OR material_revision != 0 OR review_window_minutes IS NOT NULL)
        OR EXISTS(SELECT 1 FROM registrations WHERE status NOT IN ('confirmed','waitlisted','cancelled')
            OR review_deadline IS NOT NULL OR review_stage IS NOT NULL OR reviewer_id IS NOT NULL
            OR first_reviewer_id IS NOT NULL OR timeout_count != 0 OR from_waitlist OR persona_shared
            OR reconfirm_deadline IS NOT NULL OR reconfirm_revision IS NOT NULL)
        OR EXISTS(SELECT 1 FROM registration_receipts WHERE persona_shared)
        OR EXISTS(SELECT 1 FROM notifications WHERE registration_id IS NULL OR kind != 'waitlist_promoted')
    """))
    if used:
        raise RuntimeError('Sprint 6 data exists; preserve a backup and resolve it before rollback. No rows were changed.')
    op.alter_column('notifications', 'registration_id', existing_type=sa.String(36), nullable=False)
    for name in ('ix_registrations_pending_deadline', 'ix_registrations_reconfirmation_deadline', 'uq_registrations_active_user_event'):
        op.drop_index(name, table_name='registrations')
    op.create_index('uq_registrations_active_user_event', 'registrations', ['user_id', 'event_id'], unique=True,
                    postgresql_where=sa.text("status IN ('confirmed', 'waitlisted')"))
    for name in ('ck_registrations_status', 'ck_registrations_review_stage', 'ck_registrations_timeout_count_nonnegative', 'ck_registrations_reconfirm_revision_positive'):
        op.drop_constraint(name, 'registrations', type_='check')
    op.create_check_constraint('ck_registrations_status', 'registrations', "status IN ('confirmed', 'waitlisted', 'cancelled')")
    for name in ('reviewer_id', 'first_reviewer_id'):
        op.drop_constraint(f'fk_registrations_{name}', 'registrations', type_='foreignkey')
    for name in ('review_deadline', 'review_stage', 'reviewer_id', 'first_reviewer_id', 'timeout_count', 'from_waitlist', 'persona_shared', 'reconfirm_deadline', 'reconfirm_revision'):
        op.drop_column('registrations', name)
    op.alter_column('registrations', 'status', existing_type=sa.String(32), type_=sa.String(16))
    op.drop_column('registration_receipts', 'persona_shared')
    op.drop_constraint('ck_events_registration_mode', 'events', type_='check')
    op.create_check_constraint('ck_events_registration_mode', 'events', "registration_mode = 'instant'")
    op.drop_column('events', 'review_window_minutes')
    op.drop_column('events', 'material_revision')
