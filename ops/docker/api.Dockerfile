FROM python:3.12-slim
WORKDIR /app

ENV UV_CACHE_DIR=/tmp/uv-cache

RUN pip install --no-cache-dir -U pip uv
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

# uv creates .venv by default; add it to PATH
ENV PATH="/app/.venv/bin:${PATH}"

COPY common ./common
COPY packages/locales ./packages/locales
COPY alembic.ini ./
COPY apps/api/alembic ./alembic
COPY apps/api/app ./app
COPY scripts/legacy_migration.py ./scripts/legacy_migration.py
COPY ops/docker/api.entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

ARG APP_VERSION=dev
ARG APP_REVISION=unknown
ENV APP_VERSION=${APP_VERSION} APP_REVISION=${APP_REVISION}
LABEL org.opencontainers.image.version=${APP_VERSION} \
      org.opencontainers.image.revision=${APP_REVISION} \
      org.opencontainers.image.source="https://github.com/MasterYodaOfficial/remnastore"

CMD ["/app/entrypoint.sh"]
