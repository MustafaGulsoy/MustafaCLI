# Production Deployment Guide

This guide covers deploying MustafaCLI in production environments.

## Quick Start

### Installation

```bash
# Clone repository
git clone https://github.com/kardelenyazilim/local-agent-cli.git
cd local-agent-cli

# Create virtual environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Install production dependencies
pip install -r requirements.txt

# Copy and configure environment
cp .env.example .env
# Edit .env with your settings
```

### Running

```bash
# Basic usage
local-agent

# With custom config
local-agent -m qwen2.5-coder:32b -d /path/to/workspace

# With logging
AGENT_LOG_LEVEL=INFO AGENT_LOG_FILE=agent.log local-agent
```

## Configuration

### Environment Variables

All configuration can be set via environment variables. See `.env.example` for all options.

**Critical Settings:**
```bash
AGENT_MODEL_NAME=qwen2.5-coder:32b
AGENT_WORKING_DIR=/secure/workspace
AGENT_ALLOW_DANGEROUS_COMMANDS=false  # Keep false in production
AGENT_LOG_LEVEL=INFO
AGENT_LOG_FILE=/var/log/agent/agent.log
```

### Security Configuration

**Command Whitelist:**
- By default, only safe commands are allowed
- Set `allow_dangerous=True` only when absolutely necessary
- Review `src/core/constants.py` for whitelist

**Path Protection:**
- All file operations are restricted to `working_dir`
- Path traversal attempts are logged and blocked
- Use absolute paths for `working_dir` in production

## Monitoring

### Metrics

Prometheus metrics are exposed on port 8000 by default:
```bash
curl http://localhost:8000/metrics
```

**Key Metrics:**
- `agent_iterations_total` - Total iterations
- `agent_tool_calls_total` - Tool usage
- `tool_execution_duration_seconds` - Tool performance
- `provider_requests_total` - API calls
- `context_tokens_used` - Token usage

### Health Checks

```bash
# Check health (implement in your app)
curl http://localhost:8000/health
```

### Logging

**Log Levels:**
- `DEBUG` - Detailed information (development only)
- `INFO` - General information (production default)
- `WARNING` - Warning messages
- `ERROR` - Error messages
- `CRITICAL` - Critical failures

**Log Rotation:**
- Automatic rotation at 10MB
- 5 backup files kept
- Configure in `src/core/logging_config.py`

**Structured Logging:**
```python
from src.core.logging_config import get_logger

logger = get_logger(__name__)
logger.info("event_name", key1="value1", key2="value2")
```

## Security

### Best Practices

1. **Never Run as Root**
   ```bash
   # Create dedicated user
   useradd -r -s /bin/false agent
   sudo -u agent local-agent
   ```

2. **Restrict Working Directory**
   ```bash
   # Use dedicated workspace
   mkdir -p /opt/agent/workspace
   chown agent:agent /opt/agent/workspace
   chmod 700 /opt/agent/workspace
   ```

3. **Network Isolation**
   - Run in isolated network/container
   - Restrict outbound connections if possible
   - Use firewall rules

4. **API Keys**
   - Never commit API keys
   - Use secrets manager (AWS Secrets Manager, HashiCorp Vault)
   - Rotate keys regularly

5. **Audit Logging**
   ```bash
   # Enable detailed logging
   AGENT_LOG_LEVEL=DEBUG
   AGENT_LOG_FILE=/var/log/agent/audit.log
   ```

### Security Checklist

- [ ] `AGENT_ALLOW_DANGEROUS_COMMANDS=false`
- [ ] Dedicated non-root user
- [ ] Restricted working directory
- [ ] Log rotation configured
- [ ] Metrics monitoring active
- [ ] API keys in secrets manager
- [ ] Regular security updates
- [ ] Audit logs enabled

## Performance Tuning

### Context Management

```bash
# Adjust for your model's context window
AGENT_MAX_CONTEXT_TOKENS=32000
AGENT_CONTEXT_RESERVE_TOKENS=4000
AGENT_COMPACTION_THRESHOLD=0.8
```

### Timeouts

```bash
# Adjust based on your workload
AGENT_TOOL_TIMEOUT=300
AGENT_BASH_TIMEOUT=120
PROVIDER_HTTP_TIMEOUT=300
```

### Retry Configuration

```bash
PROVIDER_MAX_RETRIES=3
PROVIDER_RETRY_MIN_WAIT=1.0
PROVIDER_RETRY_MAX_WAIT=10.0
```

## Troubleshooting

### High Memory Usage

```bash
# Reduce context window
AGENT_MAX_CONTEXT_TOKENS=16000
AGENT_COMPACTION_THRESHOLD=0.7

# Increase compaction frequency
AGENT_KEEP_RECENT_MESSAGES=5
```

### Slow Performance

1. Check metrics: `curl http://localhost:8000/metrics`
2. Review logs: `tail -f /var/log/agent/agent.log`
3. Profile: Enable DEBUG logging
4. Optimize: Reduce context window, adjust timeouts

### Tool Execution Failures

1. Check working directory permissions
2. Verify command whitelist
3. Review security logs
4. Test command manually: `bash -c "command"`

## Docker Deployment

```dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY src/ ./src/
COPY pyproject.toml .

# Create non-root user
RUN useradd -m -u 1000 agent && \
    mkdir -p /workspace && \
    chown agent:agent /workspace

USER agent
WORKDIR /workspace

EXPOSE 8000

CMD ["local-agent"]
```

**Build and Run:**
```bash
docker build -t mustafacli .
docker run -v $(pwd)/workspace:/workspace \
  -e AGENT_LOG_LEVEL=INFO \
  -p 8000:8000 \
  mustafacli
```

## Kubernetes Deployment

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: mustafacli
spec:
  replicas: 1
  selector:
    matchLabels:
      app: mustafacli
  template:
    metadata:
      labels:
        app: mustafacli
    spec:
      securityContext:
        runAsNonRoot: true
        runAsUser: 1000
      containers:
      - name: agent
        image: mustafacli:latest
        env:
        - name: AGENT_LOG_LEVEL
          value: "INFO"
        - name: AGENT_WORKING_DIR
          value: "/workspace"
        ports:
        - containerPort: 8000
          name: metrics
        resources:
          requests:
            memory: "512Mi"
            cpu: "500m"
          limits:
            memory: "2Gi"
            cpu: "2000m"
        volumeMounts:
        - name: workspace
          mountPath: /workspace
      volumes:
      - name: workspace
        emptyDir: {}
---
apiVersion: v1
kind: Service
metadata:
  name: mustafacli-metrics
spec:
  selector:
    app: mustafacli
  ports:
  - port: 8000
    targetPort: 8000
    name: metrics
```

## Maintenance

### Log Rotation

Logs are automatically rotated. Manual cleanup:
```bash
# Remove old logs
find /var/log/agent -name "agent.log.*" -mtime +30 -delete
```

### Dependency Updates

```bash
# Check for updates
pip list --outdated

# Update safely
pip install -r requirements.txt --upgrade

# Run tests
pytest

# Check security
safety check
bandit -r src/
```

### Backup

```bash
# Backup configuration
tar -czf config-backup.tar.gz .env

# Backup logs
tar -czf logs-backup.tar.gz /var/log/agent/

# Backup workspace (if needed)
tar -czf workspace-backup.tar.gz /opt/agent/workspace
```

## Support

- **Issues**: https://github.com/kardelenyazilim/local-agent-cli/issues
- **Documentation**: https://github.com/kardelenyazilim/local-agent-cli#readme
- **Security**: security@kardelenyazilim.com

## License

MIT License - See LICENSE file for details.
