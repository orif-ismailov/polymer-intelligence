# Polymer Intelligence — Backend image (api / worker / beat roles)
# Build context: backend/
# Single source of truth for the backend runtime image: compose builds it for the
# api, worker, and beat services, and CI builds the same file (docker build backend/).
# WR-02: the former duplicate deploy/Dockerfile.backend was removed so CI and compose
# validate one identical image.
#
# Usage via compose:
#   docker compose -f deploy/docker-compose.dev.yml up
# Usage via explicit build:
#   docker build -t pi-backend:latest backend/

FROM python:3.12-slim

# System deps needed by psycopg binary wheel (libpq) and argon2-cffi (libffi)
RUN apt-get update && apt-get install -y --no-install-recommends \
        libpq5 \
        libffi8 \
        curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy dependency manifest first (layer caching: deps rarely change)
COPY pyproject.toml ./
# Create minimal package stub so setuptools can install deps without full source
RUN mkdir -p app && touch app/__init__.py \
    && pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir ".[dev]"

# Copy application source (overwrites the stub created above)
COPY . .

# Non-root user for production safety
RUN adduser --disabled-password --gecos "" --uid 1001 appuser \
    && chown -R appuser:appuser /app
USER appuser

# Healthcheck: api role; worker/beat don't expose HTTP so override in compose
HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD curl -f http://localhost:8000/api/v1/health || exit 1

EXPOSE 8000

# Default CMD: api role (uvicorn)
# Override in compose for worker/beat roles
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
