FROM python:3.11-slim

LABEL maintainer="Kardelen Yazılım <mustafa@kardelenyazilim.com>"
LABEL description="MustafaCLI - Production-ready AI coding assistant"
LABEL version="0.2.0"

# Set working directory
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
    chown -R agent:agent /workspace /var/log/mustafacli

# Switch to non-root user
USER agent
WORKDIR /workspace

# Expose metrics port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import sys; sys.exit(0)" || exit 1

# Default command
CMD ["local-agent"]
