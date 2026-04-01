"""
CasAI Provenance Lab — Upload Schemas
Pydantic models for file upload validation and metadata.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class UploadedFileType(str, Enum):
    PDB         = "pdb"           # Protein Data Bank structure file
    ANNOTATION  = "annotation"    # JSON annotation/metadata file
    FASTA       = "fasta"         # FASTA sequence file
    CSV         = "csv"           # Tabular data
    VCF         = "vcf"           # Variant call format


class UploadStatus(str, Enum):
    PENDING     = "pending"
    VALIDATED   = "validated"
    REJECTED    = "rejected"


class UploadedFile(BaseModel):
    file_id:        str
    original_name:  str
    file_type:      UploadedFileType
    size_bytes:     int
    sha256:         str
    status:         UploadStatus = UploadStatus.PENDING
    storage_path:   str
    user_id:        str
    created_at:     datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    validation_errors: list[str] = Field(default_factory=list)
    metadata:       dict = Field(default_factory=dict)


class UploadResponse(BaseModel):
    file_id:       str
    original_name: str
    file_type:     UploadedFileType
    size_bytes:    int
    sha256:        str
    status:        UploadStatus
    metadata:      dict
    validation_errors: list[str]


class PDBMetadata(BaseModel):
    """Extracted from a PDB file header."""
    title:          Optional[str] = None
    resolution_a:   Optional[float] = None
    chains:         list[str] = Field(default_factory=list)
    residue_count:  Optional[int] = None
    atom_count:     Optional[int] = None
    organism:       Optional[str] = None
    experiment:     Optional[str] = None  # X-RAY, NMR, CRYO-EM…


class AnnotationMetadata(BaseModel):
    """Extracted from an annotation JSON."""
    target_gene:    Optional[str] = None
    genome_build:   Optional[str] = None
    feature_count:  int = 0
    custom_keys:    list[str] = Field(default_factory=list)
