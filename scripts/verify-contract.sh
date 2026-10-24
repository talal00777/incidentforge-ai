#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

(
  cd "$repo_root/apps/api"
  python manage.py spectacular --file "$repo_root/contracts/generated/openapi.yaml" --validate
)
(
  cd "$repo_root/apps/web"
  npm run generate:api
  npm run typecheck
)

python "$repo_root/scripts/check_api_surface.py"
test -s "$repo_root/contracts/generated/openapi.yaml"
test -s "$repo_root/apps/web/src/generated/api.d.ts"
printf 'OpenAPI validation and TypeScript generation completed.\n'
