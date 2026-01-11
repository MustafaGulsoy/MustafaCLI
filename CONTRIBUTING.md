# Contributing to MustafaCLI

Thank you for your interest in contributing to MustafaCLI! This document provides guidelines and instructions for contributing.

## Development Setup

### Prerequisites
- Python 3.10 or higher
- Git
- (Optional) Ollama for local testing

### Setup
```bash
# Clone the repository
git clone https://github.com/kardelenyazilim/local-agent-cli.git
cd local-agent-cli

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install development dependencies
pip install -r requirements-dev.txt

# Install package in editable mode
pip install -e .
```

## Development Workflow

### 1. Create a Branch
```bash
git checkout -b feature/your-feature-name
# or
git checkout -b fix/your-bug-fix
```

### 2. Make Changes
- Write code following the style guide
- Add tests for new functionality
- Update documentation as needed

### 3. Run Tests
```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=src --cov-report=term-missing

# Run specific test file
pytest tests/test_tools.py

# Run with verbose output
pytest -v
```

### 4. Code Quality Checks
```bash
# Format code with Black
black src/ tests/

# Lint with Ruff
ruff check src/ tests/ --fix

# Type check with mypy
mypy src/

# Security check
bandit -r src/
safety check
```

### 5. Commit Changes
```bash
git add .
git commit -m "feat: add new feature"
# or
git commit -m "fix: resolve bug in tool execution"
```

Follow [Conventional Commits](https://www.conventionalcommits.org/):
- `feat:` new feature
- `fix:` bug fix
- `docs:` documentation changes
- `test:` test additions or changes
- `refactor:` code refactoring
- `perf:` performance improvements
- `chore:` maintenance tasks

### 6. Push and Create Pull Request
```bash
git push origin feature/your-feature-name
```

Then create a pull request on GitHub.

## Code Style Guide

### Python Style
- Follow PEP 8
- Use type hints
- Maximum line length: 100 characters
- Use Black for formatting
- Use Ruff for linting

### Documentation
- Add docstrings to all public functions and classes
- Use Google-style docstrings
- Update README.md for user-facing changes
- Update CHANGELOG.md for notable changes

### Example Docstring
```python
def execute_tool(
    self,
    tool_name: str,
    arguments: dict[str, Any],
) -> ToolResult:
    """
    Execute a tool with given arguments.

    Args:
        tool_name: Name of the tool to execute
        arguments: Dictionary of tool arguments

    Returns:
        ToolResult: Result of tool execution

    Raises:
        ToolNotFoundError: If tool doesn't exist
        ToolExecutionError: If execution fails

    Example:
        >>> result = execute_tool("bash", {"command": "ls"})
        >>> print(result.output)
    """
    pass
```

## Testing Guidelines

### Test Structure
- Place tests in `tests/` directory
- Mirror source structure: `src/core/tools.py` → `tests/test_tools.py`
- Use descriptive test names: `test_command_validation_blocks_dangerous_commands`

### Writing Tests
```python
import pytest
from pathlib import Path

class TestBashTool:
    """Tests for BashTool."""

    @pytest.mark.asyncio
    async def test_simple_command(self, temp_dir: Path):
        """Test simple command execution."""
        tool = BashTool(working_dir=str(temp_dir))
        result = await tool.execute("echo 'hello'")

        assert result.success
        assert "hello" in result.output

    @pytest.mark.asyncio
    async def test_blocked_command(self, temp_dir: Path):
        """Test that dangerous commands are blocked."""
        tool = BashTool(working_dir=str(temp_dir))
        result = await tool.execute("rm -rf /")

        assert not result.success
        assert "blocked" in result.error.lower()
```

### Test Coverage
- Aim for >80% code coverage
- Test happy paths and error cases
- Test security boundaries
- Test edge cases

## Security Guidelines

### Reporting Security Issues
**DO NOT** open public issues for security vulnerabilities. Instead:
1. Email: security@kardelenyazilim.com
2. Include detailed description
3. Include steps to reproduce
4. Wait for response before public disclosure

### Security Best Practices
- Never commit secrets or API keys
- Use environment variables for configuration
- Validate all user inputs
- Follow principle of least privilege
- Review code for injection vulnerabilities

## Pull Request Process

### Before Submitting
- [ ] Tests pass locally
- [ ] Code is formatted (Black)
- [ ] Linting passes (Ruff)
- [ ] Type checking passes (mypy)
- [ ] Documentation is updated
- [ ] CHANGELOG.md is updated
- [ ] Commit messages follow convention

### PR Guidelines
- Provide clear description of changes
- Reference related issues
- Include test results
- Request reviews from maintainers
- Be responsive to feedback

### Review Process
1. Automated checks must pass
2. At least one maintainer approval required
3. All comments must be resolved
4. Squash and merge to main

## Release Process

### Version Numbering
Follow [Semantic Versioning](https://semver.org/):
- MAJOR: Breaking changes
- MINOR: New features (backward compatible)
- PATCH: Bug fixes (backward compatible)

### Release Steps
1. Update version in `pyproject.toml`
2. Update CHANGELOG.md
3. Create git tag: `git tag v0.2.0`
4. Push tag: `git push --tags`
5. GitHub Actions will build and publish

## Getting Help

- **Documentation**: Check README.md and code documentation
- **Issues**: Search existing issues on GitHub
- **Discussions**: Use GitHub Discussions for questions
- **Discord**: Join our community Discord (link in README)

## Code of Conduct

### Our Pledge
We pledge to make participation in our project a harassment-free experience for everyone.

### Our Standards
- Be respectful and inclusive
- Accept constructive criticism
- Focus on what is best for the community
- Show empathy towards others

### Enforcement
Violations may result in temporary or permanent ban from the project.

---

Thank you for contributing to MustafaCLI! 🚀
