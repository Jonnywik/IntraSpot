"""Add text-persona scopes, user blocks and explicit registration acknowledgement."""
from alembic import op
import sqlalchemy as sa

revision = 'mvp_0014'
down_revision = 'mvp_0013'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'user_blocks',
        sa.Column('blocker_id', sa.String(36), sa.ForeignKey('users.id'), primary_key=True),
        sa.Column('target_id', sa.String(36), sa.ForeignKey('users.id'), primary_key=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint('blocker_id <> target_id', name='ck_user_blocks_not_self'),
    )
    op.create_index('ix_user_blocks_target_blocker', 'user_blocks', ['target_id', 'blocker_id'])
    op.create_table(
        'event_persona_visibility',
        sa.Column('event_id', sa.String(36), sa.ForeignKey('events.id'), primary_key=True),
        sa.Column('user_id', sa.String(36), sa.ForeignKey('users.id'), primary_key=True),
        sa.Column('visible', sa.Boolean(), nullable=False, server_default=sa.text('false')),
    )
    op.add_column('registration_receipts', sa.Column(
        'blocked_attendee_acknowledged', sa.Boolean(), nullable=False,
        server_default=sa.text('false'),
    ))


def downgrade() -> None:
    connection = op.get_bind()
    for name in ('user_blocks', 'event_persona_visibility'):
        if connection.scalar(sa.text(f'SELECT count(*) FROM {name}')):
            raise RuntimeError('Sprint 18 privacy choices exist; preserve them before downgrading.')
    if connection.scalar(sa.text(
        'SELECT count(*) FROM registration_receipts WHERE blocked_attendee_acknowledged'
    )):
        raise RuntimeError('Sprint 18 registration acknowledgements exist; preserve them before downgrading.')
    op.drop_column('registration_receipts', 'blocked_attendee_acknowledged')
    op.drop_table('event_persona_visibility')
    op.drop_table('user_blocks')
