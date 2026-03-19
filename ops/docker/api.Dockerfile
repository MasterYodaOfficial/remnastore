FROM python:3.12-slim
WORKDIR /app

ENV UV_CACHE_DIR=/tmp/uv-cache

RUN pip install --no-cache-dir -U pip uv
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

# uv creates .venv by default; add it to PATH
ENV PATH="/app/.venv/bin:${PATH}"

COPY common ./common
COPY alembic.ini ./
COPY apps/api/alembic ./alembic
COPY apps/api/app ./app
COPY ops/docker/api.entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

CMD ["/app/entrypoint.sh"]
