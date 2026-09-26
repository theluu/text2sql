.PHONY: env up down reset logs test-api lint-api

env: ; test -f .env || (cp .env.example .env && sed -i.bak "s/^JWT_SECRET=.*/JWT_SECRET=$$(openssl rand -hex 32)/" .env && rm .env.bak)
up: env ; docker compose up -d --build
down: ; docker compose down
reset: ; docker compose down -v
logs: ; docker compose logs -f api bootstrap
test-api: ; cd backend && uv run pytest -q
lint-api: ; cd backend && uv run ruff check . && uv run ruff format --check . && uv run mypy app
