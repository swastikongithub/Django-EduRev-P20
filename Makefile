# LPU Reserve — common tasks. Uses the project virtualenv when present.
PY ?= $(if $(wildcard .venv/Scripts/python.exe),.venv/Scripts/python,$(if $(wildcard .venv/bin/python),.venv/bin/python,python))

.PHONY: dev devdb migrate seed test test-fast test-race lint fmt check up down logs loadtest openapi

devdb:        ## start the local PostgreSQL cluster (scripts/devdb.sh init on first run)
	scripts/devdb.sh start

migrate:
	$(PY) manage.py migrate

dev: migrate  ## run the app locally (Celery tasks eager)
	CELERY_TASK_ALWAYS_EAGER=1 DEBUG=1 DEMO_MODE=1 $(PY) manage.py runserver

seed:         ## load demo data (idempotent; --reset to rebuild)
	$(PY) manage.py seed_demo

test:         ## full suite including the 500-attempt concurrency proof
	$(PY) -m pytest

test-fast:    ## everything except the concurrency stampede
	$(PY) -m pytest -m "not concurrency"

test-race:    ## only the concurrency proofs (500 attempts; RAW_CONCURRENCY_ATTEMPTS=500 for the constraint-only run)
	$(PY) -m pytest -m concurrency -v

lint:
	$(PY) -m ruff check .
	$(PY) -m ruff format --check .

fmt:
	$(PY) -m ruff format .
	$(PY) -m ruff check --fix .

check:        ## Django system + migration checks
	$(PY) manage.py check
	$(PY) manage.py makemigrations --check --dry-run

openapi:      ## regenerate docs/openapi.yaml
	$(PY) manage.py spectacular --file docs/openapi.yaml --validate

up:
	docker compose up --build -d

down:
	docker compose down

logs:
	docker compose logs -f web worker beat

loadtest:     ## see loadtest/README.md for the required environment variables
	locust -f loadtest/locustfile.py --headless -u 500 -r 100 --host http://localhost:8000
