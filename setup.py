#!/usr/bin/env python3
"""
Setup.py for Nuitka bdist_nuitka support

This allows building compiled wheels with:
    python setup.py bdist_nuitka

The compiled wheel can be installed via pip and imported normally.
"""

from setuptools import setup

# Read dependencies from pyproject.toml
import tomllib
from pathlib import Path

pyproject_path = Path(__file__).parent / "pyproject.toml"
with open(pyproject_path, 'rb') as f:
    pyproject = tomllib.load(f)

project = pyproject['project']

setup(
    name=project['name'],
    version=project['version'],
    description=project['description'],
    long_description=Path('README.md').read_text(),
    long_description_content_type='text/markdown',
    author='HyperSec Team',
    author_email='dev@hypersec.io',
    url='https://github.com/hypersec-io/hyperlib',
    packages=['hyperlib'],
    package_dir={'': 'src'},
    python_requires=project['requires-python'],
    install_requires=project['dependencies'],
    classifiers=project['classifiers'],
    keywords=project['keywords'],

    # Nuitka-specific options for bdist_nuitka
    # For LIBRARY: Only compile this package, dependencies remain as Python imports
    command_options={
        'nuitka': {
            # Enable data-hiding plugin (encrypts strings and function names)
            '--enable-plugin': ['data-hiding'],
            # bdist_nuitka automatically uses --mode=package (correct for libraries)
            # Do NOT add: --standalone (conflicts with --mode=package)
            # Do NOT add: --follow-imports (keeps dependencies as Python imports)
        }
    },
)
