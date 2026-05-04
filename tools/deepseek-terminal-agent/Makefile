.PHONY: setup test lint format run docker-build docker-run demo

setup:
	python -m pip install -U pip
	pip install -e ".[dev]"

test:
	pytest -q

lint:
	ruff check src tests

format:
	ruff format src tests

run:
	deepseek-agent chat

docker-build:
	docker compose build

docker-run:
	docker compose run --rm deepseek-agent

demo:
	deepseek-agent run "Run pwd, list files, and summarize the repository structure."
