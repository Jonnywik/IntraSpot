"""Add local normalized event and organization media without changing existing rows."""
from alembic import op
import sqlalchemy as sa

revision = 'mvp_0011'
down_revision = 'mvp_0010'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'media_assets',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('org_id', sa.String(36), sa.ForeignKey('organizations.id'), nullable=False),
        sa.Column('kind', sa.String(16), nullable=False),
        sa.Column('width', sa.Integer(), nullable=False),
        sa.Column('height', sa.Integer(), nullable=False),
        sa.Column('byte_size', sa.Integer(), nullable=False),
        sa.Column('created_by', sa.String(36), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("kind IN ('banner', 'logo')", name='ck_media_assets_kind'),
        sa.CheckConstraint('width > 0 AND height > 0', name='ck_media_assets_dimensions'),
        sa.CheckConstraint('byte_size > 0', name='ck_media_assets_byte_size'),
    )
    op.add_column('events', sa.Column('banner_media_id', sa.String(36), nullable=True))
    op.add_column('organizations', sa.Column('logo_media_id', sa.String(36), nullable=True))
    op.create_foreign_key('fk_events_banner_media', 'events', 'media_assets', ['banner_media_id'], ['id'])
    op.create_foreign_key('fk_organizations_logo_media', 'organizations', 'media_assets', ['logo_media_id'], ['id'])


def downgrade() -> None:
    connection = op.get_bind()
    if connection.scalar(sa.text('SELECT count(*) FROM media_assets')):
        raise RuntimeError('Sprint 16 media data exists; preserve it before downgrading.')
    op.drop_constraint('fk_organizations_logo_media', 'organizations', type_='foreignkey')
    op.drop_constraint('fk_events_banner_media', 'events', type_='foreignkey')
    op.drop_column('organizations', 'logo_media_id')
    op.drop_column('events', 'banner_media_id')
    op.drop_table('media_assets')
