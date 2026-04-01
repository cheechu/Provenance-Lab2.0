from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID
from typing import Optional, List

from app.models import Run, RunManifest, RunStatus
from app.schemas import RunCreate, RunUpdate


async def create_run(db: AsyncSession, run_create: RunCreate) -> Run:
    """Create a new run."""
    db_run = Run(
        mode=run_create.mode,
        pdb_filename=run_create.pdb_filename,
        pdb_path=run_create.pdb_path,
        config=run_create.config or {},
    )
    db.add(db_run)
    await db.commit()
    await db.refresh(db_run)
    return db_run


async def get_run(db: AsyncSession, run_id: UUID) -> Optional[Run]:
    """Get a run by ID."""
    result = await db.execute(select(Run).where(Run.id == run_id))
    return result.scalar_one_or_none()


async def get_all_runs(db: AsyncSession, skip: int = 0, limit: int = 100) -> List[Run]:
    """Get all runs with pagination."""
    result = await db.execute(select(Run).offset(skip).limit(limit))
    return result.scalars().all()


async def update_run(db: AsyncSession, run_id: UUID, run_update: RunUpdate) -> Optional[Run]:
    """Update a run."""
    db_run = await get_run(db, run_id)
    if not db_run:
        return None
    
    if run_update.status is not None:
        db_run.status = run_update.status
    if run_update.prefect_flow_id is not None:
        db_run.prefect_flow_id = run_update.prefect_flow_id
    if run_update.config is not None:
        db_run.config = run_update.config
    
    await db.commit()
    await db.refresh(db_run)
    return db_run


async def create_manifest(db: AsyncSession, run_id: UUID) -> RunManifest:
    """Create a manifest for a run."""
    manifest = RunManifest(run_id=run_id, steps=[])
    db.add(manifest)
    await db.commit()
    await db.refresh(manifest)
    return manifest


async def get_manifest(db: AsyncSession, run_id: UUID) -> Optional[RunManifest]:
    """Get manifest for a run."""
    result = await db.execute(
        select(RunManifest).where(RunManifest.run_id == run_id)
    )
    return result.scalar_one_or_none()
