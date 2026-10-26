"""Add bounded-maintenance metadata and pseudonymous shared limiter buckets."""
from alembic import op
import sqlalchemy as sa

revision = 'mvp_0019'
down_revision = 'mvp_0018'
branch_labels = depends_on = None


def upgrade():
    op.create_table('maintenance_state',
        sa.Column('name', sa.String(40), primary_key=True),
        sa.Column('cursor', sa.String(80)),
        sa.Column('last_started_at', sa.DateTime(timezone=True)),
        sa.Column('last_success_at', sa.DateTime(timezone=True)),
        sa.Column('last_error_code', sa.String(80)),
        sa.Column('processed_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('duration_ms', sa.Integer(), nullable=False, server_default='0'))
    op.create_table('rate_limit_buckets',
        sa.Column('key', sa.String(80), primary_key=True),
        sa.Column('tokens', sa.Float(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False))
    op.create_index('ix_rate_limit_buckets_expires_at', 'rate_limit_buckets', ['expires_at'])


def downgrade():
    op.drop_table('rate_limit_buckets')
    op.drop_table('maintenance_state')
