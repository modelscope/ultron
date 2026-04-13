# Copyright (c) ModelScope Contributors. All rights reserved.
"""Setuptools metadata and dependency wiring for the ultron package."""
from pathlib import Path

from setuptools import find_packages, setup

_ROOT = Path(__file__).resolve().parent


def _read_requirements() -> list:
    path = _ROOT / "requirements.txt"
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            out.append(line)
    return out


def _read_readme() -> str:
    readme = _ROOT / "README.md"
    if readme.is_file():
        return readme.read_text(encoding="utf-8")
    return ""


setup(
    name="ultron",
    version="1.0.0",
    author="ModelScope Contributors",
    description=(
        "Collective memory and skill hub for general assistants: "
        "shared remote memory, semantic search, and skill packages."
    ),
    long_description=_read_readme(),
    long_description_content_type="text/markdown",
    url="https://github.com/modelscope/ultron",
    packages=find_packages(),
    python_requires=">=3.9",
    install_requires=_read_requirements(),
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Programming Language :: Python :: 3.13",
    ],
)
