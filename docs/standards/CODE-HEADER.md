<!-- HYPERCI_STATE_MD: core/standards/CODE-HEADER.md -->
# Code Header Standards (All Languages)

**Auto-copied to `docs/standards/` by CI_AI_MERGE_MODE**

This document defines code header standards for all AI assistants.
Headers are language-specific, but rules are universal.

---

## Header Requirements (REUSE/SPDX Compliant)

**CRITICAL:** All source code files MUST have a standard header.

### Minimum Required Fields:

```
Project:      <PROJECT_NAME>
File:         <FILENAME>
Purpose:      <One-sentence description>
Language:     <Python|Bash|C|Go|JavaScript|etc.>

License:      <SPDX-Identifier>
Copyright:    (c) <YEAR> <ORGANISATION>
```

### Optional Fields:

```
Description:
    <Multi-line purpose, notes, assumptions>

Notes:
    - Compatible with: <Platform/Runtime>
    - Follows: <Standards/Specs>
```

---

## License Selection

**Project has ONE license type** (configured in ci.yaml):

### Supported Licenses:

**1. HyperSec EULA (Proprietary)**
- SPDX: `LicenseRef-HyperSec-EULA`
- Use for: Commercial HyperSec products
- Copyright: `(c) YYYY HyperSec Pty Ltd`
- File: `LICENSE` (HyperSec EULA text)
- Reference: https://hypersec.io/eula/

**2. Apache 2.0 (Open Source)**
- SPDX: `Apache-2.0`
- Use for: Open source projects
- Copyright: `(c) YYYY HyperSec` or `(c) YYYY <Author>`
- File: `LICENSE` (Apache 2.0 text)

**Future:** Can add MIT, BSD, GPL, etc.

### Configuration (ci.yaml):

```yaml
project:
  license: hypersec-eula  # or: apache-2.0, mit, etc.
```

---

## Rules for AI Assistants

### ALWAYS:

✅ **Use project's license** - From ci.yaml configuration
✅ **Use current year** - From system date (not model training date)
✅ **Use organisation name** - From project configuration
✅ **Include SPDX identifier** - Standard format
✅ **One-sentence purpose** - Clear and concise
✅ **Language-appropriate comments** - # for Python, // for Go, etc.

### NEVER:

❌ **Include version numbers** - Managed by CHANGELOG.md and git
❌ **Include change dates** - Managed by git history
❌ **Include author names** - Always "HyperSec" or organisation
❌ **Include file modification history** - That's what git is for
❌ **Copy headers from other projects** - Use project's configured license

---

## Header Placement

**Top of file, before any code:**

```python
# Python example
#  Project:      hyperlib
#  File:         config.py
#  Purpose:      Configuration management with Dynaconf
#  Language:     Python
#
#  License:      Apache-2.0
#  Copyright:    (c) 2025 HyperSec
#
#  Description:
#      Provides configuration cascade: CLI > ENV > .env > yaml > defaults
#      Handles multiple config files with language-specific overrides.

"""Module docstring here."""

import os
...
```

---

## Language-Specific Templates

**Headers are language-specific** - see language modules:

- Python: `ci/modules/python/ai/CODE_HEADER.md`
- Bash: `ci/modules/bash/ai/CODE_HEADER.md` (future)
- Go: `ci/modules/go/ai/CODE_HEADER.md` (future)

