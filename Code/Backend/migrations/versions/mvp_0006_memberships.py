"""Add local membership lifecycle and organization-scoped notification context.

Revision ID: mvp_0006
Revises: mvp_0005
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = 'mvp_0006'
down_revision = 'mvp_0005'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('membership_applications',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('org_id', sa.String(36), sa.ForeignKey('organizations.id'), nullable=False),
        sa.Column('user_id', sa.String(36), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('client_key', sa.String(36), nullable=False),
        sa.Column('persona_shared', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('status', sa.String(24), nullable=False, server_default='pending'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('resolved_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('decided_by', sa.String(36), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('reason', sa.String(32), nullable=True),
        sa.CheckConstraint("status IN ('pending', 'approved', 'rejected', 'withdrawn', 'superseded')", name='ck_membership_applications_status'),
        sa.CheckConstraint("reason IS NULL OR reason IN ('requirements_not_met', 'applications_closed', 'other')", name='ck_membership_applications_reason'),
        sa.UniqueConstraint('user_id', 'client_key', name='uq_membership_applications_user_client_key'),
    )
    op.create_index('uq_membership_applications_pending_org_user', 'membership_applications',
                    ['org_id', 'user_id'], unique=True, postgresql_where=sa.text("status = 'pending'"))
    op.create_index('ix_membership_applications_org_status_created', 'membership_applications', ['org_id', 'status', 'created_at'])
    op.create_table('membership_invitations',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('org_id', sa.String(36), sa.ForeignKey('organizations.id'), nullable=False),
        sa.Column('recipient_id', sa.String(36), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('sender_id', sa.String(36), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('client_key', sa.String(36), nullable=False),
        sa.Column('status', sa.String(24), nullable=False, server_default='pending'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('resolved_at', sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("status IN ('pending', 'accepted', 'declined', 'revoked', 'expired', 'superseded')", name='ck_membership_invitations_status'),
        sa.CheckConstraint('expires_at > created_at', name='ck_membership_invitations_expiry_after_creation'),
        sa.UniqueConstraint('sender_id', 'client_key', name='uq_membership_invitations_sender_client_key'),
    )
    op.create_index('uq_membership_invitations_pending_org_recipient', 'membership_invitations',
                    ['org_id', 'recipient_id'], unique=True, postgresql_where=sa.text("status = 'pending'"))
    op.create_index('ix_membership_invitations_status_expires', 'membership_invitations', ['status', 'expires_at'])
    op.create_table('membership_audits',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('org_id', sa.String(36), sa.ForeignKey('organizations.id'), nullable=False),
        sa.Column('actor_id', sa.String(36), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('user_id', sa.String(36), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('action', sa.String(40), nullable=False),
        sa.Column('old_role', sa.String(16), nullable=True),
        sa.Column('new_role', sa.String(16), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index('ix_membership_audits_org_created', 'membership_audits', ['org_id', 'created_at'])
    op.create_table('membership_operations',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('org_id', sa.String(36), sa.ForeignKey('organizations.id'), nullable=False),
        sa.Column('actor_id', sa.String(36), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('user_id', sa.String(36), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('action', sa.String(24), nullable=False),
        sa.Column('client_key', sa.String(36), nullable=False),
        sa.Column('payload_hash', sa.String(64), nullable=False),
        sa.Column('result', JSONB(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("action IN ('leave', 'remove', 'role')", name='ck_membership_operations_action'),
        sa.UniqueConstraint('actor_id', 'client_key', name='uq_membership_operations_actor_client_key'),
    )
    op.create_table('membership_event_revocations',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('event_id', sa.String(36), sa.ForeignKey('events.id'), nullable=False),
        sa.Column('user_id', sa.String(36), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('cutoff_order', sa.BigInteger(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint('cutoff_order >= 0', name='ck_membership_event_revocations_cutoff_nonnegative'),
        sa.UniqueConstraint('event_id', 'user_id', name='uq_membership_event_revocations_event_user'),
    )
    op.alter_column('notifications', 'event_id', existing_type=sa.String(36), nullable=True)
    op.add_column('notifications', sa.Column('org_id', sa.String(36), sa.ForeignKey('organizations.id'), nullable=True))
    op.create_check_constraint('ck_notifications_context', 'notifications', 'event_id IS NOT NULL OR org_id IS NOT NULL')


def downgrade() -> None:
    connection = op.get_bind()
    for table in ('membership_applications', 'membership_invitations', 'membership_audits',
                  'membership_operations', 'membership_event_revocations'):
        if connection.scalar(sa.text(f'SELECT EXISTS (SELECT 1 FROM {table})')):
            raise RuntimeError('Sprint 8 data exists; downgrade would discard membership history or access revocation.')
    if connection.scalar(sa.text('SELECT EXISTS (SELECT 1 FROM notifications WHERE org_id IS NOT NULL OR event_id IS NULL)')):
        raise RuntimeError('Sprint 8 data exists; downgrade would discard organization notification context.')
    op.drop_constraint('ck_notifications_context', 'notifications', type_='check')
    op.drop_column('notifications', 'org_id')
    op.alter_column('notifications', 'event_id', existing_type=sa.String(36), nullable=False)
    for table in ('membership_event_revocations', 'membership_operations', 'membership_audits',
                  'membership_invitations', 'membership_applications'):
        op.drop_table(table)
