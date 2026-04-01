from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List
from uuid import UUID

from app.database import get_db
from app.schemas import RunCreate, RunUpdate, RunResponse, RunManifestResponse
from app.crud import (
    create_run, get_run, get_all_runs, update_run,
    create_manifest, get_manifest
)
from app.flows.design_pipeline import design_pipeline_flow

router = APIRouter(prefix="/runs", tags=["runs"])


@router.post("/", response_model=RunResponse, status_code=status.HTTP_201_CREATED)
async def create_run_endpoint(
    run_create: RunCreate,
    db: AsyncSession = Depends(get_db),
):
    """Create a new run and trigger the design pipeline flow."""
    # Create the run record
    db_run = await create_run(db, run_create)
    
    # Create an associated manifest
    manifest = await create_manifest(db, db_run.id)
    
    # Trigger the Prefect flow
    try:
        flow_run = await design_pipeline_flow(
            run_id=str(db_run.id),
            pdb_filename=db_run.pdb_filename or "sample.pdb",
            mode=db_run.mode.value,
        )
        
        # Store the flow ID on the run
        db_run.prefect_flow_id = flow_run.id
        db_run = await update_run(db, db_run.id, RunUpdate(prefect_flow_id=flow_run.id))
    except Exception as e:
        # Log error but don't fail the request
        print(f"Warning: Failed to trigger Prefect flow: {e}")
    
    return db_run


@router.get("/", response_model=List[RunResponse])
async def list_runs(
    skip: int = 0,
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
):
    """List all runs."""
    runs = await get_all_runs(db, skip=skip, limit=limit)
    return runs


@router.get("/{run_id}", response_model=RunResponse)
async def get_run_endpoint(
    run_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """Get a single run by ID."""
    db_run = await get_run(db, run_id)
    if not db_run:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Run {run_id} not found"
        )
    return db_run


@router.get("/{run_id}/manifest", response_model=RunManifestResponse)
async def get_manifest_endpoint(
    run_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """Get the manifest (provenance record) for a run."""
    # Verify run exists
    db_run = await get_run(db, run_id)
    if not db_run:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Run {run_id} not found"
        )
    
    # Get or create manifest
    manifest = await get_manifest(db, run_id)
    if not manifest:
        manifest = await create_manifest(db, run_id)
    
    return manifest
