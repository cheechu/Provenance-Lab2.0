"""
CasAI Provenance Lab — File Upload Service
Handles: PDB parsing, FASTA validation, annotation JSON ingestion,
         SHA-256 integrity sealing, secure storage path generation.
"""

from __future__ import annotations

import hashlib
import io
import json
import re
import uuid
from pathlib import Path
from typing import Optional

from app.core.config import settings
from app.models.upload_schemas import (
    AnnotationMetadata,
    PDBMetadata,
    UploadStatus,
    UploadedFile,
    UploadedFileType,
)

UPLOAD_DIR = Path("./data/uploads")
MAX_FILE_SIZES = {
    UploadedFileType.PDB:        50 * 1024 * 1024,   # 50 MB
    UploadedFileType.ANNOTATION: 5  * 1024 * 1024,   # 5 MB
    UploadedFileType.FASTA:      20 * 1024 * 1024,   # 20 MB
    UploadedFileType.CSV:        10 * 1024 * 1024,   # 10 MB
    UploadedFileType.VCF:        25 * 1024 * 1024,   # 25 MB
}

ALLOWED_EXTENSIONS = {
    UploadedFileType.PDB:        {".pdb", ".ent"},
    UploadedFileType.ANNOTATION: {".json"},
    UploadedFileType.FASTA:      {".fasta", ".fa", ".fna", ".ffn"},
    UploadedFileType.CSV:        {".csv", ".tsv"},
    UploadedFileType.VCF:        {".vcf"},
}


# ---------------------------------------------------------------------------
# SHA-256
# ---------------------------------------------------------------------------

def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# ---------------------------------------------------------------------------
# File type detection
# ---------------------------------------------------------------------------

def detect_file_type(filename: str, content: bytes) -> UploadedFileType:
    """Detect file type from extension and magic bytes."""
    suffix = Path(filename).suffix.lower()
    for ftype, exts in ALLOWED_EXTENSIONS.items():
        if suffix in exts:
            return ftype
    # Fallback: sniff content
    sample = content[:512].decode("utf-8", errors="ignore")
    if sample.startswith("HEADER") or "ATOM  " in sample:
        return UploadedFileType.PDB
    if sample.strip().startswith(">"):
        return UploadedFileType.FASTA
    if sample.strip().startswith("{"):
        return UploadedFileType.ANNOTATION
    raise ValueError(f"Unrecognised file type for: {filename}")


# ---------------------------------------------------------------------------
# PDB parser
# ---------------------------------------------------------------------------

def parse_pdb(content: bytes) -> tuple[PDBMetadata, list[str]]:
    """
    Extract metadata from a PDB file.
    Returns (metadata, validation_errors).
    """
    errors: list[str] = []
    text = content.decode("utf-8", errors="replace")
    lines = text.splitlines()

    title = None
    resolution = None
    chains: set[str] = set()
    residues: set[tuple[str, int]] = set()
    atom_count = 0
    organism = None
    experiment = None

    for line in lines:
        rec = line[:6].strip()

        if rec == "TITLE" and not title:
            title = line[10:].strip()

        elif rec == "REMARK":
            remark_num = line[6:10].strip()
            if remark_num == "2" and "RESOLUTION" in line and resolution is None:
                m = re.search(r"(\d+\.\d+)\s*ANGSTROM", line)
                if m:
                    resolution = float(m.group(1))
            elif remark_num == "3" and "PROGRAM" in line and experiment is None:
                if "X-RAY" in line:
                    experiment = "X-RAY DIFFRACTION"
                elif "NMR" in line:
                    experiment = "NMR"
                elif "CRYO" in line:
                    experiment = "CRYO-EM"

        elif rec == "SOURCE":
            if "ORGANISM_SCIENTIFIC" in line:
                organism = line.split("ORGANISM_SCIENTIFIC:")[-1].strip().rstrip(";")

        elif rec in ("ATOM", "HETATM"):
            atom_count += 1
            if len(line) >= 22:
                chain = line[21]
                chains.add(chain)
                try:
                    res_seq = int(line[22:26].strip())
                    residues.add((chain, res_seq))
                except ValueError:
                    pass

    # Validation
    if atom_count == 0:
        errors.append("No ATOM or HETATM records found — file may be empty or malformed")
    if not chains:
        errors.append("No chain identifiers detected")
    if resolution and resolution > 4.0:
        errors.append(f"Low resolution structure ({resolution} Å) — predictions may be unreliable")

    return PDBMetadata(
        title=title,
        resolution_a=resolution,
        chains=sorted(chains),
        residue_count=len(residues),
        atom_count=atom_count,
        organism=organism,
        experiment=experiment,
    ), errors


# ---------------------------------------------------------------------------
# FASTA parser
# ---------------------------------------------------------------------------

