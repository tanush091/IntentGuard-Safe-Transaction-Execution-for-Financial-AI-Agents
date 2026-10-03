# Makefile for IntentGuard Research Prototype
# Supports standard research workflows and local execution

PYTHON ?= python
VENV_PYTHON = .venv/bin/python
VENV_PY_WIN = .venv\Scripts\python.exe

.PHONY: help venv install test run-backend run-mock run-frontend demo benchmark clean

help:
	@echo "Available commands:"
	@echo "  make install        Install backend and test dependencies"
	@echo "  make test           Run all unit, integration, and safety tests"
	@echo "  make run-backend    Start the IntentGuard Gateway Backend (port 8000)"
	@echo "  make run-mock       Start the Mock Payment Service (port 8001)"
	@echo "  make run-frontend   Start the React Frontend dashboard"
	@echo "  make demo           Execute the end-to-end interactive terminal demo"
	@echo "  make benchmark      Execute the 250+ scenario empirical benchmark"
	@echo "  make clean          Clean cache files and test artifacts"

install:
	$(PYTHON) -m pip install -r requirements.txt

test:
	pytest -v tests/

run-backend:
	uvicorn backend.app.main:app --host 127.0.0.1 --port 8000 --reload

run-mock:
	uvicorn mock-payment-service.app.main:app --host 127.0.0.1 --port 8001 --reload

demo:
	$(PYTHON) scripts/run_demo.py

benchmark:
	$(PYTHON) scripts/run_experiments.py

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} +
	rm -rf .pytest_cache .coverage htmlcov
