"""Add private saved-event references without changing registration or event data."""
from alembic import op
import sqlalchemy as sa

revision = 'mvp_0012'
down_revision = 'mvp_0011'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'saved_events',
        sa.Column('user_id', sa.String(36), sa.ForeignKey('users.id'), primary_key=True),
        sa.Column('event_id', sa.String(36), sa.ForeignKey('events.id'), primary_key=True),
        sa.Column('saved_at', sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    if op.get_bind().scalar(sa.text('SELECT count(*) FROM saved_events')):
        raise RuntimeError('Sprint 17 saved events exist; preserve them before downgrading.')
    op.drop_table('saved_events')
