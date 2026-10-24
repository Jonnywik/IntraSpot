"""Add independent event safety controls, reports and temporary org suspensions."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = 'mvp_0017'
down_revision = 'mvp_0016'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('event_controls',
        sa.Column('event_id', sa.String(36), sa.ForeignKey('events.id'), primary_key=True),
        *(sa.Column(flag, sa.Boolean(), nullable=False, server_default=sa.text('false'))
          for flag in ('org_hidden', 'platform_hidden', 'removed', 'cancelled')),
        sa.Column('version', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('org_reviewed_at', sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint('version >= 0', name='ck_event_controls_version'))
    op.create_table('organization_suspensions',
        sa.Column('org_id', sa.String(36), sa.ForeignKey('organizations.id'), primary_key=True),
        sa.Column('suspended_until', sa.DateTime(timezone=True), nullable=True),
        sa.Column('version', sa.Integer(), nullable=False, server_default='0'),
        sa.CheckConstraint('version >= 0', name='ck_organization_suspensions_version'))
    op.create_table('event_reports',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('event_id', sa.String(36), sa.ForeignKey('events.id'), nullable=False),
        sa.Column('org_id', sa.String(36), sa.ForeignKey('organizations.id'), nullable=False),
        sa.Column('reporter_id', sa.String(36), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('reason', sa.String(16), nullable=False),
        sa.Column('stage', sa.String(16), nullable=False),
        sa.Column('status', sa.String(16), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('evidence', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('deadline', sa.DateTime(timezone=True), nullable=False),
        sa.Column('resolved_at', sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("reason IN ('safety','deception')", name='ck_event_reports_reason'),
        sa.CheckConstraint("stage IN ('organization','platform')", name='ck_event_reports_stage'),
        sa.CheckConstraint("status IN ('open','escalated','dismissed','hidden','removed','upheld','expired')", name='ck_event_reports_status'),
        sa.CheckConstraint('version > 0', name='ck_event_reports_version'))
    op.create_index('uq_event_reports_active_reporter', 'event_reports', ['reporter_id', 'event_id'],
                    unique=True, postgresql_where=sa.text("status IN ('open','escalated')"))
    op.create_index('ix_event_reports_event_created', 'event_reports', ['event_id', 'created_at'])
    op.create_table('safety_audits',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('org_id', sa.String(36), sa.ForeignKey('organizations.id'), nullable=False),
        sa.Column('event_id', sa.String(36), sa.ForeignKey('events.id'), nullable=True),
        sa.Column('report_id', sa.String(36), sa.ForeignKey('event_reports.id'), nullable=True),
        sa.Column('actor_id', sa.String(36), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('client_key', sa.String(100), nullable=True),
        sa.Column('payload_hash', sa.String(64), nullable=True),
        sa.Column('scope', sa.String(16), nullable=False),
        sa.Column('action', sa.String(16), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('previous', postgresql.JSONB(), nullable=False),
        sa.Column('result', postgresql.JSONB(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint('actor_id', 'client_key', name='uq_safety_audits_actor_key'),
        sa.CheckConstraint("scope IN ('report','event','organization')", name='ck_safety_audits_scope'),
        sa.CheckConstraint("action IN ('report','dismiss','hide','restore','remove','uphold','cancel','suspend','resume','expire')", name='ck_safety_audits_action'),
        sa.CheckConstraint('version >= 0', name='ck_safety_audits_version'))
    op.create_index('ix_safety_audits_org_created', 'safety_audits', ['org_id', 'created_at'])


def downgrade():
    for table in ('safety_audits', 'event_reports', 'organization_suspensions', 'event_controls'):
        if op.get_bind().scalar(sa.text(f'SELECT count(*) FROM {table}')):
            raise RuntimeError('Safety data exists; preserve it before downgrading.')
    for table in ('safety_audits', 'event_reports', 'organization_suspensions', 'event_controls'):
        op.drop_table(table)
