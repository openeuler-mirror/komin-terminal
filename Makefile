PYTHON ?= python3

PKG_NAME := $(shell awk '/^%global srcname/ {print $$3; exit}' packaging/komin-terminal.spec)
VERSION := $(shell awk '/^Version:/ {print $$2; exit}' packaging/komin-terminal.spec)
RPMTOPDIR := $(CURDIR)/rpmbuild

.PHONY: install-dev build install remove test test-cov lint format typecheck check clean

install-dev:
	$(PYTHON) -m pip install -e ".[dev]"

build:
	mkdir -p $(RPMTOPDIR)/BUILD $(RPMTOPDIR)/BUILDROOT $(RPMTOPDIR)/RPMS $(RPMTOPDIR)/SOURCES $(RPMTOPDIR)/SPECS $(RPMTOPDIR)/SRPMS
	git archive --format=tar.gz --prefix=$(PKG_NAME)-$(VERSION)/ -o $(RPMTOPDIR)/SOURCES/$(PKG_NAME)-$(VERSION).tar.gz HEAD
	dnf builddep -y packaging/komin-terminal.spec
	env VIRTUAL_ENV= PATH="$$(echo "$$PATH" | tr ':' '\n' | grep -v '/\.venv/bin' | paste -sd: -)" \
		rpmbuild -ba --define "_topdir $(RPMTOPDIR)" packaging/komin-terminal.spec

install:
	@if ! ls $(RPMTOPDIR)/RPMS/noarch/*.rpm >/dev/null 2>&1; then \
		echo "Error: no built RPMs found under $(RPMTOPDIR)/RPMS. Run 'make build' first." >&2; \
		exit 1; \
	fi
	dnf install -y $(RPMTOPDIR)/RPMS/noarch/*.rpm

remove:
	dnf remove -y $(PKG_NAME) $(PKG_NAME)-data $(PKG_NAME)-help

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

clean:
	rm -rf build dist .pytest_cache .mypy_cache .ruff_cache *.egg-info rpmbuild .venv
	find . -name __pycache__ -type d -not -path './.venv/*' -prune -exec rm -rf {} +
