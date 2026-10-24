# Development

Run commands from the repository root unless noted otherwise.

## Services

```powershell
docker compose up --build -d --wait
docker compose ps
docker compose logs api --tail=100
docker compose logs web --tail=100
```

After changing frontend source for the production container:

```powershell
docker compose build web
docker compose up -d --no-deps --force-recreate web
```

The frontend Dockerfile must copy `public/` into the runtime image so static assets, including SVG logos, are served.

## Checks

```powershell
docker compose exec -T api python manage.py check
docker compose exec -T api python manage.py migrate --check
```

From `apps/web`, with development dependencies installed:

```powershell
npm run lint
npm run typecheck
npm test
npm run build
```

With the frontend running locally and Playwright's Chromium installed:

```powershell
npx playwright test e2e/accessibility.spec.ts
```

Run backend tests and linting in an environment with backend development dependencies installed:

```bash
cd apps/api
ruff check .
ruff format --check .
pytest
```

The accessibility test checks automatically detectable issues; keyboard and screen-reader review are still required for UI changes.

## Local cleanup

`docker compose down` stops the stack without deleting stored database data. Do not use `docker compose down --volumes` unless you intend to delete the PostgreSQL volume.
