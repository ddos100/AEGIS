# syntax=docker/dockerfile:1.6
FROM python:3.12-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# System dependencies:
#   build-essential / python3-dev → compile pyahocorasick C extension
#   libpq-dev                     → psycopg2 build headers
#   curl                          → used by HEALTHCHECK
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential python3-dev libpq-dev curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# IMPORTANT: copy the full source BEFORE installing.
# `pip install -e ".[dev]"` resolves the hatchling build backend's
# `packages = ["app"]` setting at install time, which requires the
# `app/` directory to already exist on disk. The previous Dockerfile
# copied only pyproject.toml first and then ran the install, which
# failed because the editable target wasn't yet on disk.
COPY . .

# BuildKit cache mount keeps the pip wheel cache between rebuilds —
# re-installs stay fast even without splitting the dep layer.
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install -e ".[dev]"

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS http://localhost:8000/v1/health || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
