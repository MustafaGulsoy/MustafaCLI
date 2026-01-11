# 🚀 Production Deployment Checklist

## Pre-Deployment

### 1. Code Repository
- [x] ✅ Code committed to git
- [x] ✅ Version tagged (v0.2.0)
- [ ] ⏸️ Push to GitHub
  ```bash
  git remote add origin https://github.com/YOUR_USERNAME/local-agent-cli.git
  git push -u origin main
  git push origin v0.2.0
  ```

### 2. Testing
- [x] ✅ All tests passing (18/18)
- [x] ✅ Security tests verified
- [x] ✅ Code coverage acceptable (25%+)
- [ ] Load testing (optional)

### 3. Documentation
- [x] ✅ README.md updated
- [x] ✅ CHANGELOG.md created
- [x] ✅ CONTRIBUTING.md created
- [x] ✅ README_PRODUCTION.md created
- [x] ✅ API documentation (inline)

---

## Deployment Options

Choose one of the following deployment methods:

### Option A: Docker Compose (Recommended) 🐳

#### Prerequisites
- Docker & Docker Compose installed
- 8GB+ RAM
- 20GB+ disk space

#### Steps
1. **Prepare environment**
   ```bash
   cd deployment/
   cp production.env .env
   # Edit .env with your settings
   nano .env
   ```

2. **Pull Ollama model**
   ```bash
   docker-compose up -d ollama
   docker exec -it mustafacli-ollama ollama pull qwen2.5-coder:32b
   ```

3. **Start all services**
   ```bash
   docker-compose up -d
   ```

4. **Verify**
   ```bash
   # Check services
   docker-compose ps

   # Check logs
   docker-compose logs -f agent

   # Check metrics
   curl http://localhost:8000/metrics

   # Access Grafana
   open http://localhost:3000  # admin/admin
   ```

#### Monitoring Stack Included:
- ✅ MustafaCLI Agent (port 8000)
- ✅ Ollama (port 11434)
- ✅ Prometheus (port 9090)
- ✅ Grafana (port 3000)

---

### Option B: Systemd Service (Linux Server) 🖥️

#### Prerequisites
- Ubuntu 20.04+ or Debian 11+
- Python 3.10+
- 4GB+ RAM
- sudo access

#### Steps
1. **Run installation script**
   ```bash
   sudo bash deployment/install.sh
   ```

2. **Configure environment**
   ```bash
   sudo nano /opt/mustafacli/.env
   # Update settings, especially:
   # - AGENT_WORKING_DIR
   # - AGENT_LOG_FILE
   # - PROVIDER_OLLAMA_URL
   ```

3. **Start service**
   ```bash
   sudo systemctl start mustafacli
   sudo systemctl status mustafacli
   ```

4. **Check logs**
   ```bash
   sudo journalctl -u mustafacli -f
   ```

---

### Option C: Kubernetes (Enterprise) ☸️

Coming soon in v0.3.0

---

## Post-Deployment Checklist

### 1. Service Verification
- [ ] Service is running
  ```bash
  # Docker
  docker-compose ps

  # Systemd
  sudo systemctl status mustafacli
  ```

- [ ] Metrics endpoint responding
  ```bash
  curl http://localhost:8000/metrics
  ```

- [ ] Health check passing
  ```bash
  # TODO: Implement /health endpoint
  ```

### 2. Security Verification
- [ ] Non-root user running service
- [ ] Dangerous commands disabled
  ```bash
  # Check .env file
  grep AGENT_ALLOW_DANGEROUS_COMMANDS .env
  # Should show: AGENT_ALLOW_DANGEROUS_COMMANDS=false
  ```

- [ ] Working directory restricted
  ```bash
  # Check permissions
  ls -la /opt/mustafacli/workspace  # or container workspace
  # Should show: drwx------ (700)
  ```

- [ ] Logs rotating properly
  ```bash
  ls -lh /var/log/mustafacli/
  ```

### 3. Monitoring Setup
- [ ] Prometheus scraping metrics
  ```bash
  curl http://localhost:9090/targets
  ```

- [ ] Grafana dashboard configured
  - Login: http://localhost:3000
  - Add Prometheus data source
  - Import dashboard (coming soon)

- [ ] Alerts configured (optional)

### 4. Backup Configuration
- [ ] Workspace backup scheduled
  ```bash
  # Example cron job
  0 2 * * * tar -czf /backup/workspace-$(date +\%Y\%m\%d).tar.gz /opt/mustafacli/workspace
  ```

- [ ] Configuration backed up
  ```bash
  cp /opt/mustafacli/.env /backup/.env.$(date +%Y%m%d)
  ```

---

## Performance Tuning

### Resource Limits (Docker)
Edit `docker-compose.yml`:
```yaml
deploy:
  resources:
    limits:
      cpus: '4'      # Adjust based on your needs
      memory: 8G     # Adjust based on your needs
```

### Context Settings (.env)
```bash
AGENT_MAX_CONTEXT_TOKENS=32000    # Reduce for smaller models
AGENT_COMPACTION_THRESHOLD=0.7    # Compact more aggressively
AGENT_KEEP_RECENT_MESSAGES=5      # Keep fewer messages
```

### Timeouts
```bash
AGENT_TOOL_TIMEOUT=180             # Reduce for faster failure
AGENT_BASH_TIMEOUT=60              # Reduce for faster failure
PROVIDER_HTTP_TIMEOUT=180          # Adjust for your network
```

---

## Troubleshooting

### Service Won't Start
1. Check logs:
   ```bash
   # Docker
   docker-compose logs agent

   # Systemd
   sudo journalctl -u mustafacli -n 100
   ```

2. Verify configuration:
   ```bash
   # Check .env syntax
   cat .env | grep -v '^#' | grep -v '^$'
   ```

3. Test dependencies:
   ```bash
   # Test Ollama connection
   curl http://localhost:11434/api/health
   ```

### High Memory Usage
1. Reduce context window:
   ```bash
   AGENT_MAX_CONTEXT_TOKENS=16000
   ```

2. Compact more frequently:
   ```bash
   AGENT_COMPACTION_THRESHOLD=0.7
   ```

3. Monitor with metrics:
   ```bash
   curl http://localhost:8000/metrics | grep memory
   ```

### Slow Performance
1. Check resource limits
2. Monitor CPU usage
3. Review tool execution times in metrics
4. Consider using smaller model

---

## Maintenance

### Daily
- [ ] Check service status
- [ ] Review error logs
- [ ] Monitor resource usage

### Weekly
- [ ] Review metrics dashboard
- [ ] Check disk space
- [ ] Verify backups

### Monthly
- [ ] Update dependencies
- [ ] Security audit
- [ ] Performance review
- [ ] Backup testing

---

## Rollback Plan

If deployment fails:

1. **Stop service**
   ```bash
   # Docker
   docker-compose down

   # Systemd
   sudo systemctl stop mustafacli
   ```

2. **Restore previous version**
   ```bash
   git checkout v0.1.0
   # Rebuild/reinstall
   ```

3. **Restore configuration**
   ```bash
   cp /backup/.env.backup /opt/mustafacli/.env
   ```

4. **Restart service**

---

## Support

- 📚 Documentation: README_PRODUCTION.md
- 🐛 Issues: GitHub Issues
- 💬 Community: GitHub Discussions
- 🔒 Security: security@kardelenyazilim.com

---

## Success Criteria

✅ All items checked = Production Ready!

- [ ] Service running stably
- [ ] Tests passing
- [ ] Metrics available
- [ ] Logs readable
- [ ] Security hardened
- [ ] Backups configured
- [ ] Monitoring active
- [ ] Documentation complete
