from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime
from uuid import UUID
from enum import Enum


class RunStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class RunMode(str, Enum):
    THERAPEUTIC = "therapeutic"
    CROP_DEMO = "crop_demo"


class RunCreate(BaseModel):
    """Schema for creating a new run."""
    mode: RunMode
    pdb_filename: Optional[str] = None
    pdb_path: Optional[str] = None
    config: Optional[Dict[str, Any]] = Field(default_factory=dict)


class RunUpdate(BaseModel):
    """Schema for updating a run."""
    status: Optional[RunStatus] = None
    prefect_flow_id: Optional[str] = None
    config: Optional[Dict[str, Any]] = None


class RunResponse(BaseModel):
    """Schema for run response."""
    id: UUID
    created_at: datetime
    status: RunStatus
    mode: RunMode
    pdb_filename: Optional[str]
    pdb_path: Optional[str]
    config: Dict[str, Any]
    prefect_flow_id: Optional[str]
    
    class Config:
        from_attributes = True


class StepInfo(BaseModel):
    """Schema for a manifest step."""
    tool_version: str
    exit_status: int
    artifacts_hash: str
    timestamp: datetime


class RunManifestResponse(BaseModel):
    """Schema for run manifest (JSON-LD provenance)."""
    id: UUID
    run_id: UUID
    inputs_digest: Optional[str]
    git_sha: Optional[str]
    docker_image: Optional[str]
    prefect_flow_id: Optional[str]
    created_at: datetime
    sealed_at: Optional[datetime]
    steps: List[Dict[str, Any]]
    
    class Config:
        from_attributes = True