def parse_fasta(content: bytes) -> tuple[dict, list[str]]:
    errors: list[str] = []
    text = content.decode("utf-8", errors="replace")
    sequences: dict[str, str] = {}
    current_header = None
    current_seq: list[str] = []

    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith(">"):
            if current_header:
                sequences[current_header] = "".join(current_seq)
            current_header = line[1:].split()[0]
            current_seq = []
        else:
            current_seq.append(line.upper())

    if current_header:
        sequences[current_header] = "".join(current_seq)

    if not sequences:
        errors.append("No sequences found in FASTA file")

    # Validate nucleotide sequences
    valid_dna = set("ACGTNRYSWKMBDHV-")
    for header, seq in sequences.items():
        invalid = set(seq) - valid_dna
        if invalid:
            errors.append(f"Sequence '{header}' contains non-DNA characters: {invalid}")
        if len(seq) < 20:
            errors.append(f"Sequence '{header}' too short ({len(seq)} bp) — minimum 20 bp")

    return {
        "sequence_count": len(sequences),
        "headers": list(sequences.keys())[:10],
        "total_length_bp": sum(len(s) for s in sequences.values()),
    }, errors


# ---------------------------------------------------------------------------
# Annotation JSON parser
# ---------------------------------------------------------------------------

def parse_annotation(content: bytes) -> tuple[AnnotationMetadata, list[str]]:
    errors: list[str] = []
    try:
        data = json.loads(content.decode("utf-8"))
    except json.JSONDecodeError as e:
        return AnnotationMetadata(), [f"Invalid JSON: {e}"]

    if not isinstance(data, dict):
        errors.append("Annotation must be a JSON object at the top level")
        return AnnotationMetadata(), errors

    return AnnotationMetadata(
        target_gene=data.get("target_gene") or data.get("gene"),
        genome_build=data.get("genome_build") or data.get("assembly"),
        feature_count=len(data.get("features", [])),
        custom_keys=[k for k in data.keys() if k not in {"target_gene", "gene", "genome_build", "assembly", "features"}],
    ), errors


# ---------------------------------------------------------------------------
# Storage
# ---------------------------------------------------------------------------

def _storage_path(user_id: str, file_id: str, filename: str) -> Path:
    """Deterministic, collision-safe storage path under uploads dir."""
    suffix = Path(filename).suffix.lower()
    return UPLOAD_DIR / user_id[:8] / f"{file_id}{suffix}"


def store_file(user_id: str, file_id: str, filename: str, content: bytes) -> Path:
    path = _storage_path(user_id, file_id, filename)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def process_upload(
    user_id: str,
    filename: str,
    content: bytes,
    declared_type: Optional[UploadedFileType] = None,
) -> UploadedFile:
    """
    Validate, parse, store, and seal a file upload.
    Returns an UploadedFile record (not persisted to DB here).
    """
    file_id = str(uuid.uuid4())
    errors: list[str] = []
    metadata: dict = {}

    # Detect type
    try:
        file_type = declared_type or detect_file_type(filename, content)
    except ValueError as e:
        return UploadedFile(
            file_id=file_id, original_name=filename,
            file_type=declared_type or UploadedFileType.ANNOTATION,
            size_bytes=len(content), sha256=sha256_bytes(content),
            status=UploadStatus.REJECTED, storage_path="",
            user_id=user_id, validation_errors=[str(e)],
        )

    # Size check
    max_size = MAX_FILE_SIZES.get(file_type, 10 * 1024 * 1024)
    if len(content) > max_size:
        errors.append(f"File too large: {len(content):,} bytes (max {max_size:,} bytes for {file_type.value})")

    # Extension check
    suffix = Path(filename).suffix.lower()
    allowed = ALLOWED_EXTENSIONS.get(file_type, set())
    if allowed and suffix not in allowed:
        errors.append(f"Extension '{suffix}' not allowed for {file_type.value} (allowed: {allowed})")

    # Type-specific parsing
    if not errors:
        if file_type == UploadedFileType.PDB:
            pdb_meta, parse_errors = parse_pdb(content)
            errors.extend(parse_errors)
            metadata = pdb_meta.model_dump()

        elif file_type == UploadedFileType.FASTA:
            fasta_meta, parse_errors = parse_fasta(content)
            errors.extend(parse_errors)
            metadata = fasta_meta

        elif file_type == UploadedFileType.ANNOTATION:
            ann_meta, parse_errors = parse_annotation(content)
            errors.extend(parse_errors)
            metadata = ann_meta.model_dump()

    # Store file (even if validation errors — researcher may want to inspect)
    try:
        path = store_file(user_id, file_id, filename, content)
        storage_path = str(path)
    except Exception as e:
        errors.append(f"Storage error: {e}")
        storage_path = ""

    status = UploadStatus.REJECTED if any(
        "too large" in e or "not allowed" in e or "Invalid JSON" in e or "No ATOM" in e
        for e in errors
    ) else (UploadStatus.VALIDATED if not errors else UploadStatus.VALIDATED)

    return UploadedFile(
        file_id=file_id,
        original_name=filename,
        file_type=file_type,
        size_bytes=len(content),
        sha256=sha256_bytes(content),
        status=status,
        storage_path=storage_path,
        user_id=user_id,
        validation_errors=errors,
        metadata=metadata,
    )
