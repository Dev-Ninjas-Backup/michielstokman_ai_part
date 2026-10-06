# Use Python 3.13 slim as the base image
FROM python:3.13-slim

# Install system dependencies needed for compiling psycopg2 and other packages
RUN apt-get update && apt-get install -y \
    libpq-dev \
    gcc \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Install uv entirely correctly from the official Docker image
COPY --from=ghcr.io/astral-sh/uv:0.4 /uv /uvx /bin/

# Set working directory
WORKDIR /app

# Enable bytecode compilation to improve startup time
ENV UV_COMPILE_BYTECODE=1
ENV UV_LINK_MODE=copy

# 1. Install dependencies first for better caching
# We mount the cache so repeat builds are lightning fast
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --frozen --no-install-project --no-dev

# 2. Copy the actual application files
ADD . /app

# 3. Finalize the uv environment (installs the actual project if applicable)
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

# Place the uv virtual environment executables at the front of the PATH
# This means we can just type 'uvicorn' instead of 'uv run uvicorn'
ENV PATH="/app/.venv/bin:$PATH"

# Chromium + OS libraries for the isolated HTML cover-template screenshot route.
# `--with-deps` is `playwright install-deps` + `playwright install chromium`.
ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright
RUN playwright install --with-deps chromium

# Expose the API port
EXPOSE 8000

# Start script: Run the Alembic migrations FIRST, and only if successful, start Uvicorn
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
