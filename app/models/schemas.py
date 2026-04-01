"""
CasAI Provenance Lab — Core Data Models
Implements W3C PROV + RO-Crate aligned RunManifest and all sub-models.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, field_validator, computed_field


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class RunTrack(str, Enum):
    THERAPEUTIC = "therapeutic"
    CROP_DEMO = "crop_demo"
    GENOMICS_RESEARCH = "genomics_research"


class RunStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class BaseEditorType(str, Enum):
    CBE = "CBE"   # Cytosine Base Editor (C→T)
    ABE = "ABE"   # Adenine Base Editor (A→G)


class ScoringAlgorithm(str, Enum):
    CFD = "CFD"
    MIT = "MIT"
    CCTOP = "CCTop"
    DEEP_CRISPR = "DeepCRISPR"
    CRISPR_MCA = "CRISPR-MCA"


# ---------------------------------------------------------------------------
# Input Models
# ---------------------------------------------------------------------------

class GuideRNAInput(BaseModel):
    """20-nt protospacer + PAM for a CRISPR base-editor guide."""
    sequence: str = Field(..., min_length=20, max_length=20, description="20-nt protospacer sequence")
    pam: str = Field(..., description="PAM sequence (e.g. NGG for SpCas9)")
    target_gene: str = Field(..., description="Human-readable target gene symbol")
    chromosome: Optional[str] = Field(None, description="Chromosome (e.g. chr17)")
    position_start: Optional[int] = Field(None, ge=1, description="Genomic start position (1-based)")
    position_end: Optional[int] = Field(None, ge=1, description="Genomic end position (1-based)")
    strand: Optional[str] = Field(None, pattern="^[+-]$", description="Strand: + or -")

    @field_validator("sequence")
    @classmethod
    def validate_sequence(cls, v: str) -> str:
        valid = set("ACGTacgt")
        invalid = set(v) - valid
        if invalid:
            raise ValueError(f"Sequence contains invalid nucleotides: {invalid}")
        return v.upper()


class EditorConfig(BaseModel):
    """Configuration for the base-editor complex."""
    editor_type: BaseEditorType = Field(..., description="CBE (C→T) or ABE (A→G)")
    cas_variant: str = Field(default="nCas9", description="Cas protein variant used")
    deaminase: Optional[str] = Field(None, description="Deaminase enzyme (e.g. APOBEC3A, TadA-8e)")
    editing_window_start: int = Field(default=4, ge=1, le=20, description="Start of editing window (1-indexed from PAM-distal end)")
    editing_window_end: int = Field(default=8, ge=1, le=20, description="End of editing window")
    algorithms: list[ScoringAlgorithm] = Field(
        default=[ScoringAlgorithm.CFD, ScoringAlgorithm.MIT],
        description="Scoring algorithms to run"
    )

    @field_validator("editing_window_end")
    @classmethod
    def window_end_after_start(cls, v: int, info) -> int:
        start = info.data.get("editing_window_start", 4)
        if v < start:
            raise ValueError("editing_window_end must be >= editing_window_start")
        return v


class RunRequest(BaseModel):
    """Payload to initiate a new design run."""
    guide_rna: GuideRNAInput
    editor_config: EditorConfig
    track: RunTrack = Field(default=RunTrack.GENOMICS_RESEARCH)
    annotation_json: Optional[dict[str, Any]] = Field(None, description="Optional annotation metadata")
    pdb_filename: Optional[str] = Field(None, description="Reference PDB filename if uploaded")
    random_seed: int = Field(default=42, description="Seed for stochastic model components")
    benchmark_mode: bool = Field(default=False, description="If true, writes to benchmark_results.json")


# ---------------------------------------------------------------------------
# Scoring / Output Models
# ---------------------------------------------------------------------------

class AlgorithmScore(BaseModel):
    """Score produced by one scoring algorithm."""
    algorithm: ScoringAlgorithm
    on_target_score: float = Field(..., ge=0.0, le=1.0)
    off_target_risk: float = Field(..., ge=0.0, le=1.0)
    confidence_interval_95_low: float
    confidence_interval_95_high: float
    standard_error: float
    raw_data: Optional[dict[str, Any]] = None


class BystanderEditPrediction(BaseModel):
    """Predicted bystander edit at a specific position."""
    position_in_window: int
    original_base: str
    edited_base: str
    probability: float = Field(..., ge=0.0, le=1.0)
    risk_level: str = Field(..., description="low | medium | high")


class ExplainabilityEntry(BaseModel):
    """SHAP/LIME explanation for a single metric."""
    metric: str
    value: float
    plain_text: str
    caveats: str
    top_features: Optional[list[dict[str, Any]]] = None


class DesignPrediction(BaseModel):
    """Aggregated scoring output for a guide RNA design."""
    scores: list[AlgorithmScore]
    bystander_edits: list[BystanderEditPrediction]
    explanations: list[ExplainabilityEntry]
    editing_window_bases: str = Field(..., description="Bases within the editing window")
    target_base_count: int
    structural_variation_risk: Optional[str] = Field(None, description="low | medium | high (therapeutic track)")
    genome_coverage: Optional[float] = Field(None, description="Sub-genome coverage fraction (crop track)")


# ---------------------------------------------------------------------------
# Provenance / Manifest Models (W3C PROV + RO-Crate aligned)
# ---------------------------------------------------------------------------

class StepTrace(BaseModel):
    """Execution trace for a single pipeline step."""
    step_name: str
    start_time: datetime
    end_time: Optional[datetime] = None
    exit_status: int = 0
    docker_image: str
    command_args: list[str] = Field(default_factory=list)
    seed_used: Optional[int] = None


class InputEntity(BaseModel):
    """W3C PROV Entity — an input file or object."""
    entity_id: str
    name: str
    sha256_hash: str
    media_type: str = "application/json"
    description: Optional[str] = None


class OutputEntity(BaseModel):
    """W3C PROV Entity — a generated output artifact."""
    entity_id: str
    name: str
    sha256_hash: str
    media_type: str
    file_path: Optional[str] = None
    description: Optional[str] = None


class RunManifest(BaseModel):
    """
    The core provenance record for a CasAI design run.
    Implements RO-Crate Process Run Crate v0.4 profile.
    """

    # Identity
    run_id: UUID = Field(default_factory=uuid4, description="UUIDv4 unique run identifier")
    conforms_to: str = Field(
        default="https://w3id.org/ro/wfrun/process/0.4",
        description="RO-Crate profile URI"
    )

    # Instrument (the CasAI engine version)
    instrument_name: str = Field(default="CasAI-Core", description="Tool/model name")
    instrument_version: str = Field(default="2.0.0")
    git_sha: str = Field(..., description="Git SHA of the codebase at run time")
    docker_image: str = Field(..., description="Docker image ID used")
    app_version: str = Field(default="1.0.0")

    # Timing
    start_time: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    end_time: Optional[datetime] = None

    # Status
    status: RunStatus = Field(default=RunStatus.PENDING)

    # Inputs digest (frozen inputs)
    inputs_digest: str = Field(..., description="SHA-256 of concatenated input hashes")

    # W3C PROV — object (inputs) and result (outputs)
    object: list[InputEntity] = Field(default_factory=list)
    result: list[OutputEntity] = Field(default_factory=list)

    # Execution trace
    step_traces: list[StepTrace] = Field(default_factory=list)

    # Run configuration (stored for re-run)
    run_request: RunRequest
    prediction: Optional[DesignPrediction] = None

    # Track
    track: RunTrack

    # Benchmark flag
    benchmark_mode: bool = False

    @computed_field
    @property
    def duration_seconds(self) -> Optional[float]:
        if self.start_time and self.end_time:
            return (self.end_time - self.start_time).total_seconds()
        return None

    def as_json_ld(self) -> dict[str, Any]:
        """Serialize to W3C PROV-compatible JSON-LD."""
        return {
            "@context": [
                "https://w3id.org/ro/crate/1.1/context",
                {"prov": "http://www.w3.org/ns/prov#"}
            ],
            "@graph": [
                {
                    "@id": "./",
                    "@type": "Dataset",
                    "conformsTo": {"@id": self.conforms_to},
                    "datePublished": self.start_time.isoformat(),
                    "hasPart": [{"@id": e.entity_id} for e in self.object + self.result],
                },
                {
                    "@id": f"#run-{self.run_id}",
                    "@type": ["CreateAction", "prov:Activity"],
                    "instrument": {
                        "@type": "SoftwareApplication",
                        "name": self.instrument_name,
                        "version": self.instrument_version,
                        "identifier": self.git_sha,
                    },
                    "startTime": self.start_time.isoformat(),
                    "endTime": self.end_time.isoformat() if self.end_time else None,
                    "object": [{"@id": e.entity_id} for e in self.object],
                    "result": [{"@id": e.entity_id} for e in self.result],
                    "prov:used": [{"@id": e.entity_id} for e in self.object],
                    "prov:generated": [{"@id": e.entity_id} for e in self.result],
                },
                *[
                    {
                        "@id": e.entity_id,
                        "@type": ["File", "prov:Entity"],
                        "name": e.name,
                        "encodingFormat": e.media_type,
                        "sha256": e.sha256_hash,
                        "description": e.description,
                    }
                    for e in self.object + self.result
                ],
            ],
        }


# ---------------------------------------------------------------------------
# Diff / Comparison Models
# ---------------------------------------------------------------------------

class ManifestDiffEntry(BaseModel):
    field: str
    run_a_value: Any
    run_b_value: Any
    changed: bool


class ManifestDiff(BaseModel):
    run_a_id: UUID
    run_b_id: UUID
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    differences: list[ManifestDiffEntry]
    summary: str


# ---------------------------------------------------------------------------
# Benchmark Models
# ---------------------------------------------------------------------------

class BenchmarkResult(BaseModel):
    run_id: UUID
    track: RunTrack
    task_success: bool
    on_target_mean: float
    off_target_risk_mean: float
    completion_time_seconds: float
    model_version: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class LeaderboardEntry(BaseModel):
    rank: int
    run_id: UUID
    target_gene: str
    editor_type: BaseEditorType
    on_target_mean: float
    off_target_risk_mean: float
    percentile_specificity: float
    model_version: str
    created_at: datetime


# ---------------------------------------------------------------------------
# Export / Response Wrappers
# ---------------------------------------------------------------------------

class RunSummary(BaseModel):
    """Lightweight run listing item."""
    run_id: UUID
    status: RunStatus
    track: RunTrack
    target_gene: str
    editor_type: BaseEditorType
    start_time: datetime
    end_time: Optional[datetime]
    duration_seconds: Optional[float]
    benchmark_mode: bool


class APIResponse(BaseModel):
    success: bool = True
    message: str = "OK"
    data: Optional[Any] = None
