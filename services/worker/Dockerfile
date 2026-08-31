FROM python:3.14-slim AS build

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /app
RUN python -m pip install --no-cache-dir uv==0.11.28
COPY pyproject.toml uv.lock README.md ./
COPY src ./src
RUN uv sync --locked --no-dev --no-editable

FROM python:3.14-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH" \
    ROMANPICS_PREVIEW_DIR=/previews

WORKDIR /app
COPY --from=build /app/.venv /app/.venv
RUN useradd --create-home --uid 10001 worker \
    && mkdir -p /data /previews \
    && chown -R worker:worker /data /previews

USER worker
VOLUME ["/data", "/previews"]
STOPSIGNAL SIGTERM
ENTRYPOINT ["romanpics-worker"]
CMD ["--help"]
