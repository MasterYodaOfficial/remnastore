FROM python:3.12-slim
WORKDIR /app

ENV UV_CACHE_DIR=/tmp/uv-cache

RUN pip install --no-cache-dir -U pip uv
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

# uv creates .venv by default; add it to PATH
ENV PATH="/app/.venv/bin:${PATH}"

COPY apps/bot/bot ./bot
COPY packages/locales ./packages/locales
EXPOSE 8080
CMD ["python", "-m", "bot.main"]
