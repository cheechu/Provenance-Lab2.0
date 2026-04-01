"""
CasAI Provenance Lab — ORM / Database Models
Replaces flat JSON file storage with SQLAlchemy async tables.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean, DateTime, Float, ForeignKey, Index,
    Integer, String, Text, UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _uuid() -> str:
    return str(uuid.uuid4())


# ---------------------------------------------------------------------------
# User
# ---------------------------------------------------------------------------

class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_superuser: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)

    api_keys: Mapped[list[APIKey]] = relationship("APIKey", back_populates="user", cascade="all, delete-orphan")
    runs: Mapped[list[Run]] = relationship("Run", back_populates="user", cascade="all, delete-orphan")
    refresh_tokens: Mapped[list[RefreshToken]] = relationship("RefreshToken", back_populates="user", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<User id={self.id} email={self.email}>"


# ---------------------------------------------------------------------------
# API Key
# ---------------------------------------------------------------------------

class APIKey(Base):
    __tablename__ = "api_keys"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)        # human label e.g. "CI pipeline"
    key_prefix: Mapped[str] = mapped_column(String(16), nullable=False)   # first 8 chars for lookup
    key_hash: Mapped[str] = mapped_column(String(255), nullable=False)    # bcrypt hash of full key
    scopes: Mapped[str] = mapped_column(String(255), default="read:runs write:runs")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    request_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    user: Mapped[User] = relationship("User", back_populates="api_keys")

    __table_args__ = (
        Index("ix_api_keys_prefix", "key_prefix"),
    )

    def __repr__(self) -> str:
        return f"<APIKey id={self.id} name={self.name} prefix={self.key_prefix}>"


# ---------------------------------------------------------------------------
# Refresh Token
# ---------------------------------------------------------------------------

class RefreshToken(Base):
    __tablename__ = "refresh_tokens"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    token_hash: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    user_agent: Mapped[str | None] = mapped_column(String(255), nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)

    user: Mapped[User] = relationship("User", back_populates="refresh_tokens")


# ---------------------------------------------------------------------------
# Run  (replaces flat JSON files in data/runs/)
# ---------------------------------------------------------------------------

class Run(Base):
    __tablename__ = "runs"

    # Identity
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)

    # Status / timing
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False, index=True)
    track: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Provenance / environment
    git_sha: Mapped[str] = mapped_column(String(40), nullable=False)
    docker_image: Mapped[str] = mapped_column(String(120), nullable=False)
    app_version: Mapped[str] = mapped_column(String(20), default="1.0.0")
    inputs_digest: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    random_seed: Mapped[int] = mapped_column(Integer, default=42)
    benchmark_mode: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Guide RNA
    guide_sequence: Mapped[str] = mapped_column(String(20), nullable=False)
    guide_pam: Mapped[str] = mapped_column(String(10), nullable=False)
    target_gene: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    chromosome: Mapped[str | None] = mapped_column(String(20), nullable=True)
    position_start: Mapped[int | None] = mapped_column(Integer, nullable=True)
    position_end: Mapped[int | None] = mapped_column(Integer, nullable=True)
    strand: Mapped[str | None] = mapped_column(String(1), nullable=True)

    # Editor config
    editor_type: Mapped[str] = mapped_column(String(10), nullable=False)   # CBE | ABE
    cas_variant: Mapped[str] = mapped_column(String(30), default="nCas9")
    deaminase: Mapped[str | None] = mapped_column(String(30), nullable=True)
    editing_window_start: Mapped[int] = mapped_column(Integer, default=4)
    editing_window_end: Mapped[int] = mapped_column(Integer, default=8)
    algorithms: Mapped[str] = mapped_column(String(120), default="CFD,MIT")  # comma-separated

    # Prediction results (JSON blobs stored as Text)
    scores_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    bystanders_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    explanations_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    step_traces_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Aggregate metrics (denormalized for fast leaderboard queries)
    cfd_on_target: Mapped[float | None] = mapped_column(Float, nullable=True, index=True)
    cfd_off_target: Mapped[float | None] = mapped_column(Float, nullable=True)
    mit_on_target: Mapped[float | None] = mapped_column(Float, nullable=True)
    mit_off_target: Mapped[float | None] = mapped_column(Float, nullable=True)
    on_target_mean: Mapped[float | None] = mapped_column(Float, nullable=True, index=True)
    off_target_mean: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Track-specific
    structural_variation_risk: Mapped[str | None] = mapped_column(String(10), nullable=True)
    genome_coverage: Mapped[float | None] = mapped_column(Float, nullable=True)

    user: Mapped[User | None] = relationship("User", back_populates="runs")

    __table_args__ = (
        Index("ix_runs_gene_track", "target_gene", "track"),
        Index("ix_runs_benchmark", "benchmark_mode", "on_target_mean"),
    )

    def __repr__(self) -> str:
        return f"<Run id={self.id} gene={self.target_gene} status={self.status}>"
