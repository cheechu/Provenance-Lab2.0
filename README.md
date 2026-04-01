# CasAI Provenance Lab — Backend API

A FastAPI backend for reproducible CRISPR base-editor design. Every design run is a fully auditable, comparable research object conforming to **W3C PROV** and the **RO-Crate Process Run Crate v0.4** profile.

---

## Quick Start

```bash
# 1. Create a virtual environment
python3 -m venv .venv && source .venv/bin/activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Run the server
uvicorn app.main:app --reload --port 8000
```

Interactive docs available at: **http://localhost:8000/docs**

---

## Project Structure

```
casai-provenance-lab/
├── app/
│   ├── main.py                  # FastAPI entrypoint + lifespan
│   ├── core/
│   │   └── config.py            # Settings (track, dirs, git SHA)
│   ├── models/
│   │   └── schemas.py           # All Pydantic models (RunManifest, DesignPrediction, etc.)
│   ├── routers/
│   │   └── api.py               # All API endpoints
│   └── services/
│       ├── provenance.py        # Run lifecycle, diff, leaderboard
│       └── export_service.py    # ZIP Export Pack builder
├── tests/
│   └── test_api.py              # Full test suite (pytest)
├── data/                        # Auto-created at runtime
│   ├── runs/                    # Persisted RunManifest JSON files
│   ├── exports/                 # Cached ZIP exports
│   └── benchmarks/              # benchmark_results.json
└── requirements.txt
```

---

## API Reference

### Runs

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/runs` | Initiate a new design run |
| `GET` | `/runs` | List all runs (filter by track) |
| `GET` | `/runs/{id}` | Get full RunManifest |
| `GET` | `/runs/{id}/manifest` | Get W3C PROV JSON-LD provenance record |
| `GET` | `/runs/{id}/diff?other_id=` | Structural diff of two runs |
| `POST` | `/runs/rerun/{id}` | Re-run with identical archived inputs |
| `GET` | `/runs/{id}/export.zip` | Download lab-ready Export Pack |

### Benchmarks

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/benchmarks/run` | Run in benchmark mode (writes to leaderboard) |
| `GET` | `/benchmarks/leaderboard` | Ranked leaderboard with percentile scores |

---

## Example: Create a Design Run

```bash
curl -X POST http://localhost:8000/runs \
  -H "Content-Type: application/json" \
  -d '{
    "guide_rna": {
      "sequence": "ATGCATGCATGCATGCATGC",
      "pam": "NGG",
      "target_gene": "BRCA1",
      "chromosome": "chr17",
      "position_start": 41196312,
      "position_end": 41196331,
      "strand": "+"
    },
    "editor_config": {
      "editor_type": "CBE",
      "cas_variant": "nCas9",
      "deaminase": "APOBEC3A",
      "editing_window_start": 4,
      "editing_window_end": 8,
      "algorithms": ["CFD", "MIT", "DeepCRISPR"]
    },
    "track": "genomics_research",
    "random_seed": 42,
    "benchmark_mode": false
  }'
```

## Example: Download Export Pack

```bash
curl -O http://localhost:8000/runs/{run_id}/export.zip
```

The ZIP contains:
- `run.manifest.json` — W3C PROV JSON-LD provenance record
- `report.txt` — Human-readable scoring summary with interpretability
- `guide_rna_input.json` — Frozen input (verifiable via SHA-256)
- `prediction.json` — Full scoring output (CFD, MIT, SHAP/LIME)
- `cloning_oligos.json` — Forward/reverse oligos for BsmBI vector cloning
- `validation_primers.json` — PCR primers for Sanger/NGS validation
- `protospacer.fasta` — FASTA for guide synthesis
- `provenance_passport.md` — Lab notebook markdown with re-run instructions

---

## Tracks

| Track | Key Constraint | Primary Metrics |
|-------|---------------|-----------------|
| `genomics_research` | General CRISPR research | CFD, MIT, CI bounds |
| `therapeutic` | Off-target safety + structural variation risk | CFD Score, MIT Score, SV risk |
| `crop_demo` | Polyploid genome coverage | On-target efficiency, sub-genome coverage |

---

## Provenance Model

Every run produces a `RunManifest` with:
- `run_id` — UUIDv4 unique identifier
- `inputs_digest` — SHA-256 of all frozen inputs (reproducibility guarantee)
- `git_sha` + `docker_image` — Environment snapshot
- `step_traces` — Per-step timestamps, command args, exit codes
- `object` / `result` — W3C PROV Entities (inputs + outputs)
- `conformsTo` — RO-Crate Process Run Crate v0.4 URI

To verify a run is reproducible: `POST /runs/rerun/{run_id}` and confirm `inputs_digest` matches.

---

## Running Tests

```bash
pytest tests/ -v
```

---

## v1 Non-Goals

- No clinical predictions — all outputs labeled **"in-silico hypothesis"**
- No new GPU infrastructure — scoring uses placeholder mocks until real ML is wired
- No authentication layer (add before production deployment)
