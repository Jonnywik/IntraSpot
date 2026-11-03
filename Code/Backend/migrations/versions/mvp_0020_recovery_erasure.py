"""Add backup retention references and minimal erasure receipts/tombstones."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = 'mvp_0020'
down_revision = 'mvp_0019'
branch_labels = depends_on = None


def upgrade():
    op.create_table('erasure_requests',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('user_id', sa.String(36), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('requested_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('due_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('completed_at', sa.DateTime(timezone=True)),
        sa.Column('status', sa.String(20), nullable=False),
        sa.Column('blocker_code', sa.String(80)),
        sa.Column('counts', JSONB, nullable=False))
    op.create_index('uq_erasure_requests_active_user', 'erasure_requests', ['user_id'], unique=True,
                    postgresql_where=sa.text("user_id IS NOT NULL AND status <> 'completed'"))
    op.create_table('erased_accounts',
        sa.Column('user_id', sa.String(36), sa.ForeignKey('users.id'), primary_key=True),
        sa.Column('erased_at', sa.DateTime(timezone=True), nullable=False))
    op.create_table('backup_snapshots',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('purpose', sa.String(20), nullable=False),
        sa.Column('status', sa.String(20), nullable=False),
        sa.Column('retired_at', sa.DateTime(timezone=True)))
    op.create_table('backup_object_references',
        sa.Column('snapshot_id', sa.String(36), sa.ForeignKey('backup_snapshots.id'), primary_key=True),
        sa.Column('media_id', sa.String(36), primary_key=True))


def downgrade():
    for table in ('erasure_requests','erased_accounts','backup_snapshots','backup_object_references'):
        if op.get_bind().scalar(sa.text(f'SELECT count(*) FROM {table}')):
            raise RuntimeError('Recovery/erasure history exists; use application rollback and preserve metadata')
    op.drop_table('backup_object_references')
    op.drop_table('backup_snapshots')
    op.drop_table('erased_accounts')
    op.drop_table('erasure_requests')
