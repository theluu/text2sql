.PHONY: env up down reset logs test test-api test-web lint lint-api lint-web eval eval-smoke eval-record

env: ; test -f .env || (cp .env.example .env && sed -i.bak "s/^JWT_SECRET=.*/JWT_SECRET=$$(openssl rand -hex 32)/" .env && rm .env.bak)
up: env ; docker compose up -d --build
down: ; docker compose down
reset: ; docker compose down -v
logs: ; docker compose logs -f api bootstrap
test: test-api test-web
test-api: ; cd backend && uv run pytest -q
test-web: ; cd frontend && npx vitest run
lint: lint-api lint-web
lint-api: ; cd backend && uv run ruff check . && uv run ruff format --check . && uv run mypy app
lint-web: ; cd frontend && npm run lint && npm run typecheck

# Eval harness (runs inside the api container against the live warehouse).
SUITE ?= smoke
MODE ?= chain
eval: ; docker compose exec api python -m app.cli eval --suite $(SUITE) --mode $(MODE)
eval-smoke: ; docker compose exec api python -m app.cli eval --suite smoke --mode chain --cassette replay --gate eval/baseline.json
eval-record: ; docker compose exec api python -m app.cli eval --suite smoke --mode chain --cassette record
