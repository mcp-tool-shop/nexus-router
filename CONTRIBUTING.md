# Contributing to nexus-router

Thank you for your interest in contributing to nexus-router! We appreciate your help in building a robust event-sourced MCP router.

## How to Contribute

### Reporting Issues

If you find a bug or have a suggestion:

1. Check if the issue already exists in [GitHub Issues](https://github.com/mcp-tool-shop/nexus-router/issues)
2. If not, create a new issue with:
   - A clear, descriptive title
   - Steps to reproduce (for bugs)
   - Expected vs. actual behavior
   - Your environment (Python version, OS)

### Contributing Code

1. **Fork the repository** and create a branch from `master`
2. **Set up your development environment**
   ```bash
   pip install -e ".[dev]"
   ```
3. **Make your changes**
   - Follow the existing code style
   - Add tests for new functionality
   - Ensure all tests pass: `pytest`
   - Run linting: `ruff check .`
   - Run type checking: `mypy nexus_router`
4. **Commit your changes**
   - Use clear, descriptive commit messages
   - Reference issue numbers when applicable
5. **Submit a pull request**
   - Describe what your PR does and why
   - Link to related issues

### Development Workflow

```bash
# Install in editable mode with dev dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Run tests with coverage
pytest --cov=nexus_router

# Lint code
ruff check .

# Format code
ruff format .

# Type check
mypy nexus_router
```

### Testing

All new features should include tests. Tests are located in the `tests/` directory and use pytest.

```python
# Example test structure
def test_new_feature():
    # Arrange
    # Act
    # Assert
    pass
```

### Code Style

- Follow PEP 8 conventions
- Use type hints for all function signatures
- Maximum line length: 100 characters
- Use ruff for linting and formatting
- Pass mypy strict type checking

### Event Store Design Principles

- **Immutability** - Events are append-only, never modified
- **Monotonic sequencing** - Events have strictly increasing sequence numbers
- **Provenance** - All runs include integrity digests
- **Policy gating** - Enforce `allow_apply` and `max_steps` constraints

## Project Structure

```
nexus-router/
├── nexus_router/      # Main package
│   ├── tool.py        # MCP tool interface
│   ├── router.py      # Core router logic
│   ├── events.py      # Event definitions
│   ├── policy.py      # Policy enforcement
│   └── schemas/       # JSON schemas
├── tests/             # Test suite
└── pyproject.toml     # Project configuration
```

## Release Process

See [RELEASING.md](RELEASING.md) for the release workflow.

## Code of Conduct

Please note that this project is released with a [Code of Conduct](CODE_OF_CONDUCT.md). By participating, you agree to abide by its terms.

## Questions?

Open an issue or start a discussion. We're here to help!
