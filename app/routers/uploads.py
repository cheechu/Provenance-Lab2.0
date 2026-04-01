"""
CasAI Provenance Lab — Upload Router
POST /uploads              — upload a PDB, FASTA, annotation JSON, CSV, or VCF
GET  /uploads/{file_id}    — retrieve upload metadata
POST /uploads/{file_id}/attach/{run_id} — attach an uploaded file to a run
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status

from app.core.dependencies import require_scope
from app.models.db_models import User
from app.models.upload_schemas import UploadedFileType, UploadResponse
from app.services.upload_service import process_upload

upload_router = APIRouter(prefix="/uploads", tags=["Uploads"])

# In-memory store for demo (replace with DB table in production)
_upload_store: dict[str, dict] = {}


@upload_router.post(
    "",
    response_model=UploadResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload a PDB, FASTA, annotation JSON, CSV, or VCF file",
    description=(
        "Accepts multipart/form-data. Files are validated, parsed, "
        "SHA-256 sealed, and stored. Returns metadata and any validation warnings.\n\n"
        "**Supported types:** PDB (≤50 MB), FASTA (≤20 MB), "
        "annotation JSON (≤5 MB), CSV (≤10 MB), VCF (≤25 MB)"
    ),
)
async def upload_file(
    file: UploadFile = File(..., description="File to upload"),
    file_type: Optional[UploadedFileType] = Form(None, description="Override auto-detected file type"),
    user: User = Depends(require_scope("write:runs")),
) -> UploadResponse:
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")

    result = process_upload(
        user_id=user.id,
        filename=file.filename or "upload",
        content=content,
        declared_type=file_type,
    )

    # Store in memory (swap for DB in production)
    _upload_store[result.file_id] = result.model_dump()

    return UploadResponse(
        file_id=result.file_id,
        original_name=result.original_name,
        file_type=result.file_type,
        size_bytes=result.size_bytes,
        sha256=result.sha256,
        status=result.status,
        metadata=result.metadata,
        validation_errors=result.validation_errors,
    )


@upload_router.get(
    "/{file_id}",
    response_model=UploadResponse,
    summary="Get upload metadata by file_id",
)
def get_upload(
    file_id: str,
    user: User = Depends(require_scope("read:runs")),
) -> UploadResponse:
    record = _upload_store.get(file_id)
    if not record:
        raise HTTPException(status_code=404, detail=f"Upload {file_id} not found")
    if record["user_id"] != user.id and not user.is_superuser:
        raise HTTPException(status_code=403, detail="Forbidden")
    return UploadResponse(**{k: record[k] for k in UploadResponse.model_fields})


@upload_router.get(
    "",
    response_model=list[UploadResponse],
    summary="List all uploads for current user",
)
def list_uploads(user: User = Depends(require_scope("read:runs"))) -> list[UploadResponse]:
    return [
        UploadResponse(**{k: v[k] for k in UploadResponse.model_fields})
        for v in _upload_store.values()
        if v["user_id"] == user.id
    ]


@upload_router.delete(
    "/{file_id}",
    status_code=status.HTTP_200_OK,
    summary="Delete an uploaded file",
)
def delete_upload(file_id: str, user: User = Depends(require_scope("write:runs"))) -> dict:
    record = _upload_store.get(file_id)
    if not record:
        raise HTTPException(status_code=404, detail="Upload not found")
    if record["user_id"] != user.id and not user.is_superuser:
        raise HTTPException(status_code=403, detail="Forbidden")
    import os
    try:
        os.remove(record["storage_path"])
    except FileNotFoundError:
        pass
    del _upload_store[file_id]
    return {"message": "File deleted"}
