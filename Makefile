SHELL := /bin/bash
export PATH := $(HOME)/.local/bin:$(PATH)

.PHONY: help db db-down api web test migrate revision install

help:
	@echo "Targets:"
	@echo "  make db        - start Postgres in docker"
	@echo "  make db-down   - stop Postgres"
	@echo "  make install   - install backend + frontend deps"
	@echo "  make migrate   - alembic upgrade head"
	@echo "  make revision m=\"msg\"  - alembic autogenerate revision"
	@echo "  make api       - run FastAPI (uvicorn) on :8000"
	@echo "  make web       - run Vite dev server on :5173"
	@echo "  make test      - run backend pytest suite"

db:
	docker-compose up -d postgres

db-down:
	docker-compose down

install:
	cd backend && uv sync
	cd frontend && npm install

migrate:
	cd backend && uv run alembic upgrade head

revision:
	cd backend && uv run alembic revision --autogenerate -m "$(m)"

api:
	cd backend && uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

web:
	cd frontend && npm run dev

test:
	cd backend && uv run pytest -q