Each language module provides:
- Comment syntax (# vs // vs /* */)
- Header template
- Examples

---

## REUSE Compliance

Follows REUSE Software Specification 3.3:
- ✅ SPDX license identifier
- ✅ Copyright notice
- ✅ No version/changelog in headers (managed separately)
- ✅ Machine-readable format
- ✅ Language-appropriate syntax

**For full spec:** https://reuse.software/spec-3.3/

---

## Example: License Selection

```python
# Get license from project config
from ci_lib import get_config_value

license_type = get_config_value("project.license", default="apache-2.0")

if license_type == "hypersec-eula":
    spdx_id = "LicenseRef-HyperSec-EULA"
    copyright_holder = "HyperSec Pty Ltd"
elif license_type == "apache-2.0":
    spdx_id = "Apache-2.0"
    copyright_holder = "HyperSec"
```

---

## For AI Assistants

**When creating new files:**

1. Check project license (ci.yaml → project.license)
2. Get current year (from system date)
3. Load header template for language
4. Fill in: project name, filename, purpose, language
5. Add header at top of file (before code)

**When editing existing files:**

- Preserve existing headers (don't modify)
- If no header exists, add one
- Update Purpose if file purpose changed significantly

---

**See language-specific CODE_HEADER.md for templates and examples.**


---

<!-- HYPERCI_STATE_MD: python/standards/CODE-HEADER.md -->
# Code Header Standards (Python)

**Auto-copied to `docs/standards/` by CI_AI_MERGE_MODE**

Python-specific code header templates and examples.

---

## Python Comment Syntax

Python uses `#` for comments. Headers go at the TOP of the file, before any code or imports.

---

## Standard Python Header Template

### For HyperSec EULA Projects:

```python
#  Project:      <project-name>
#  File:         <filename>.py
#  Purpose:      <One-sentence description>
#  Language:     Python
#
#  License:      LicenseRef-HyperSec-EULA
#  Copyright:    (c) <YEAR> HyperSec Pty Ltd
#  EULA:         https://hypersec.io/eula/
#
#  Description:
#      <Optional multi-line description>
#      <Assumptions, notes, etc.>
#
#  Notes:
#      - Compatible with: Python 3.11+
#      - Follows: PEP 8, Black formatting

"""Module docstring here."""

import os
...
```

### For Apache 2.0 Projects:

```python
#  Project:      <project-name>
#  File:         <filename>.py
#  Purpose:      <One-sentence description>
#  Language:     Python
#
#  License:      Apache-2.0
#  Copyright:    (c) <YEAR> HyperSec
#
#  Description:
#      <Optional multi-line description>

"""Module docstring here."""

import os
...
```

---

## Examples

### Minimal Header (Required fields only):

```python
#  Project:      hyperlib
#  File:         config.py
#  Purpose:      Configuration management with Dynaconf
#  Language:     Python
#
#  License:      Apache-2.0
#  Copyright:    (c) 2025 HyperSec

"""Configuration management module."""

from dynaconf import Dynaconf
...
```

### Full Header (With description and notes):

```python
#  Project:      hyperlib
#  File:         logger.py
#  Purpose:      Structured logging with RFC 3339 timestamps
#  Language:     Python
#
#  License:      Apache-2.0
#  Copyright:    (c) 2025 HyperSec
#
#  Description:
#      Provides structured logging using loguru with:
#      - RFC 3339 compliant timestamps
#      - CHARS-POLICY.md emoji support
#      - Container-aware output (Docker/K8s)
#      - Solarized color scheme
#
#  Notes:
#      - Compatible with: Python 3.11+
#      - Follows: RFC 3339 timestamps, CHARS-POLICY.md
#      - Dependencies: loguru, dynaconf

"""Structured logging with RFC 3339 timestamps."""

import os
import sys
from loguru import logger
...
```

---

## Field Guidelines

### Project:
- Use project name from pyproject.toml (name field)
- Example: hyperlib, dfe-hunt-runner

### File:
- Just the filename (not full path)
- Example: config.py, logger.py

### Purpose:
- ONE sentence (concise)
- Describes what this file does
- Example: "Configuration management with Dynaconf"

### Language:
- Language name (not version)
- Example: Python, Bash, Go, JavaScript

### License:
- SPDX identifier from ci.yaml
- HyperSec EULA: `LicenseRef-HyperSec-EULA`
- Apache: `Apache-2.0`

### Copyright:
- Current year (from system date)
- HyperSec EULA: "HyperSec Pty Ltd"
- Apache: "HyperSec" or project-specific

### Description (optional):
- Multi-line details about the file
- Assumptions, design notes
- Keep concise

### Notes (optional):
- Compatibility (Python version, platform)
- Standards followed (PEP 8, RFC 3339)
- Dependencies

---

## What NOT to Include

❌ **Version numbers** - Managed by git tags and CHANGELOG.md
❌ **Change dates** - Managed by git history
❌ **Author names** - Always use organisation (HyperSec)
❌ **Modification history** - Use `git log`
❌ **TODO/FIXME** - Put in TODO.md, not headers

---

## For AI Assistants

### When Creating New Python Files:

1. Get license from `ci.yaml` (project.license)
2. Get current year from system date
3. Get project name from pyproject.toml
4. Fill in filename, purpose, description
5. Add header before any code/imports
6. Add module docstring after header

### When Editing Existing Files:

- **Preserve existing headers** (don't modify)
- Update Purpose only if file purpose changed significantly
- If no header, add one following project's license

### Determining License:

```python
# From ci.yaml
license_type = config.get("project.license", "apache-2.0")

if license_type == "hypersec-eula":
    spdx = "LicenseRef-HyperSec-EULA"
    copyright_holder = "HyperSec Pty Ltd"
elif license_type == "apache-2.0":
    spdx = "Apache-2.0"
    copyright_holder = "HyperSec"
```

---

**This is the Python-specific header guide. See common/ai/CODE_HEADER.md for universal rules.**
