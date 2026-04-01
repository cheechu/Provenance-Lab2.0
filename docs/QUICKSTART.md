# Quick Start Guide

Get Provenance Lab running locally in 5 minutes.

## Prerequisites

- **Docker & Docker Compose** (https://docs.docker.com/compose/install/)
- **curl** or **Postman** (for testing API)

## 1. Start Services (2 min)

```bash
cd /Users/kavin/Provenance-Lab2.0

# Start all containers in background
docker-compose up -d

# Wait for postgres to be healthy
docker-compose ps postgres
# Watch for "healthy" status in the STATUS column (takes ~30s)
```

**What started**:
- PostgreSQL @ localhost:5432 (user: postgres, pass: postgres)
- Prefect Server @ http://localhost:4200
- FastAPI Backend @ http://localhost:8000
- Next.js Frontend placeholder @ http://localhost:3000

## 2. Run Database Migrations (1 min)

```bash
# Run Alembic migration
docker-compose exec backend alembic upgrade head

# Verify tables were created
docker-compose exec postgres psql -U postgres -d provenance -c "\dt"
```

Should show:
```
              List of relations
 Schema |       Name       | Type  |  Owner
--------+------------------+-------+----------
 public | run_manifests    | table | postgres
 public | runs             | table | postgres
 (2 rows)
```

## 3. Verify Services (1 min)

### FastAPI Health
```bash
curl http://localhost:8000/health
# Should return: {"status":"ok","app":"Provenance Lab API"}
```

### List Runs (initially empty)
```bash
curl http://localhost:8000/runs
# Should return: []
```

### Prefect UI
```bash
# Open in browser
open http://localhost:4200
# You should see Prefect dashboard
```

## 4. Create Your First Run (1 min)

```bash
# Create a run
curl -X POST http://localhost:8000/runs \
  -H "Content-Type: application/json" \
  -d '{
    "mode": "therapeutic",
    "pdb_filename": "sample.pdb",
    "config": {}
  }'
```

**Response** (example):
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "created_at": "2026-03-31T12:00:00.000000Z",
  "status": "pending",
  "mode": "therapeutic",
  "pdb_filename": "sample.pdb",
  "pdb_path": null,
  "config": {},
  "prefect_flow_id": "a7f4e2d9-7c1b-4e0c-a1b2-3c4d5e6f7a8b"
}
```

**Note**: The `prefect_flow_id` shows that the Prefect flow was triggered!

## 5. View Your Run

```bash
# Get the run ID from the response above, e.g., 550e8400-e29b-41d4-a716-446655440000
RUN_ID="550e8400-e29b-41d4-a716-446655440000"

# Fetch run details
curl http://localhost:8000/runs/$RUN_ID

# Get the sealed manifest (provenance record)
curl http://localhost:8000/runs/$RUN_ID/manifest
```

## 6. Check Prefect Flow Status

1. Open **http://localhost:4200** in your browser
2. Click **"Flow Runs"** in the left sidebar
3. You should see your `design_pipeline_flow` run
4. Click on it to see task execution logs

---

## Common Commands

### View Logs

```bash
# All services
docker-compose logs -f

# Specific service
docker-compose logs -f backend
docker-compose logs -f postgres
docker-compose logs -f prefect-server
```

### Database Access

```bash
# Connect to Postgres directly
docker-compose exec postgres psql -U postgres -d provenance

# Example queries
psql> SELECT id, status, mode, prefect_flow_id FROM runs;
psql> SELECT run_id, sealed_at, steps FROM run_manifests;
psql> \q  # Exit
```

### Rebuild (if you modify requirements.txt)

```bash
docker-compose down
docker-compose build --no-cache
docker-compose up -d
```

### Reset Everything (fresh start)

```bash
# Stop all containers
docker-compose down -v  # -v removes volumes (data is deleted)

# Restart
docker-compose up -d
docker-compose exec backend alembic upgrade head
```

---

## Next: Local Development (Optional)

To develop locally without Docker (for faster iteration):

```bash
cd backend

# Create virtual environment
python3.12 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Set environment
export DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/provenance
export PREFECT_API_URL=http://localhost:4200/api

# Run FastAPI with hot-reload
uvicorn app.main:app --reload

# In another terminal: run migrations
alembic upgrade head
```

---

## Troubleshooting

### "Connection refused" to Postgres
```bash
# Postgres might still be starting
docker-compose ps postgres  # Check STATUS

# Wait a bit longer, or restart
docker-compose restart postgres
```

### "Connection refused" to Prefect server
```bash
# Check if prefect-server is running
docker-compose ps prefect-server

# If it's not, start it
docker-compose restart prefect-server

# Wait for it to initialize (~30s)
docker-compose logs -f prefect-server
```

### API returns 422 Unprocessable Entity
```bash
# Likely JSON schema issue. Verify your POST body:
curl -X POST http://localhost:8000/runs \
  -H "Content-Type: application/json" \
  -d '{
    "mode": "therapeutic",
    "pdb_filename": "sample.pdb",
    "config": {}
  }'

# mode must be "therapeutic" or "crop_demo"
```

### Migrations failed
```bash
# Check migration status
docker-compose exec backend alembic current

# View migration history
docker-compose exec backend alembic history

# Downgrade one step if needed
docker-compose exec backend alembic downgrade -1

# Then try again
docker-compose exec backend alembic upgrade head
```

---

## What's Next?

- 📖 Read [IMPLEMENTATION.md](../IMPLEMENTATION.md) for architecture details
- 📋 Read [PREFECT_FLOWS.md](./PREFECT_FLOWS.md) for flow documentation
- 🔧 Implement real bio tasks in `flows/design_pipeline.py`
- 🎨 Build Next.js frontend in `frontend/`
- 📝 Add tests in `backend/tests/`
- 🚀 Deploy to cloud!

---

## Need Help?

- **API Docs**: http://localhost:8000/docs (interactive Swagger UI)
- **README**: See [README.md](../README.md) for detailed documentation
- **Docker Issues**: Check `docker-compose logs`
- **Database Issues**: Connect directly with psql to inspect

Good luck! 🚀
