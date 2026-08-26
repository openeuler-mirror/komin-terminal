PYTHON ?= python3

.PHONY: install-dev test test-cov lint format typecheck check docs clean

install-dev:
	$(PYTHON) -m pip install -e ".[dev]"

test:
	$(PYTHON) -m pytest

test-cov:
	$(PYTHON) -m pytest --cov --cov-report=term-missing

lint:
	$(PYTHON) -m ruff check komin_terminal tests

format:
	$(PYTHON) -m ruff format komin_terminal tests
	$(PYTHON) -m ruff check --fix komin_terminal tests

typecheck:
	$(PYTHON) -m mypy komin_terminal

check: lint typecheck test

docs:
	$(MAKE) -C docs html

clean:
	rm -rf build dist .pytest_cache .mypy_cache .ruff_cache *.egg-info
