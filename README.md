# Provenance Lab 2.0

A monorepo for provenance-tracked bioinformatics workflows with FastAPI backend, Next.js frontend, PostgreSQL JSONB storage, and Prefect orchestration.

## Quick Start

### Prerequisites

- Docker & Docker Compose
- Python 3.12+ (for local development)
- Node.js 20+ (for frontend development)

### Environment Setup

Clone the repo and set up environment variables:

```bash
# Copy template (create one if needed)
cp .env.example .env
```

Basic `.env`:
```
DATABASE_URL=postgresql+asyncpg://postgres:postgres@postgres:5432/provenance
PREFECT_API_URL=http://prefect-server:4200/api
```

### Docker Compose Start

```bash
# Build and start all services
docker-compose up -d

# Check logs
docker-compose logs -f backend
docker-compose logs -f prefect-server
docker-compose logs -f postgres
```

Services will be available at:
- **FastAPI Docs:** http://localhost:8000/docs
- **Prefect UI:** http://localhost:4200
- **PostgreSQL:** localhost:5432 (postgres/postgres)

### Database Migrations

```bash
# Run Alembic migrations
docker-compose exec backend alembic upgrade head
```

### Verify Services

```bash
# Health check
curl http://localhost:8000/health
# Should return: {"status":"ok","app":"Provenance Lab API"}

# List runs (initially empty)
curl http://localhost:8000/runs
# Should return: []
```

## Project Structure

```
.
├── backend/                    # FastAPI app (Python)
│   ├── app/
│   │   ├── main.py            # FastAPI entry point
│   │   ├── config.py          # Settings (env-based)
│   │   ├── database.py        # Async SQLAlchemy engine & session
│   │   ├── models.py          # SQLAlchemy ORM models
│   │   ├── schemas.py         # Pydantic request/response schemas
│   │   ├── crud.py            # Database operations
│   │   └── routers/
│   │       └── runs.py        # /runs endpoints
│   ├── flows/
│   │   ├── hello.py           # Hello-world Prefect flow
│   │   └── design_pipeline.py # Main orchestration flow
│   ├── alembic/               # Database migrations
│   │   ├── env.py
│   │   ├── versions/
│   │   │   └── 0001_initial_schema.py
│   │   └── alembic.ini
│   ├── Dockerfile
│   └── requirements.txt
├── frontend/                   # Next.js app (Node)
├── test-fixtures/             # Sample files (PDB, etc.)
├── docs/                       # Specs and notes
├── docker-compose.yml
└── README.md

```

## API Endpoints

### Health & Info

- `GET /health` — Health check
- `GET /` — App info

### Runs

- `POST /runs` — Create a new run (triggers Prefect flow)
  ```json
  {
    "mode": "therapeutic",
    "pdb_filename": "sample.pdb",
    "config": {}
  }
  ```
- `GET /runs` — List all runs
- `GET /runs/{id}` — Get run details
- `GET /runs/{id}/manifest` — Get provenance manifest (JSON-LD format)

## Database Schema

### Runs Table
```sql
CREATE TABLE runs (
  id UUID PRIMARY KEY,
  created_at TIMESTAMP NOT NULL,
  status ENUM (pending, running, completed, failed) NOT NULL,
  mode ENUM (therapeutic, crop_demo) NOT NULL,
  pdb_filename VARCHAR,
  pdb_path VARCHAR,
  config JSONB NOT NULL DEFAULT '{}',
  prefect_flow_id VARCHAR
);
```

### RunManifests Table
```sql
CREATE TABLE run_manifests (
  id UUID PRIMARY KEY,
  run_id UUID NOT NULL REFERENCES runs(id) UNIQUE,
  inputs_digest VARCHAR,
  git_sha VARCHAR,
  docker_image VARCHAR,
  prefect_flow_id VARCHAR,
  created_at TIMESTAMP NOT NULL,
  sealed_at TIMESTAMP,
  steps JSONB NOT NULL DEFAULT '[]'
);
```

## Prefect Integration

The backend is configured to communicate with a Prefect server running at `http://prefect-server:4200/api`.

### Available Flows

**Hello World Flow** (`flows/hello.py`)
- Simple task-based flow for testing connectivity

**Design Pipeline** (`flows/design_pipeline.py`)
- Orchestrates the full provenance workflow
- Steps: validate_pdb → generate_grna → run_scoring → seal_manifest
- Currently stub implementations; ready for real task logic

When a run is created via `POST /runs`, the design_pipeline flow is triggered and the flow ID is stored on the Run record.

## GitHub Repository & Branch Protection (Manual Setup)

When ready to push to GitHub:

1. **Create repo** on GitHub (cheechu/Provenance-Lab2.0)
2. **Add remote**:
   ```bash
   git remote add origin https://github.com/cheechu/Provenance-Lab2.0.git
   ```
3. **Push main branch**:
   ```bash
   git branch -M main
   git push -u origin main
   ```
4. **Enable branch protection** in GitHub Settings:
   - Go to Settings → Branches → Add rule
   - Pattern: `main`
   - ✓ Require pull request reviews before merging (≥1)
   - ✓ Dismiss stale pull request approvals
   - ✓ Require status checks to pass

## Development

### Local Backend Dev (without Docker)

```bash
cd backend

# Create virtual environment
python3.12 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Set environment variables
export DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/provenance
export PREFECT_API_URL=http://localhost:4200/api

# Start FastAPI dev server
uvicorn app.main:app --reload

# In another terminal, run Alembic migrations
alembic upgrade head
```

### Local Prefect Setup

```bash
# Run Prefect server locally
prefect server start  # UI at http://localhost:4200
```

## Testing

```bash
# Run tests
pytest tests/

# Run with coverage
pytest --cov=app tests/
```

## Troubleshooting

### PostgreSQL connection refused
```bash
# Ensure postgres service is healthy
docker-compose ps postgres
# Should show healthy status
```

### Prefect server not responding
```bash
# Check if prefect-server is running
docker-compose logs prefect-server

# Restart it
docker-compose restart prefect-server
```

### Database migrations failed
```bash
# View migration status
docker-compose exec backend alembic current
docker-compose exec backend alembic history

# Downgrade if needed
docker-compose exec backend alembic downgrade -1
```

## Next Steps

1. ✅ Monorepo folder structure
2. ✅ Docker services (FastAPI, Prefect, PostgreSQL)
3. ✅ Async database layer
4. ✅ Basic CRUD endpoints
5. ✅ Prefect flow integration
6. 🔄 Implement real bio tasks (validate_pdb, generate_grna, etc.)
7. 🔄 Add authentication/authorization
8. 🔄 Build Next.js frontend
9. 🔄 Add comprehensive tests
10. 🔄 Deploy to cloud (AWS ECS, GCP Cloud Run, etc.)

## License

MIT (or your preferred license)
