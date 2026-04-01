"""Add notifications table + user preferences column

Revision ID: 0002_notifications
Revises: 0001_initial_schema
Create Date: 2026-03-29
"""
from alembic import op
import sqlalchemy as sa

revision = '0002_notifications'
down_revision = '0001_initial_schema'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('notifications',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('user_id', sa.String(36), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('level', sa.String(10), nullable=False, default='info'),
        sa.Column('title', sa.String(120), nullable=False),
        sa.Column('body', sa.Text, nullable=False),
        sa.Column('run_id', sa.String(36), nullable=True),
        sa.Column('read', sa.Boolean, default=False, nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('action_url', sa.String(255), nullable=True),
    )
    op.create_index('ix_notifications_user_id', 'notifications', ['user_id'])
    op.create_index('ix_notifications_read', 'notifications', ['user_id', 'read'])

    with op.batch_alter_table('users') as batch_op:
        batch_op.add_column(sa.Column('preferences_json', sa.Text, nullable=True))


def downgrade() -> None:
    op.drop_table('notifications')
    with op.batch_alter_table('users') as batch_op:
        batch_op.drop_column('preferences_json')
