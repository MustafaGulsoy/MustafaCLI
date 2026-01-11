# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.0] - 2024-01-XX - Production Hardening Release

### Added
- **Security**
  - Command whitelist for BashTool (prevents arbitrary command execution)
  - Path traversal protection for all file operations
  - Input validation and sanitization
  - Security audit logging

- **Logging**
  - Structured logging with structlog
  - Log rotation and file management
  - Sensitive data censoring
  - JSON log format support

- **Error Handling**
  - Custom exception hierarchy
  - Retry logic with exponential backoff (tenacity)
  - Better error messages and context
  - Graceful degradation

- **Configuration**
  - Pydantic-based settings management
  - Environment variable support
  - Validation and type safety
  - Multi-environment support (dev/staging/prod)

- **Testing**
  - Comprehensive test suite (pytest)
  - Security tests
  - Mock providers for testing
  - Test fixtures and conftest

- **Observability**
  - Prometheus metrics integration
  - Health check endpoints
  - System resource monitoring
  - Performance metrics

- **CI/CD**
  - GitHub Actions workflow
  - Multi-OS testing (Ubuntu, Windows, macOS)
  - Multi-Python version testing (3.10, 3.11, 3.12)
  - Code quality checks (Black, Ruff, mypy)
  - Security scanning (Safety, Bandit)
  - Coverage reporting

- **Code Quality**
  - Constants module (no magic numbers)
  - Strict mypy configuration
  - Dependency locking (requirements.txt)
  - Code documentation improvements

### Changed
- **Breaking**: BashTool now requires explicit `allow_dangerous=True` for non-whitelisted commands
- All file paths now use pathlib.Path for better cross-platform support
- Provider initialization now includes retry configuration
- Improved token estimation accuracy

### Fixed
- Path traversal vulnerabilities in file operations
- Command injection risks in BashTool
- Memory leaks in long-running sessions
- Race conditions in concurrent tool execution

### Security
- Added command whitelist to prevent arbitrary execution
- Implemented path traversal protection
- Added input sanitization for all user inputs
- Improved error messages to not leak sensitive information

## [0.1.0] - 2024-01-XX - Initial Release

### Added
- Core agent loop implementation
- Basic tool system (Bash, View, StrReplace, CreateFile)
- Context management with compaction
- Multi-provider support (Ollama, OpenAI-compatible, Anthropic)
- CLI interface with Rich formatting
- Skills system (placeholder)
- Advanced features (planning, reflection, memory)

---

## Upcoming Features

### [0.3.0] - Planned
- [ ] Parallel tool execution optimization
- [ ] Memory management and persistence
- [ ] Rate limiting and circuit breaker pattern
- [ ] Skills system implementation
- [ ] Multi-modal support (images)
- [ ] Streaming improvements
- [ ] Docker and Kubernetes support

### [0.4.0] - Planned
- [ ] Plugin system
- [ ] Multi-tenancy support
- [ ] Distributed execution
- [ ] Advanced caching strategies
- [ ] API versioning
- [ ] GraphQL API

---

## Migration Guide

### From 0.1.0 to 0.2.0

#### BashTool Changes
```python
# Old (0.1.0)
tool = BashTool(working_dir=".")

# New (0.2.0) - whitelisted commands work as before
tool = BashTool(working_dir=".")

# For non-whitelisted commands, explicit flag required
tool = BashTool(working_dir=".", allow_dangerous=True)
```

#### Configuration Changes
```python
# Old (0.1.0)
config = AgentConfig(
    model_name="qwen2.5-coder:32b",
    working_dir=".",
)

# New (0.2.0) - Use pydantic-based settings
from src.core.config import AgentSettings

settings = AgentSettings(
    model_name="qwen2.5-coder:32b",
    working_dir=".",
)
# Or load from environment variables automatically
```

#### Logging Changes
```python
# Old (0.1.0)
# No structured logging

# New (0.2.0)
from src.core.logging_config import configure_default_logging

configure_default_logging(debug=True, log_file="agent.log")
```
