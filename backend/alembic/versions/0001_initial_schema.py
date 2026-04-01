"""Create initial schema with Run and RunManifest tables.

Revision ID: 0001_initial_schema
Revises: 
Create Date: 2026-03-31 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
import uuid

# revision identifiers, used by Alembic.
revision = '0001_initial_schema'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create ENUM types
    status_enum = postgresql.ENUM('pending', 'running', 'completed', 'failed', name='runstatus', create_type=False)
    status_enum.create(op.get_bind(), checkfirst=True)
    
    mode_enum = postgresql.ENUM('therapeutic', 'crop_demo', name='runmode', create_type=False)
    mode_enum.create(op.get_bind(), checkfirst=True)
    
    # Create runs table
    op.create_table(
        'runs',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False, default=uuid.uuid4),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('status', sa.Enum('pending', 'running', 'completed', 'failed', name='runstatus'), nullable=False, server_default='pending'),
        sa.Column('mode', sa.Enum('therapeutic', 'crop_demo', name='runmode'), nullable=False),
        sa.Column('pdb_filename', sa.String(), nullable=True),
        sa.Column('pdb_path', sa.String(), nullable=True),
        sa.Column('config', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default='{}'),
        sa.Column('prefect_flow_id', sa.String(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_runs_created_at', 'runs', ['created_at'])
    op.create_index('ix_runs_status', 'runs', ['status'])
    
    # Create run_manifests table
    op.create_table(
        'run_manifests',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False, default=uuid.uuid4),
        sa.Column('run_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('inputs_digest', sa.String(), nullable=True),
        sa.Column('git_sha', sa.String(), nullable=True),
        sa.Column('docker_image', sa.String(), nullable=True),
        sa.Column('prefect_flow_id', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('sealed_at', sa.DateTime(), nullable=True),
        sa.Column('steps', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default='[]'),
        sa.ForeignKeyConstraint(['run_id'], ['runs.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('run_id', name='uq_run_manifests_run_id')
    )
    op.create_index('ix_run_manifests_run_id', 'run_manifests', ['run_id'])


def downgrade() -> None:
    op.drop_index('ix_run_manifests_run_id', table_name='run_manifests')
    op.drop_table('run_manifests')
    op.drop_index('ix_runs_status', table_name='runs')
    op.drop_index('ix_runs_created_at', table_name='runs')
    op.drop_table('runs')
    
    # Drop ENUM types
    sa.Enum('pending', 'running', 'completed', 'failed', name='runstatus').drop(op.get_bind(), checkfirst=True)
    sa.Enum('therapeutic', 'crop_demo', name='runmode').drop(op.get_bind(), checkfirst=True)
