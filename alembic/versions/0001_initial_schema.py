"""Initial schema — users, api_keys, refresh_tokens, runs

Revision ID: 0001_initial_schema
Revises: 
Create Date: 2026-03-29
"""
from __future__ import annotations
from alembic import op
import sqlalchemy as sa

revision = '0001_initial_schema'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('users',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('email', sa.String(255), nullable=False, unique=True),
        sa.Column('hashed_password', sa.String(255), nullable=False),
        sa.Column('full_name', sa.String(255), nullable=True),
        sa.Column('is_active', sa.Boolean(), default=True, nullable=False),
        sa.Column('is_superuser', sa.Boolean(), default=False, nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index('ix_users_email', 'users', ['email'])

    op.create_table('api_keys',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('user_id', sa.String(36), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('key_prefix', sa.String(16), nullable=False),
        sa.Column('key_hash', sa.String(255), nullable=False),
        sa.Column('scopes', sa.String(255), default='read:runs write:runs'),
        sa.Column('is_active', sa.Boolean(), default=True, nullable=False),
        sa.Column('last_used_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('request_count', sa.Integer(), default=0, nullable=False),
    )
    op.create_index('ix_api_keys_user_id', 'api_keys', ['user_id'])
    op.create_index('ix_api_keys_prefix', 'api_keys', ['key_prefix'])

    op.create_table('refresh_tokens',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('user_id', sa.String(36), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('token_hash', sa.String(255), nullable=False, unique=True),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('revoked', sa.Boolean(), default=False, nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('user_agent', sa.String(255), nullable=True),
        sa.Column('ip_address', sa.String(45), nullable=True),
    )
    op.create_index('ix_refresh_tokens_user_id', 'refresh_tokens', ['user_id'])

    op.create_table('runs',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('user_id', sa.String(36), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('status', sa.String(20), default='pending', nullable=False),
        sa.Column('track', sa.String(40), nullable=False),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('duration_ms', sa.Integer(), nullable=True),
        sa.Column('git_sha', sa.String(40), nullable=False),
        sa.Column('docker_image', sa.String(120), nullable=False),
        sa.Column('app_version', sa.String(20), default='1.0.0'),
        sa.Column('inputs_digest', sa.String(64), nullable=False),
        sa.Column('random_seed', sa.Integer(), default=42),
        sa.Column('benchmark_mode', sa.Boolean(), default=False, nullable=False),
        sa.Column('guide_sequence', sa.String(20), nullable=False),
        sa.Column('guide_pam', sa.String(10), nullable=False),
        sa.Column('target_gene', sa.String(50), nullable=False),
        sa.Column('chromosome', sa.String(20), nullable=True),
        sa.Column('position_start', sa.Integer(), nullable=True),
        sa.Column('position_end', sa.Integer(), nullable=True),
        sa.Column('strand', sa.String(1), nullable=True),
        sa.Column('editor_type', sa.String(10), nullable=False),
        sa.Column('cas_variant', sa.String(30), default='nCas9'),
        sa.Column('deaminase', sa.String(30), nullable=True),
        sa.Column('editing_window_start', sa.Integer(), default=4),
        sa.Column('editing_window_end', sa.Integer(), default=8),
        sa.Column('algorithms', sa.String(120), default='CFD,MIT'),
        sa.Column('scores_json', sa.Text(), nullable=True),
        sa.Column('bystanders_json', sa.Text(), nullable=True),
        sa.Column('explanations_json', sa.Text(), nullable=True),
        sa.Column('step_traces_json', sa.Text(), nullable=True),
        sa.Column('cfd_on_target', sa.Float(), nullable=True),
        sa.Column('cfd_off_target', sa.Float(), nullable=True),
        sa.Column('mit_on_target', sa.Float(), nullable=True),
        sa.Column('mit_off_target', sa.Float(), nullable=True),
        sa.Column('on_target_mean', sa.Float(), nullable=True),
        sa.Column('off_target_mean', sa.Float(), nullable=True),
        sa.Column('structural_variation_risk', sa.String(10), nullable=True),
        sa.Column('genome_coverage', sa.Float(), nullable=True),
    )
    op.create_index('ix_runs_status', 'runs', ['status'])
    op.create_index('ix_runs_track', 'runs', ['track'])
    op.create_index('ix_runs_target_gene', 'runs', ['target_gene'])
    op.create_index('ix_runs_inputs_digest', 'runs', ['inputs_digest'])
    op.create_index('ix_runs_on_target_mean', 'runs', ['on_target_mean'])
    op.create_index('ix_runs_benchmark', 'runs', ['benchmark_mode', 'on_target_mean'])
    op.create_index('ix_runs_gene_track', 'runs', ['target_gene', 'track'])


def downgrade() -> None:
    op.drop_table('runs')
    op.drop_table('refresh_tokens')
    op.drop_table('api_keys')
    op.drop_table('users')
