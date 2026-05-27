# Project:   hyperi-pylib
# File:      deployment/errors.py
# Purpose:   Deployment validation/generation error types
# Language:  Python
#
# License:   FSL-1.1-ALv2
# Copyright: (c) 2026 HYPERI PTY LIMITED

"""Deployment validation and generation error types -- mirrors rustlib's
``hyperi_rustlib::deployment::error``."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ContractMismatch:
    """A single contract mismatch between app defaults and a deployment artefact."""

    field: str
    expected: str
    actual: str

    def __str__(self) -> str:
        return f"{self.field}: expected '{self.expected}', got '{self.actual}'"


class DeploymentError(Exception):
    """Base exception for deployment artefact generation/validation failures."""


class ReadFileError(DeploymentError):
    """Failed to read a deployment artefact file."""

    def __init__(self, path: str, source: Exception) -> None:
        self.path = path
        self.source = source
        super().__init__(f"failed to read {path}: {source}")


class WriteFileError(DeploymentError):
    """Failed to write a deployment artefact file."""

    def __init__(self, path: str, source: Exception) -> None:
        self.path = path
        self.source = source
        super().__init__(f"failed to write {path}: {source}")


class CreateDirError(DeploymentError):
    """Failed to create a directory."""

    def __init__(self, path: str, source: Exception) -> None:
        self.path = path
        self.source = source
        super().__init__(f"failed to create directory {path}: {source}")


class ParseYamlError(DeploymentError):
    """Failed to parse YAML."""

    def __init__(self, path: str, source: Exception) -> None:
        self.path = path
        self.source = source
        super().__init__(f"failed to parse YAML in {path}: {source}")


class NotFoundError(DeploymentError):
    """File not found."""

    def __init__(self, path: str) -> None:
        self.path = path
        super().__init__(f"file not found: {path}")


__all__ = [
    "ContractMismatch",
    "CreateDirError",
    "DeploymentError",
    "NotFoundError",
    "ParseYamlError",
    "ReadFileError",
    "WriteFileError",
]
