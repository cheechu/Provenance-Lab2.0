from prefect import flow, task
from typing import Optional
from datetime import datetime


@task
def validate_pdb(filename: str) -> dict:
    """Validate PDB file. Stub implementation."""
    print(f"[Task] validate_pdb: not implemented for {filename}")
    return {
        "filename": filename,
        "valid": True,
        "timestamp": datetime.utcnow().isoformat(),
    }


@task
def generate_grna(pdb_filename: str, mode: str) -> dict:
    """Generate gRNA sequences. Stub implementation."""
    print(f"[Task] generate_grna: not implemented for {pdb_filename} (mode={mode})")
    return {
        "sequences": ["GGGCGATGATGATGATGATGA", "TTTTCCCCGGGGAAAATTTTC"],
        "count": 2,
        "timestamp": datetime.utcnow().isoformat(),
    }


@task
def run_scoring(sequences: list) -> dict:
    """Run scoring engine on sequences. Stub implementation."""
    print(f"[Task] run_scoring: not implemented for {len(sequences)} sequences")
    return {
        "scores": [0.95, 0.87],
        "top_sequence": sequences[0],
        "timestamp": datetime.utcnow().isoformat(),
    }


@task
def seal_manifest(run_id: str, results: dict) -> dict:
    """Seal the manifest with provenance info. Stub implementation."""
    print(f"[Task] seal_manifest: not implemented for run {run_id}")
    return {
        "sealed": True,
        "run_id": run_id,
        "timestamp": datetime.utcnow().isoformat(),
    }


@flow
def design_pipeline_flow(
    run_id: str,
    pdb_filename: str,
    mode: str,
) -> dict:
    """
    Design pipeline flow: orchestrates the full provenance-tracked workflow.
    
    Flow steps:
    1. Validate input PDB file
    2. Generate gRNA candidates
    3. Run scoring engine
    4. Seal manifest with results
    
    Args:
        run_id: Unique run identifier
        pdb_filename: Input PDB file name
        mode: Execution mode (therapeutic or crop_demo)
    
    Returns:
        Flow results dict with sealed manifest
    """
    print(f"[Flow] design_pipeline_flow starting for run {run_id}")
    
    # Step 1: Validate PDB
    pdb_info = validate_pdb(pdb_filename)
    
    # Step 2: Generate gRNA
    grna_results = generate_grna(pdb_filename, mode)
    
    # Step 3: Score results
    scoring_results = run_scoring(grna_results["sequences"])
    
    # Step 4: Seal manifest
    final_result = seal_manifest(run_id, {
        "pdb": pdb_info,
        "grna": grna_results,
        "scores": scoring_results,
    })
    
    print(f"[Flow] design_pipeline_flow completed for run {run_id}")
    return final_result
