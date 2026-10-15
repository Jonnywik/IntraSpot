"""Add local communication and bounded report evidence without rewriting MVP data.

Revision ID: mvp_0005
Revises: mvp_0004
"""
from alembic import op
import sqlalchemy as sa

revision = 'mvp_0005'
down_revision = 'mvp_0004'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('event_reactions',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('event_id', sa.String(36), sa.ForeignKey('events.id'), nullable=False),
        sa.Column('user_id', sa.String(36), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('kind', sa.String(16), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint('event_id', 'user_id', name='uq_event_reactions_user_event'),
        sa.CheckConstraint("kind IN ('interested','excited','support','kudos','wow','relate')", name='ck_event_reactions_kind'),
    )
    for table, prefix in (('event_comments', 'event_comments'), ('chat_messages', 'chat_messages')):
        op.create_table(table,
            sa.Column('id', sa.String(36), primary_key=True),
            sa.Column('event_id', sa.String(36), sa.ForeignKey('events.id'), nullable=False),
            sa.Column('author_id', sa.String(36), sa.ForeignKey('users.id'), nullable=False),
            sa.Column('sequence', sa.BigInteger(), sa.Identity(), nullable=False, unique=True),
            sa.Column('body', sa.Text(), nullable=True),
            sa.Column('body_hash', sa.String(64), nullable=False),
            sa.Column('client_key', sa.String(128), nullable=False),
            sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
            sa.Column('removed_at', sa.DateTime(timezone=True), nullable=True),
            sa.UniqueConstraint('event_id', 'author_id', 'client_key', name=f'uq_{prefix}_client_key'),
        )
        op.create_index(f'ix_{prefix}_event_sequence', table, ['event_id', 'sequence'])
    op.create_table('content_reports',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('event_id', sa.String(36), sa.ForeignKey('events.id'), nullable=False),
        sa.Column('org_id', sa.String(36), sa.ForeignKey('organizations.id'), nullable=False),
        sa.Column('reporter_id', sa.String(36), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('subject_user_id', sa.String(36), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('kind', sa.String(16), nullable=False),
        sa.Column('target_id', sa.String(36), nullable=False),
        sa.Column('reason', sa.String(24), nullable=False),
        sa.Column('status', sa.String(24), nullable=False),
        sa.Column('stage', sa.String(16), nullable=False),
        sa.Column('evidence', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('deadline', sa.DateTime(timezone=True), nullable=False),
        sa.Column('resolved_at', sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("kind IN ('comment','message','person')", name='ck_content_reports_kind'),
        sa.CheckConstraint("reason IN ('harassment','spam','deception','impersonation','other')", name='ck_content_reports_reason'),
        sa.CheckConstraint("status IN ('open','escalated','dismissed','removed','warned','expired')", name='ck_content_reports_status'),
        sa.CheckConstraint("stage IN ('organization','platform')", name='ck_content_reports_stage'),
    )
    op.create_index('uq_content_reports_active_reporter_target', 'content_reports',
                    ['reporter_id', 'kind', 'target_id'], unique=True,
                    postgresql_where=sa.text("status IN ('open','escalated')"))
    op.create_index('ix_content_reports_event_stage_deadline', 'content_reports', ['event_id', 'stage', 'deadline'])
    op.create_index('ix_content_reports_subject_kind_status_deadline', 'content_reports',
                    ['subject_user_id', 'kind', 'status', 'deadline'])
    op.create_table('report_decisions',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('report_id', sa.String(36), sa.ForeignKey('content_reports.id'), nullable=False),
        sa.Column('reviewer_id', sa.String(36), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('action', sa.String(24), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("action IN ('dismiss','remove','escalate','warn','expire')", name='ck_report_decisions_action'),
    )
    op.create_table('content_hides',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('user_id', sa.String(36), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('event_id', sa.String(36), sa.ForeignKey('events.id'), nullable=False),
        sa.Column('kind', sa.String(16), nullable=False),
        sa.Column('target_id', sa.String(36), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("kind IN ('comment','message')", name='ck_content_hides_kind'),
        sa.UniqueConstraint('user_id', 'kind', 'target_id', name='uq_content_hides_user_target'),
    )
    op.add_column('notifications', sa.Column('read_at', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    connection = op.get_bind()
    for table in ('event_reactions', 'event_comments', 'chat_messages', 'content_reports', 'report_decisions', 'content_hides'):
        if connection.scalar(sa.text(f'SELECT EXISTS (SELECT 1 FROM {table})')):
            raise RuntimeError('Sprint 7 data exists; downgrade would discard communication or safety records.')
    if connection.scalar(sa.text('SELECT EXISTS (SELECT 1 FROM notifications WHERE read_at IS NOT NULL)')):
        raise RuntimeError('Sprint 7 data exists; downgrade would discard notification read states.')
    op.drop_column('notifications', 'read_at')
    for table in ('content_hides', 'report_decisions', 'content_reports', 'chat_messages', 'event_comments', 'event_reactions'):
        op.drop_table(table)
