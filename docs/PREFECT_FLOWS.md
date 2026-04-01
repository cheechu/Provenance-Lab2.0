# Prefect Flows Documentation

## Overview

The backend integrates **Prefect 3.0** as the orchestration layer for all bioinformatics workflows. Flows are triggered by the FastAPI `POST /runs` endpoint and manage the entire provenance-tracked design pipeline.

---

## Available Flows

### 1. Hello World Flow (`flows/hello.py`)

**Purpose**: Test Prefect server connectivity  
**Status**: ✅ Complete & working

```python
@flow
def hello_world():
    """Simple hello-world flow to verify Prefect server connection."""
    result = hello_world_task()
    return result
```

**Usage**:
```bash
# Run locally
python -m flows.hello

# Or trigger via API (future endpoint)
POST /flows/hello/run
```

**Output**: Logs "Hello from Prefect! 🎉"

---

### 2. Design Pipeline Flow (`flows/design_pipeline.py`)

**Purpose**: Orchestrate the full CRISPR design workflow  
**Status**: ✅ Flow structure complete, tasks are stubs

```python
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
    """
```

#### Task: `validate_pdb(filename: str)`
- **Purpose**: Validate input PDB file format and structure
- **Inputs**: PDB filename
- **Outputs**: Validation status, file metadata
- **Status**: 🔴 Stub (returns mock data)

```python
@task
def validate_pdb(filename: str) -> dict:
    """Validate PDB file. Stub implementation."""
    return {
        "filename": filename,
        "valid": True,
        "timestamp": datetime.utcnow().isoformat(),
    }
```

#### Task: `generate_grna(pdb_filename: str, mode: str)`
- **Purpose**: Generate gRNA candidate sequences using BioPython
- **Inputs**: PDB filename, mode (therapeutic/crop_demo)
- **Outputs**: List of gRNA sequences, count
- **Status**: 🔴 Stub (returns mock data)

```python
@task
def generate_grna(pdb_filename: str, mode: str) -> dict:
    """Generate gRNA sequences. Stub implementation."""
    return {
        "sequences": ["GGGCGATGATGATGATGATGA", "TTTTCCCCGGGGAAAATTTTC"],
        "count": 2,
        "timestamp": datetime.utcnow().isoformat(),
    }
```

#### Task: `run_scoring(sequences: list)`
- **Purpose**: Score gRNA candidates using the scoring engine
- **Inputs**: List of gRNA sequences
- **Outputs**: Scores, top candidate
- **Status**: 🔴 Stub (returns mock data)

```python
@task
def run_scoring(sequences: list) -> dict:
    """Run scoring engine on sequences. Stub implementation."""
    return {
        "scores": [0.95, 0.87],
        "top_sequence": sequences[0],
        "timestamp": datetime.utcnow().isoformat(),
    }
```

#### Task: `seal_manifest(run_id: str, results: dict)`
- **Purpose**: Create sealed provenance manifest with all results
- **Inputs**: Run ID, aggregated results from all tasks
- **Outputs**: Sealed manifest
- **Status**: 🔴 Stub (returns mock data)

```python
@task
def seal_manifest(run_id: str, results: dict) -> dict:
    """Seal the manifest with provenance info. Stub implementation."""
    return {
        "sealed": True,
        "run_id": run_id,
        "timestamp": datetime.utcnow().isoformat(),
    }
```

---

## Flow Execution & Provenance Tracking

### How It Works

1. **Trigger**: User calls `POST /runs` with mode, pdb_filename, config
2. **Backend Creates Run**: FastAPI endpoint creates a `Run` record in database
3. **Flow Submission**: Design pipeline flow is submitted to Prefect server
4. **Store Flow ID**: The returned `flow_run.id` is saved on the Run record (`prefect_flow_id`)
5. **Task Execution**: Prefect orchestrates tasks with retry logic, logging, monitoring
6. **Manifest Sealing**: Final task captures all intermediate results

### Example Request
```bash
curl -X POST http://localhost:8000/runs \
  -H "Content-Type: application/json" \
  -d '{
    "mode": "therapeutic",
    "pdb_filename": "1234.pdb",
    "config": {
      "scoring_threshold": 0.8
    }
  }'
```

