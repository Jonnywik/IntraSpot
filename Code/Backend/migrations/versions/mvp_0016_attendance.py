"""Add manual attendance state, marks and immutable command history."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = 'mvp_0016'
down_revision = 'mvp_0015'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'attendance_sessions',
        sa.Column('event_id', sa.String(36), sa.ForeignKey('events.id'), primary_key=True),
        sa.Column('is_open', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('version', sa.Integer(), nullable=False, server_default='0'),
        sa.CheckConstraint('version >= 0', name='ck_attendance_sessions_version'),
    )
    op.create_table(
        'attendance_marks',
        sa.Column('registration_id', sa.String(36), sa.ForeignKey('registrations.id'), primary_key=True),
        sa.Column('attended', sa.Boolean(), nullable=False, server_default=sa.text('false')),
    )
    op.create_table(
        'attendance_audits',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('event_id', sa.String(36), sa.ForeignKey('events.id'), nullable=False),
        sa.Column('actor_id', sa.String(36), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('client_key', sa.String(36), nullable=False),
        sa.Column('payload_hash', sa.String(64), nullable=False),
        sa.Column('action', sa.String(16), nullable=False),
        sa.Column('registration_id', sa.String(36), sa.ForeignKey('registrations.id'), nullable=True),
        sa.Column('previous_value', sa.Boolean(), nullable=False),
        sa.Column('value', sa.Boolean(), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('result', postgresql.JSONB(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint('actor_id', 'client_key', name='uq_attendance_audits_actor_key'),
        sa.CheckConstraint("action IN ('session','mark')", name='ck_attendance_audits_action'),
        sa.CheckConstraint('version > 0', name='ck_attendance_audits_version'),
    )
    op.create_index('ix_attendance_audits_event_created', 'attendance_audits', ['event_id', 'created_at'])


def downgrade() -> None:
    for table in ('attendance_audits', 'attendance_marks', 'attendance_sessions'):
        if op.get_bind().scalar(sa.text(f'SELECT count(*) FROM {table}')):
            raise RuntimeError('Attendance data exists; preserve it before downgrading.')
    op.drop_table('attendance_audits')
    op.drop_table('attendance_marks')
    op.drop_table('attendance_sessions')
