# hex-editor justfile

set shell := ["bash", "-cu"]

default:
    @just --list

run *args:
    uv run python -m hexmapper {{ args }}

lint:
    uv run ruff check src/ tests/
    uv run mypy src/

fmt:
    uv run ruff format src/ tests/
    uv run ruff check --fix src/ tests/

check:
    uv run ruff format --check src/ tests/
    uv run ruff check src/ tests/
    uv run mypy src/

test *args:
    uv run pytest {{ args }}

test-cov:
    uv run pytest --cov=src/ --cov-report=term-missing

clean:
    rm -rf dist/ build/ .mypy_cache/ .pytest_cache/ .ruff_cache/
    find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
