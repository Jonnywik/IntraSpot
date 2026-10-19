"""Persist private attendee preferences without changing identity or privileges."""
from alembic import op
import sqlalchemy as sa

revision = 'mvp_0007'
down_revision = 'mvp_0006'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'user_preferences',
        sa.Column('user_id', sa.String(36), sa.ForeignKey('users.id'), primary_key=True),
        sa.Column('language', sa.String(3), nullable=False, server_default='en'),
        sa.Column('theme', sa.String(16), nullable=False, server_default='light'),
        sa.Column('text_size', sa.String(16), nullable=False, server_default='standard'),
        sa.Column('high_contrast', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('reduced_motion', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('decoration_paused', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("language IN ('en', 'fil')", name='ck_user_preferences_language'),
        sa.CheckConstraint("theme IN ('light', 'dark', 'system')", name='ck_user_preferences_theme'),
        sa.CheckConstraint("text_size IN ('standard', 'large', 'extra_large')", name='ck_user_preferences_text_size'),
    )


def downgrade() -> None:
    if op.get_bind().scalar(sa.text('SELECT EXISTS (SELECT 1 FROM user_preferences)')):
        raise RuntimeError('Sprint 9 preferences exist; archive them before a deliberate rollback.')
    op.drop_table('user_preferences')
