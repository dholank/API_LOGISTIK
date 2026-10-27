ARG PYTHON_IMAGE=python:3.15.2-slim@sha256:197f6622a70b727a4e61bdac13a73b4e2b914b896aa5a729ceb1f45a09bde5fa
FROM ghcr.io/astral-sh/uv:0.13.5@sha256:32a7bb39b496babbd997b0a39a4d66c126bdaf5661b302bf6f06abda8deca6ff AS uv
FROM ${PYTHON_IMAGE} AS python-base
RUN python -c "import sys; assert sys.version_info[:3] == (3, 15, 2), sys.version"

FROM python-base AS builder

ENV UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
WORKDIR /app
COPY --from=uv /uv /usr/local/bin/uv
COPY pyproject.toml uv.lock README.md ./
COPY src/ ./src/
RUN uv sync --locked --no-dev --no-editable --no-python-downloads

FROM builder AS offline-tests
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 COVERAGE_FILE=/tmp/.coverage
RUN uv sync --locked --no-editable --no-python-downloads
COPY tests/ ./tests/
COPY scripts/ ./scripts/
COPY database/ ./database/
COPY docs/ ./docs/
COPY .python-version ./
CMD ["python", "-m", "pytest", "-q", "-p", "no:cacheprovider", "--basetemp=/tmp/api-logistik-pytest", "--cov=api_logistik", "--cov-report=term-missing"]

FROM python-base AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH" \
    BIND_HOST=0.0.0.0 \
    PORT=8000
WORKDIR /app
RUN groupadd --gid 10001 api \
    && useradd --uid 10001 --gid 10001 --no-create-home --no-log-init \
        --shell /usr/sbin/nologin api
COPY --from=builder /app/.venv /app/.venv
USER 10001:10001
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD ["python", "-c", "import urllib.request; r = urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health/live', timeout=3); assert r.status == 200"]
CMD ["python", "-m", "api_logistik"]
