FROM python:3.14-slim AS builder

WORKDIR /src

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

RUN python -m pip install --upgrade pip --break-system-packages && \
    pip install uv --break-system-packages

COPY ./pyproject.toml ./uv.lock ./

# The libsql extra (ADR-21) is Linux-x86_64-marked, so it's a no-op for a plain `uv sync`.
RUN uv sync --no-cache --no-group dev --extra libsql


FROM python:3.14-slim AS runtime
LABEL authors="aleksander.marszalki"
LABEL name="travelplanner"

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

RUN groupadd -r appgroup && useradd -r -g appgroup appuser

ENV PATH="/src/.venv/bin:/usr/local/bin:$PATH"
ENV PLAYWRIGHT_BROWSERS_PATH="/ms-playwright"

WORKDIR /src

COPY --from=builder --chown=appuser:appgroup /src/.venv /src/.venv
RUN chmod -R +x /src/.venv/bin/

# appuser must own /data (compose mounts a named volume there) or a fresh volume can't be
# written to when the Turso sqlite file is first created.
RUN mkdir -p /ms-playwright /log /data && \
    /src/.venv/bin/python -m playwright install --with-deps chromium && \
    chown -R appuser:appgroup /ms-playwright /log /data

COPY --chown=appuser:appgroup ./src .
RUN chown appuser:appgroup /src

USER appuser

EXPOSE 8080/tcp

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
