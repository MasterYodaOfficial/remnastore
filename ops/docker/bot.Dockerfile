FROM python:3.12-slim
WORKDIR /app

ENV UV_CACHE_DIR=/tmp/uv-cache

RUN pip install --no-cache-dir -U pip uv
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

# uv creates .venv by default; add it to PATH
ENV PATH="/app/.venv/bin:${PATH}"

COPY common ./common
COPY apps/bot/bot ./bot
COPY packages/locales ./packages/locales
ARG APP_VERSION=dev
ARG APP_REVISION=unknown
ENV APP_VERSION=${APP_VERSION} APP_REVISION=${APP_REVISION}
LABEL org.opencontainers.image.version=${APP_VERSION} \
      org.opencontainers.image.revision=${APP_REVISION} \
      org.opencontainers.image.source="https://github.com/MasterYodaOfficial/remnastore"
EXPOSE 8080
CMD ["uv", "run", "--no-sync", "python", "-m", "bot.main"]
