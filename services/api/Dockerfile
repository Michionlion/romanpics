FROM python:3.14-slim AS build

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /app
RUN python -m pip install --no-cache-dir uv==0.11.28
COPY pyproject.toml uv.lock README.md ./
COPY romanpics_api ./romanpics_api
RUN uv sync --locked --no-dev --no-editable

FROM python:3.14-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH"

RUN addgroup --system romanpics && adduser --system --ingroup romanpics romanpics
WORKDIR /app

COPY --from=build /app/.venv /app/.venv
COPY alembic.ini ./
COPY alembic ./alembic
COPY manifests ./manifests

USER romanpics
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
  CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=2)"]
CMD ["uvicorn", "romanpics_api.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
