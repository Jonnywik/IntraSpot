"""Durable media accounting; keep legacy metadata and bytes unchanged."""
from alembic import op
import sqlalchemy as sa

revision = 'mvp_0018'
down_revision = 'mvp_0017'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('media_objects',
        sa.Column('id', sa.String(36), primary_key=True),
        # Independent reservations must not wait on the caller's organization lock.
        sa.Column('org_id', sa.String(36), nullable=False),
        sa.Column('provider', sa.String(16), nullable=False),
        sa.Column('object_key', sa.String(128), nullable=False),
        sa.Column('byte_size', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('status', sa.String(16), nullable=False, server_default='reserved'),
        sa.Column('orphan_seen_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('orphan_seen_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('last_seen_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('backup_protected_until', sa.DateTime(timezone=True), nullable=True),
        sa.Column('report_protected_until', sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("provider IN ('local','supabase')", name='ck_media_objects_provider'),
        sa.CheckConstraint("status IN ('reserved','stored')", name='ck_media_objects_status'),
        sa.CheckConstraint('byte_size > 0', name='ck_media_objects_byte_size'),
        sa.CheckConstraint('orphan_seen_count >= 0', name='ck_media_objects_orphan_seen_count'),
        sa.UniqueConstraint('object_key', name='uq_media_objects_object_key'))
    op.create_index('ix_media_objects_org_status', 'media_objects', ['org_id', 'status'])
    op.execute("INSERT INTO media_objects (id,org_id,provider,object_key,byte_size,created_at,status,orphan_seen_count) SELECT id,org_id,'local',id || '.webp',byte_size,created_at,'stored',0 FROM media_assets")


def downgrade():
    if op.get_bind().scalar(sa.text('SELECT count(*) FROM media_objects')):
        raise RuntimeError('Media accounting exists; preserve objects and ledger before downgrade')
    op.drop_index('ix_media_objects_org_status', table_name='media_objects')
    op.drop_table('media_objects')
