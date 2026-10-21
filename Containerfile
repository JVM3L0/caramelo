# Works with both `podman build` and `docker build` (compose.yaml points here).
FROM docker.io/library/python:3.13-slim

COPY --from=ghcr.io/astral-sh/uv:0.13.2 /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Dependencies first so code changes don't invalidate this layer.
COPY pyproject.toml uv.lock .python-version ./
RUN uv sync --locked --no-dev --no-install-project

COPY README.md ./
COPY src ./src
RUN uv sync --locked --no-dev

RUN useradd --system --uid 10001 caramelo
USER caramelo

ENV PATH="/app/.venv/bin:$PATH"
ENTRYPOINT ["caramelo"]
