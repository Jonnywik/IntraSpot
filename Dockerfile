FROM ghcr.io/astral-sh/uv:0.12.17 AS uv

FROM python:3.14-slim AS dependencies
COPY --from=uv /uv /uvx /bin/
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
WORKDIR /app
COPY Code/Backend/pyproject.toml Code/Backend/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

FROM python:3.14-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    INTRASPOT_CONFIG=hosted \
    PATH="/app/.venv/bin:${PATH}"

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --system --gid 10001 intraspot \
    && useradd --system --uid 10001 --gid intraspot --create-home intraspot

COPY --from=dependencies --chown=intraspot:intraspot /app/.venv /app/.venv
COPY --chown=intraspot:intraspot Code/Backend/app /app/app
COPY --chown=intraspot:intraspot Code/Backend/migrations /app/migrations
COPY --chown=intraspot:intraspot Code/Backend/alembic.ini /app/alembic.ini

USER intraspot:intraspot
EXPOSE 8000

CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port \"${PORT:-8000}\" --workers 1"]
