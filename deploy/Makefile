.PHONY: install test lint clean run

install:
	pip install -e ".[dev,llm]"

test:
	pytest

lint:
	black --check deal_finder tests
	isort --check deal_finder tests

format:
	black deal_finder tests
	isort deal_finder tests

clean:
	rm -rf build dist *.egg-info
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete

run:
	python -m deal_finder.main --config config/config.yaml
