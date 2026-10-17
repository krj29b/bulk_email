# Note: Ensure tabs are preserved if copying manually
.PHONY: install test lint dead-code complexity audit quality-gate run-dry clean

PYTHON ?= python
PYTEST ?= pytest

install:
	$(PYTHON) -m pip install -e ".[dev]"

test:
	$(PYTEST) --cov=src/bulk_mailer --cov-report=term-missing

lint:
	ruff check src/ tests/
	mypy src/

dead-code:
	vulture src/ --min-confidence 80

complexity:
	radon cc src/ -a -nb --total-average

audit:
	pip-audit

quality-gate: lint dead-code complexity audit test

run-dry:
	$(PYTHON) -m bulk_mailer.cli \
		--tasks-xml config/samples/tasks.xml \
		--schedule-xml config/samples/schedules.xml \
		--dry-run

clean:
	rm -rf .pytest_cache .mypy_cache .ruff_cache .coverage dist build *.egg-info
