# IntentGuard research prototype. Run from the repository root.

PYTHON ?= python

.PHONY: help install test run-provider run-gateway run-frontend bench-quick bench-full up down

help:
	@echo "make install       Install backend (pip) and dashboard (npm) dependencies"
	@echo "make test          Run the backend test suite (from backend/)"
	@echo "make run-provider  Start the mock payment provider on :8001"
	@echo "make run-gateway   Start the IntentGuard gateway on :8000"
	@echo "make run-frontend  Start the React dashboard on :3000"
	@echo "make bench-quick   Quick benchmark (2 seeds x 60 scenarios) -> experiments/results/quick/"
	@echo "make bench-full    Full benchmark (10 seeds x 300 scenarios) -> experiments/results/latest/"
	@echo "make up            docker compose up --build"
	@echo "make down          docker compose down"

install:
	$(PYTHON) -m pip install -r backend/requirements.txt
	cd frontend && npm install

test:
	cd backend && $(PYTHON) -m pytest -q

run-provider:
	cd backend && $(PYTHON) -m uvicorn provider_api.main:app --host 127.0.0.1 --port 8001

run-gateway:
	cd backend && $(PYTHON) -m uvicorn gateway_api.main:app --host 127.0.0.1 --port 8000

run-frontend:
	cd frontend && npm run dev

# Writes to its own folder so it never replaces the measured results in experiments/results/latest/.
bench-quick:
	cd experiments && $(PYTHON) -m bench run --seeds 2 --scenarios 60 --out results/quick

bench-full:
	cd experiments && $(PYTHON) -m bench run --seeds 10 --start-seed 42 --scenarios 300

up:
	docker compose up --build

down:
	docker compose down
