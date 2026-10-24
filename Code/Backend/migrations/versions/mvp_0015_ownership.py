"""Add manual ownership offers/audits and enforce unique active ownership."""
from alembic import op
import sqlalchemy as sa

revision = 'mvp_0015'
down_revision = 'mvp_0014'
branch_labels = None
depends_on = None


def upgrade() -> None:
    duplicate = op.get_bind().scalar(sa.text("""
        SELECT 1 FROM org_memberships WHERE active AND role = 'owner'
        GROUP BY org_id HAVING count(*) > 1 LIMIT 1
    """))
    if duplicate:
        raise RuntimeError('Multiple active owners exist; review existing data before upgrading.')
    op.create_index('uq_org_memberships_active_owner', 'org_memberships', ['org_id'],
                    unique=True, postgresql_where=sa.text("active AND role = 'owner'"))
    op.create_table(
        'ownership_transfers',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('org_id', sa.String(36), sa.ForeignKey('organizations.id'), nullable=False),
        sa.Column('from_user_id', sa.String(36), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('nominee_id', sa.String(36), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('client_key', sa.String(36), nullable=False),
        sa.Column('status', sa.String(16), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('resolved_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('decided_by', sa.String(36), sa.ForeignKey('users.id'), nullable=True),
        sa.UniqueConstraint('from_user_id', 'client_key', name='uq_ownership_transfers_from_key'),
        sa.CheckConstraint("status IN ('pending','accepted','declined','revoked','expired')", name='ck_ownership_transfers_status'),
        sa.CheckConstraint('from_user_id <> nominee_id', name='ck_ownership_transfers_distinct_users'),
        sa.CheckConstraint('version > 0', name='ck_ownership_transfers_version'),
        sa.CheckConstraint('expires_at > created_at', name='ck_ownership_transfers_expiry'),
    )
    op.create_index('uq_ownership_transfers_pending_org', 'ownership_transfers', ['org_id'],
                    unique=True, postgresql_where=sa.text("status = 'pending'"))
    op.create_index('ix_ownership_transfers_org_created', 'ownership_transfers', ['org_id', 'created_at'])
    op.create_table(
        'ownership_transfer_audits',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('transfer_id', sa.String(36), sa.ForeignKey('ownership_transfers.id'), nullable=False),
        sa.Column('actor_id', sa.String(36), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('action', sa.String(16), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("action IN ('requested','accepted','declined','revoked','expired')", name='ck_ownership_transfer_audits_action'),
    )
    op.create_index('ix_ownership_transfer_audits_transfer_created', 'ownership_transfer_audits', ['transfer_id', 'created_at'])


def downgrade() -> None:
    for name in ('ownership_transfers', 'ownership_transfer_audits'):
        if op.get_bind().scalar(sa.text(f'SELECT count(*) FROM {name}')):
            raise RuntimeError('Ownership transfer history exists; preserve it before downgrading.')
    op.drop_table('ownership_transfer_audits')
    op.drop_table('ownership_transfers')
    op.drop_index('uq_org_memberships_active_owner', table_name='org_memberships')
