FROM python:3.14-slim AS builder

WORKDIR /src

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

RUN python -m pip install --upgrade pip --break-system-packages && \
    pip install uv --break-system-packages

COPY ./pyproject.toml ./uv.lock ./

RUN uv sync --no-cache --no-group dev


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

COPY --chown=appuser:appgroup ./src .
COPY --from=builder --chown=appuser:appgroup /src/.venv /src/.venv
RUN chmod -R +x /src/.venv/bin/

RUN mkdir -p /ms-playwright /log && \
    /src/.venv/bin/python -m playwright install --with-deps chromium && \
    chown -R appuser:appgroup /ms-playwright /log

USER appuser

EXPOSE 8080/tcp

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
