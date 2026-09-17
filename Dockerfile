FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md ./
COPY packages ./packages
COPY scripts ./scripts
COPY tests ./tests

RUN pip install --no-cache-dir -e ".[dev]"

RUN mkdir -p /app/workspace_data

ENV PYTHONPATH=/app/packages/control_plane:/app/packages/workflows:/app/packages/gateway:/app/packages/tools:/app/packages/db:/app/packages/ar:/app/packages/evals
ENV ALLOWED_ROOT=/app/workspace_data

EXPOSE 8000

CMD ["uvicorn", "control_plane.main:app", "--host", "0.0.0.0", "--port", "8000"]
