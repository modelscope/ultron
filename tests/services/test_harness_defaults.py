# Copyright (c) ModelScope Contributors. All rights reserved.
"""Default templates must only be loaded for registered products."""

from pathlib import Path

import pytest

from ultron.services.harness import defaults
from ultron.services.harness.allowlist import ALLOWLIST_REGISTRY


@pytest.fixture
def template_root(tmp_path, monkeypatch):
    root = tmp_path / "defaults"
    root.mkdir()
    monkeypatch.setattr(defaults, "_DEFAULTS_DIR", root)
    return root


@pytest.mark.parametrize("product", ALLOWLIST_REGISTRY)
def test_registered_product_loads_nested_text_files(template_root, product):
    product_dir = template_root / product
    (product_dir / "memory").mkdir(parents=True)
    (product_dir / "SOUL.md").write_text("Default soul", encoding="utf-8")
    (product_dir / "memory" / "MEMORY.md").write_text("记忆", encoding="utf-8")
    (product_dir / "binary.dat").write_bytes(b"\xff\xfe")

    assert defaults.get_defaults(product) == {
        "SOUL.md": "Default soul",
        str(Path("memory") / "MEMORY.md"): "记忆",
    }


@pytest.mark.parametrize("exists", [False, True])
def test_missing_or_empty_product_directory_returns_empty(template_root, exists):
    if exists:
        (template_root / "nanobot").mkdir()

    assert defaults.get_defaults("nanobot") == {}


@pytest.mark.parametrize(
    "product",
    [
        "absolute", "../outside", "nanobot/../../outside", "", ".", "..",
        "unknown", "nanobot/..", "nanobot/memory", "nanobot/",
        r"..\outside", r"C:\outside", "%2e%2e%2foutside",
    ],
)
def test_invalid_product_cannot_load_files(template_root, tmp_path, product):
    # Both outside directories and unregistered directories inside defaults
    # contain real files, so an empty result proves they were not loaded.
    for directory in (
        tmp_path / "outside", template_root / "unknown",
        template_root / "nanobot" / "memory",
    ):
        directory.mkdir(parents=True)
        (directory / "proof.txt").write_text("Do not export", encoding="utf-8")
    if product == "absolute":
        product = str(tmp_path / "outside")

    assert defaults.get_defaults(product) == {}
