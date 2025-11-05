.PHONY: install install-dev fmt lint test

install:
	python -m pip install -r requirements/base.txt

install-dev: install
	python -m pip install -r requirements/dev.txt

fmt:
	ruff check src tests --fix
	black src tests

lint:
	ruff check src tests
	mypy src

test:
	python -m pytest
