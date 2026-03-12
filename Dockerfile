FROM python:3.9-slim

WORKDIR /app
ENV PYTHONPATH=/app

# Install system dependencies (curl needed for healthcheck)
RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc libpq-dev curl && \
    rm -rf /var/lib/apt/lists/*

# Copy all source first, then install
COPY pyproject.toml ./
COPY src/ src/
RUN pip install --no-cache-dir ".[prod]"

# Copy remaining files
COPY migrations/ migrations/
COPY alembic.ini ./

# Run migrations and start (migrations handled by entrypoint)
COPY scripts/docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh

# Run as non-root user
RUN useradd -m -r appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

ENTRYPOINT ["/docker-entrypoint.sh"]
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
