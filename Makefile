.PHONY: up down logs ps backend-test backend-lint frontend-test frontend-lint schema contract ci

up:
	docker compose up --build -d

down:
	docker compose down

logs:
	docker compose logs -f --tail=100

ps:
	docker compose ps

backend-test:
	cd apps/api && python -m pytest

backend-lint:
	cd apps/api && ruff check . && ruff format --check .

frontend-test:
	cd apps/web && npm test

frontend-lint:
	cd apps/web && npm run lint && npm run typecheck

schema:
	cd apps/api && python manage.py spectacular --file ../../contracts/openapi.yaml --validate

contract:
	bash scripts/verify-contract.sh

ci: backend-lint backend-test frontend-lint frontend-test contract
