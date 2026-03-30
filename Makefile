.PHONY: install test lint typecheck demo clean

install:
	pip install -e .[dev]
	playwright install chromium

test:
	python -m pytest -q

lint:
	python -m ruff check .

typecheck:
	python -m mypy chromelens

demo:
	chromelens crawl https://manishklach.github.io --output reports/demo --max-pages 10

clean:
	rm -rf reports/ __pycache__ .mypy_cache .ruff_cache .pytest_cache *.egg-info
