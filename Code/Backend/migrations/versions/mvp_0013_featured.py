"""Add featured requests and immutable decision history; preserve existing data."""
from alembic import op
import sqlalchemy as sa

revision = 'mvp_0013'
down_revision = 'mvp_0012'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'featured_requests',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('event_id', sa.String(36), sa.ForeignKey('events.id'), nullable=False),
        sa.Column('requested_by', sa.String(36), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('requested_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('status', sa.String(16), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('snapshot_hash', sa.String(64), nullable=False),
        sa.Column('starts_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('ends_at', sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("status IN ('pending','paused','approved','rejected','revoked','expired')", name='ck_featured_requests_status'),
        sa.CheckConstraint('version > 0', name='ck_featured_requests_version'),
        sa.CheckConstraint("status != 'approved' OR (starts_at IS NOT NULL AND ends_at IS NOT NULL AND ends_at > starts_at)", name='ck_featured_requests_window'),
    )
    op.create_index('uq_featured_requests_open_event', 'featured_requests', ['event_id'], unique=True,
                    postgresql_where=sa.text("status IN ('pending','paused','approved')"))
    # PostgreSQL's native range GiST operator class needs no btree_gist extension.
    op.create_exclude_constraint(
        'ex_featured_requests_window', 'featured_requests',
        (sa.literal_column("tstzrange(starts_at, ends_at, '[)')"), '&&'),
        where=sa.text("status = 'approved'"), using='gist',
    )
    op.create_table(
        'featured_decisions',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('request_id', sa.String(36), sa.ForeignKey('featured_requests.id'), nullable=False),
        sa.Column('actor_id', sa.String(36), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('action', sa.String(16), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('snapshot_hash', sa.String(64), nullable=False),
        sa.Column('starts_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('ends_at', sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("action IN ('requested','approved','rejected','revoked','paused')", name='ck_featured_decisions_action'),
    )
    op.create_index('ix_featured_decisions_request_id', 'featured_decisions', ['request_id'])


def downgrade() -> None:
    for name in ('featured_decisions', 'featured_requests'):
        if op.get_bind().scalar(sa.text(f'SELECT count(*) FROM {name}')):
            raise RuntimeError('Sprint 19 feature history exists; preserve it before downgrading.')
    op.drop_table('featured_decisions')
    op.drop_table('featured_requests')
