"""Add organization announcements and event-independent platform safety review."""
from alembic import op
import sqlalchemy as sa

revision = 'mvp_0010'
down_revision = 'mvp_0009'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('announcements',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('org_id', sa.String(36), sa.ForeignKey('organizations.id'), nullable=False),
        sa.Column('created_by', sa.String(36), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('title', sa.String(200), nullable=False),
        sa.Column('body', sa.Text(), nullable=True),
        sa.Column('audience', sa.String(16), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('client_key', sa.String(36), nullable=False),
        sa.Column('create_hash', sa.String(64), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('edited_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('hidden_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('removed_at', sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint('org_id', 'created_by', 'client_key', name='uq_announcements_create_key'),
        sa.CheckConstraint("audience IN ('public','members')", name='ck_announcements_audience'),
        sa.CheckConstraint('version > 0', name='ck_announcements_version'),
        sa.CheckConstraint('removed_at IS NOT NULL OR body IS NOT NULL', name='ck_announcements_body'),
    )
    op.create_index('ix_announcements_org_created', 'announcements', ['org_id', 'created_at', 'id'])
    op.create_table('announcement_revisions',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('announcement_id', sa.String(36), sa.ForeignKey('announcements.id'), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('actor_id', sa.String(36), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('action', sa.String(16), nullable=False),
        sa.Column('title', sa.String(200), nullable=False),
        sa.Column('body', sa.Text(), nullable=True),
        sa.Column('audience', sa.String(16), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint('announcement_id', 'version', name='uq_announcement_revisions_version'),
        sa.CheckConstraint('version > 0', name='ck_announcement_revisions_version'),
        sa.CheckConstraint("audience IN ('public','members')", name='ck_announcement_revisions_audience'),
        sa.CheckConstraint("action IN ('publish','edit','remove','hide','restore')", name='ck_announcement_revisions_action'),
    )
    op.create_table('announcement_reactions',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('announcement_id', sa.String(36), sa.ForeignKey('announcements.id'), nullable=False),
        sa.Column('user_id', sa.String(36), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('kind', sa.String(16), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint('announcement_id', 'user_id', name='uq_announcement_reactions_user_post'),
        sa.CheckConstraint("kind IN ('interested','excited','support','kudos','wow','relate')", name='ck_announcement_reactions_kind'),
    )
    op.create_table('announcement_reports',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('announcement_id', sa.String(36), sa.ForeignKey('announcements.id'), nullable=False),
        sa.Column('org_id', sa.String(36), sa.ForeignKey('organizations.id'), nullable=False),
        sa.Column('reporter_id', sa.String(36), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('subject_user_id', sa.String(36), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('reason', sa.String(24), nullable=False),
        sa.Column('status', sa.String(24), nullable=False),
        sa.Column('reported_version', sa.Integer(), nullable=False),
        sa.Column('evidence', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('deadline', sa.DateTime(timezone=True), nullable=False),
        sa.Column('resolved_at', sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("reason IN ('harassment','spam','deception','impersonation','other')", name='ck_announcement_reports_reason'),
        sa.CheckConstraint("status IN ('open','dismissed','hidden','restored','removed','expired')", name='ck_announcement_reports_status'),
        sa.CheckConstraint('reported_version > 0', name='ck_announcement_reports_version'),
    )
    op.create_index('uq_announcement_reports_active_target', 'announcement_reports',
        ['reporter_id', 'announcement_id'], unique=True, postgresql_where=sa.text("status = 'open'"))
    op.create_index('ix_announcement_reports_org_deadline', 'announcement_reports', ['org_id', 'status', 'deadline'])
    op.create_table('announcement_report_decisions',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('report_id', sa.String(36), sa.ForeignKey('announcement_reports.id'), nullable=False),
        sa.Column('reviewer_id', sa.String(36), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('action', sa.String(16), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("action IN ('dismiss','hide','restore','remove','expire')", name='ck_announcement_report_decisions_action'),
    )


def downgrade() -> None:
    if any(op.get_bind().scalar(sa.text(f'SELECT EXISTS (SELECT 1 FROM {table})')) for table in (
        'announcements', 'announcement_revisions', 'announcement_reactions',
        'announcement_reports', 'announcement_report_decisions',
    )):
        raise RuntimeError('Sprint 14 announcement data exists; archive before deliberate rollback.')
    op.drop_table('announcement_report_decisions')
    op.drop_index('ix_announcement_reports_org_deadline', table_name='announcement_reports')
    op.drop_index('uq_announcement_reports_active_target', table_name='announcement_reports')
    op.drop_table('announcement_reports')
    op.drop_table('announcement_reactions')
    op.drop_table('announcement_revisions')
    op.drop_index('ix_announcements_org_created', table_name='announcements')
    op.drop_table('announcements')
