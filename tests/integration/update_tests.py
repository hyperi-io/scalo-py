#!/usr/bin/env python3
"""Script to update test_container_deployment.py to use fixture files."""

import re
from pathlib import Path

# Read the test file
test_file = Path("test_container_deployment.py")
content = test_file.read_text()

# Define replacements - map from old code to fixture name
replacements = [
    # Prometheus metrics app
    (
        r'app_file\.write_text\(""".*?from hyperlib import Application, create_metrics.*?app\.run\(\)\n"""\)',
        'app_file.write_text(self.load_fixture("test_container_deployment_code_2"))',
    ),
    # Daemon app
    (
        r'app_file\.write_text\(""".*?from hyperlib import Application, get_mount_config.*?app\.run\(\)\n"""\)',
        'app_file.write_text(self.load_fixture("test_container_deployment_code_3"))',
    ),
    # Database compose app
    (
        r'app_file\.write_text\(""".*?from hyperlib import get_database_config, build_database_url.*?print\(f"Database: \{db_config\[\'database\'\]\}"\)\n"""\)',
        'app_file.write_text(self.load_fixture("test_container_deployment_code_5"))',
    ),
    # K8s pod app
    (
        r'app_code = """.*?k8s_token = Path.*?print\(f"Mount paths: \{mounts\}"\)\n"""',
        'app_code = self.load_fixture("test_container_deployment_7")',
    ),
    # K8s metrics app
    (
        r'app_code = """.*?class MetricsHandler.*?httpd\.serve_forever\(\)\n"""',
        'app_code = self.load_fixture("test_container_deployment_9")',
    ),
]

# Apply replacements
for pattern, replacement in replacements:
    content = re.sub(pattern, replacement, content, flags=re.DOTALL)

# Write back
test_file.write_text(content)
print("Updated test_container_deployment.py")
