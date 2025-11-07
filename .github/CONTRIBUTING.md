# Contributing to Resumable Upload

Thank you for your interest in contributing to this project! We welcome contributions from the community.

## Getting Started

1. Fork the repository
2. Clone your fork: `git clone https://github.com/your-username/resumable-upload.git`
3. Create a new branch: `git checkout -b feature/your-feature-name`

## Development Setup

1. Install development dependencies:

```bash
pip install -e ".[dev]"
```

1. Install pre-commit hooks:

```bash
pre-commit install
```

1. Run tests:

```bash
pytest
```

## Code Quality

This project uses several tools to maintain code quality:

- **Ruff**: Fast Python linter and formatter
- **Pre-commit**: Git hooks for automatic code checks
- **Pytest**: Testing framework

### Running Linters

```bash
# Run ruff linter
ruff check .

# Run ruff formatter
ruff format .

# Run all pre-commit hooks
pre-commit run --all-files
```

### Running Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=resumable_upload --cov-report=html
```

## Coding Standards

- Follow PEP 8 style guide
- Write docstrings for all public functions and classes
- Add type hints where appropriate
- Keep functions focused and small
- Write tests for new features

## Pull Request Process

1. Ensure all tests pass
2. Update documentation if needed
3. Add tests for new features
4. Run pre-commit hooks: `pre-commit run --all-files`
5. Create a pull request with a clear description

## Reporting Issues

When reporting issues, please include:

- Python version
- Operating system
- Steps to reproduce
- Expected behavior
- Actual behavior
- Error messages (if any)

## License

By contributing, you agree that your contributions will be licensed under the MIT License.
