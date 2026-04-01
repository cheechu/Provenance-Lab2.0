from sqlalchemy import Column, String, DateTime, Enum, ForeignKey, JSON, UUID as SQL_UUID
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from datetime import datetime
import uuid
import enum

from app.database import Base


class RunStatus(str, enum.Enum):
    """Status of a provenance run."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class RunMode(str, enum.Enum):
    """Mode of execution for a run."""
    THERAPEUTIC = "therapeutic"
    CROP_DEMO = "crop_demo"


class Run(Base):
    """Provenance run record."""
    
    __tablename__ = "runs"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    status = Column(Enum(RunStatus), default=RunStatus.PENDING, nullable=False)
    mode = Column(Enum(RunMode), nullable=False)
    pdb_filename = Column(String, nullable=True)
    pdb_path = Column(String, nullable=True)
    config = Column(JSONB, default={}, nullable=False)
    prefect_flow_id = Column(String, nullable=True)
    
    # Relationships
    manifest = relationship("RunManifest", back_populates="run", uselist=False)


class RunManifest(Base):
    """Sealed manifest for a run (provenance record)."""
    
    __tablename__ = "run_manifests"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id = Column(UUID(as_uuid=True), ForeignKey("runs.id"), nullable=False)
    inputs_digest = Column(String, nullable=True)  # SHA-256 hash
    git_sha = Column(String, nullable=True)
    docker_image = Column(String, nullable=True)
    prefect_flow_id = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    sealed_at = Column(DateTime, nullable=True)
    steps = Column(JSONB, default=[], nullable=False)  # Array of step objects
    
    # Relationships
    run = relationship("Run", back_populates="manifest")
