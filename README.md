# IncidentForge

IncidentForge is a web application for software incident investigation.

## Stack

- Next.js, React, TypeScript
- Django, Django REST Framework, Celery
- PostgreSQL, Redis
- Docker Compose

## Local setup

Requires Docker Engine or Docker Desktop with Compose v2.

```powershell
Copy-Item .env.example .env
# Review local configuration in .env before starting services.
docker compose up --build -d --wait
docker compose ps
```

The database host in `.env` must be `postgres` when accessed from the Compose network.

- Web UI: http://localhost:3000
- API readiness: http://localhost:8000/health/ready
- API schema: http://localhost:8000/api/v1/openapi/
- API reference: http://localhost:8000/api/v1/docs/

Stop services with `docker compose down`. This preserves the PostgreSQL volume.

## Source layout

```text
apps/web/       Next.js application
apps/api/       Django API and Celery worker
contracts/      API contract checks
scripts/        Contract validation utilities
docs/           Architecture and development notes
compose.yaml    Local service configuration
```

See [Development](docs/development.md) for checks and troubleshooting, and [Architecture](docs/architecture.md) for service boundaries.

## License

No license has been assigned.
