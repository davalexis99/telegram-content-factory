.PHONY: lint typecheck test ci

lint:
	ruff check src/

typecheck:
	mypy src/ --ignore-missing-imports

test:
	pytest tests/ -v --cov=src --cov-report=term-missing

ci: lint typecheck test
