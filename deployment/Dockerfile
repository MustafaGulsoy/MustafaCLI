FROM python:3.11-slim

LABEL maintainer="Kardelen Yazilim <mustafa@kardelenyazilim.com>"
LABEL description="MustafaCLI - Production-ready AI coding assistant"
LABEL version="0.5.0"

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    git \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first (for better caching)
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY src/ ./src/
COPY pyproject.toml .
COPY README.md .

# Install the package
RUN pip install --no-cache-dir -e .

# Create non-root user
RUN useradd -m -u 1000 -s /bin/bash agent && \
    mkdir -p /workspace /var/log/mustafacli && \
    chown -R agent:agent /workspace /var/log/mustafacli /app

USER agent
WORKDIR /workspace

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Default: run API server
CMD ["python", "-m", "uvicorn", "src.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
