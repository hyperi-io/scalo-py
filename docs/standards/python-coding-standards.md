# Python Coding Standards (HyperCI)

**Auto-copied to `docs/standards/` by CI_MERGE**

## Code Style

**Formatter:** `black` (line length: 120)

**Linter:** `ruff` (replaces flake8, isort, pyupgrade)

**Type checker:** `mypy` (optional, configure in pyproject.toml)

**Configuration:** All tools configured in `pyproject.toml`

## Running Code Quality Tools

```bash
# Lint code
ci-local/.venv/bin/python ci/python/ci.d/20-python-test.py lint

# Format code
ci-local/.venv/bin/ruff format src/ tests/

# Type check
ci-local/.venv/bin/mypy src/
```

## Python Version

**Minimum:** Python 3.11+

**Specified in:**
- `pyproject.toml`: `requires-python = ">=3.11"`
- Type hints: Use modern syntax (| for union, not Union[])

## Import Organization

**Order (enforced by ruff):**
1. Standard library imports
2. Third-party imports
3. Local application imports

**Example:**
```python
import os
import sys
from pathlib import Path

import loguru
from dynaconf import Dynaconf

from hyperlib import get_logger
from hyperlib.config import load_config
```

## Type Hints

**Use type hints for:**
- Function signatures (parameters and return types)
- Class attributes
- Complex variables

**Example:**
```python
from pathlib import Path
from typing import Optional

def process_file(file_path: Path, encoding: str = "utf-8") -> Optional[str]:
    """Process a file and return content."""
    if not file_path.exists():
        return None
    return file_path.read_text(encoding=encoding)
```

## Docstrings

**Style:** Google-style docstrings

**Example:**
```python
def calculate_total(items: list[int], tax_rate: float = 0.1) -> float:
    """
    Calculate total with tax.

    Args:
        items: List of item prices
        tax_rate: Tax rate as decimal (default: 0.1 for 10%)

    Returns:
        Total price including tax

    Raises:
        ValueError: If tax_rate is negative
    """
    if tax_rate < 0:
        raise ValueError("Tax rate cannot be negative")

    subtotal = sum(items)
    return subtotal * (1 + tax_rate)
```

## Testing

**Framework:** `pytest`

**Test location:** `tests/` directory

**Test file naming:** `test_*.py` or `*_test.py`

**Running tests:**
```bash
ci-local/.venv/bin/python ci/python/ci.d/20-python-test.py test
```

**Test markers:**
```python
import pytest

@pytest.mark.e2e
def test_end_to_end():
    """End-to-end integration test."""
    pass

@pytest.mark.integration
def test_integration():
    """Integration test."""
    pass
```

**Configure markers in `pyproject.toml`:**
```toml
[tool.pytest.ini_options]
markers = [
    "e2e: end-to-end integration tests",
    "integration: integration tests",
]
```

## Dependencies

**Management:** `uv` (preferred) or `pip`

**Lock files:**
- `uv.lock` - Project dependencies (committed)
- `ci-local/uv.lock` - CI tool dependencies (committed)

**Adding dependencies:**
```bash
# Add to pyproject.toml dependencies
uv add package-name

# Add as optional dependency
uv add --optional api fastapi

# Update lockfile
uv lock
```

## Project Structure

**Standard Python package:**
```
project/
├── src/
│   └── package_name/
│       ├── __init__.py
│       └── module.py
├── tests/
│   ├── __init__.py
│   └── test_module.py
├── docs/
├── ci/               # HyperCI submodule (READ-ONLY)
├── ci-local/         # Project CI customizations (writable)
├── pyproject.toml
├── uv.lock
├── README.md
├── STATE.md         # Project state (may include CI docs)
└── TODO.md          # Tasks (todo-md standard)
```

## Error Handling

**Use specific exceptions:**
```python
# Good
try:
    result = risky_operation()
except FileNotFoundError as e:
    logger.error(f"File not found: {e}")
    raise
except ValueError as e:
    logger.error(f"Invalid value: {e}")
    return None

# Avoid
try:
    result = risky_operation()
except Exception:  # Too broad
    pass
```

## Logging

**Use structured logging:**
```python
from hyperlib import get_logger

logger = get_logger(__name__)

logger.info("Processing file", file_path=path, size=size)
logger.error("Failed to process", error=str(e), file=path)
```

## Security

**Tools:**
- `bandit` - Security linter (checks for common vulnerabilities)
- `safety` - Dependency vulnerability scanner (optional)

**Configuration:**
```toml
[tool.bandit]
exclude_dirs = ["tests", "ci"]
skips = ["B101"]  # Skip assert warnings in non-test code
```

## Performance

**Tools:**
- `pytest-benchmark` - Performance testing
- `py-spy` - Profiling (optional)

**Guidelines:**
- Profile before optimizing
- Use appropriate data structures
- Cache expensive operations
- Use generators for large datasets

## For More Details

See official documentation:
- Black: https://black.readthedocs.io/
- Ruff: https://docs.astral.sh/ruff/
- pytest: https://docs.pytest.org/
- mypy: https://mypy.readthedocs.io/
- uv: https://docs.astral.sh/uv/