### Response
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "created_at": "2026-03-31T12:00:00Z",
  "status": "pending",
  "mode": "therapeutic",
  "pdb_filename": "1234.pdb",
  "config": { "scoring_threshold": 0.8 },
  "prefect_flow_id": "a7f4e2d9-7c1b-4e0c-a1b2-3c4d5e6f7a8b"
}
```

---

## Prefect Server Integration

### Configuration

**Environment Variables**:
```bash
PREFECT_API_URL=http://prefect-server:4200/api
PREFECT_HOME=/app/.prefect
```

**Docker Compose Service**:
```yaml
prefect-server:
  image: prefecthq/prefect:3-latest
  command: prefect server start
  ports:
    - "4200:4200"
  depends_on:
    postgres:
      condition: service_healthy
```

### Accessing Prefect UI

- **URL**: http://localhost:4200
- **Features**:
  - Flow run history and status
  - Task execution logs
  - Error tracking and retries
  - Deployment configuration
  - Schedule management (future)

---

## Implementing Real Tasks

### Example: Replace `validate_pdb` Stub

**Before** (stub):
```python
@task
def validate_pdb(filename: str) -> dict:
    print(f"[Task] validate_pdb: not implemented for {filename}")
    return {"filename": filename, "valid": True, "timestamp": ...}
```

**After** (real):
```python
from Bio import PDB

@task
def validate_pdb(pdb_path: str) -> dict:
    """Validate PDB file using BioPython."""
    try:
        parser = PDB.PDBParser(QUIET=True)
        structure = parser.get_structure("protein", pdb_path)
        
        # Collect validation metrics
        ppb = PDB.PPBuilder()
        pp_list = ppb.build_peptides(structure)
        num_chains = len([c for c in structure.get_chains()])
        
        return {
            "filename": pdb_path,
            "valid": True,
            "num_chains": num_chains,
            "num_residues": sum(len(pp) for pp in pp_list),
            "timestamp": datetime.utcnow().isoformat(),
        }
    except Exception as e:
        return {
            "filename": pdb_path,
            "valid": False,
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat(),
        }
```

### Best Practices

1. **Idempotency**: Tasks should be safe to retry
2. **Logging**: Use `logger` from prefect for visibility
3. **State Serialization**: Return JSON-serializable dicts (for database storage)
4. **Error Handling**: Catch exceptions, return error state (don't raise)
5. **Dependencies**: Pin versions in requirements.txt

---

## Testing Flows Locally

### Run Hello World
```bash
cd backend
python -m flows.hello
```

### Run Design Pipeline
```bash
python -c "
import asyncio
from flows.design_pipeline import design_pipeline_flow

result = asyncio.run(design_pipeline_flow(
    run_id='test-123',
    pdb_filename='sample.pdb',
    mode='therapeutic'
))
print(result)
"
```

### With Local Prefect Server
```bash
# Terminal 1: Start Prefect server
prefect server start

# Terminal 2: Run flow (will register with server)
python -m flows.hello
```

---

## Future Enhancements

- [ ] Add Prefect deployments for scheduled runs
- [ ] Implement flow versioning & git-aware deployments
- [ ] Add custom concurrency limits per task
- [ ] Integrate with Gemini API for design tasks
- [ ] Store flow artifacts (PDB, gRNA lists) in S3/GCS
- [ ] Add flow failure notifications (email, Slack)
- [ ] Implement flow state machine (pending → running → sealed)
- [ ] Support flow parameters from RunManifest.config

---

## Troubleshooting

### "Connection refused" to Prefect server
```bash
# Check if prefect-server is running
docker-compose logs prefect-server

# Restart
docker-compose restart prefect-server
```

### Flow appears stuck in "Running"
```bash
# Check task logs in Prefect UI
# Or query directly via Prefect CLI
prefect flow-run ls
prefect flow-run inspect <flow_run_id>
```

### Task output not stored
- Ensure task returns JSON-serializable dict
- Check database connectivity
- Verify `prefect_flow_id` is set on Run record

---

## References

- [Prefect 3.0 Docs](https://docs.prefect.io)
- [Prefect Flows & Tasks](https://docs.prefect.io/concepts/flows/)
- [Prefect Server](https://docs.prefect.io/guides/deployment/)
- [BioPython PDB](https://biopython.org/wiki/Documentation)
