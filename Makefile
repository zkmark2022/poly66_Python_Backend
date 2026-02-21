.PHONY: up down dev test migrate lint format typecheck

up:
	docker-compose up -d

down:
	docker-compose down

dev:
	uv run uvicorn src.main:app --reload --port 8000

test:
	uv run pytest tests/ -v

migrate:
	uv run alembic upgrade head

migration:
	uv run alembic revision -m "$(MSG)"

lint:
	uv run ruff check src/ tests/

format:
	uv run ruff format src/ tests/

typecheck:
	uv run mypy src/
