# API contracts

Django REST Framework produces the OpenAPI schema. `api-surface.json` defines allowed API paths for contract-policy checks.

Generate the schema after installing backend dependencies:

```bash
cd apps/api
python manage.py spectacular --file ../../contracts/generated/openapi.yaml --validate
```

Generate TypeScript declarations from `apps/web`:

```bash
npm run generate:api
```

Run `bash scripts/verify-contract.sh` from the repository root for contract verification. Generated declarations and schemas are ignored by Git.
