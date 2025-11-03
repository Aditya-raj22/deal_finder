FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY requirements.txt pyproject.toml ./

# Install Python dependencies
RUN pip install --no-cache-dir -e ".[dev,llm]"

# Copy application code
COPY deal_finder/ ./deal_finder/
COPY config/ ./config/
COPY tests/ ./tests/

# Create output directories
RUN mkdir -p /app/output /app/logs /app/.cache

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV TZ=UTC

# Run as non-root user
RUN useradd -m -u 1000 dealfinder && \
    chown -R dealfinder:dealfinder /app
USER dealfinder

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import deal_finder; print('OK')" || exit 1

# Default command
CMD ["python", "-m", "deal_finder.main", "--config", "config/production.yaml"]
