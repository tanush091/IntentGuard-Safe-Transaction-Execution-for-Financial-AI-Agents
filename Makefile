# IntentGuard research prototype

PYTHON ?= python

.PHONY: help install test test-fast run-provider run-gateway run-frontend benchmark benchmark-quick up clean

help:
	@echo "make install        Install Python dependencies"
	@echo "make test           Run the full test suite (incl. property-based safety tests)"
	@echo "make run-provider   Start the mock payment provider on :8001"
	@echo "make run-gateway    Start the IntentGuard gateway on :8000"
	@echo "make run-frontend   Start the React dashboard on :3000"
	@echo "make benchmark      Full experiment: all arms x 10 seeds x 300 scenarios"
	@echo "make benchmark-quick  Small run for a quick check"
	@echo "make up             docker compose up --build"

install:
	$(PYTHON) -m pip install -r requirements.txt

test:
	$(PYTHON) -m pytest -q

run-provider:
	$(PYTHON) -m uvicorn provider_api.main:app --host 127.0.0.1 --port 8001

run-gateway:
	$(PYTHON) -m uvicorn gateway_api.main:app --host 127.0.0.1 --port 8000

run-frontend:
	cd frontend && npm install && npm run dev

benchmark:
	$(PYTHON) -m bench run --seeds 10 --start-seed 42 --scenarios 300

benchmark-quick:
	$(PYTHON) -m bench run --seeds 2 --scenarios 60 --out experiments/results/quick

up:
	docker compose up --build

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} +
	rm -rf .pytest_cache .hypothesis
