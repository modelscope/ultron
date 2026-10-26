# Copyright (c) ModelScope Contributors. All rights reserved.
"""HTTP export regression tests with real storage and no LLM startup."""

import os
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from ultron import server_state
from ultron.api.routers import harness
from ultron.core.database import Database
from ultron.services.harness import HarnessService, defaults
from ultron.services.harness.allowlist import ALLOWLIST_REGISTRY


@pytest.fixture
def export_context(tmp_path, monkeypatch):
    db = Database(str(tmp_path / "test.db"))
    service = HarnessService(db)
    service.sync_up("alice", "agent", "nanobot", {"SOUL.md": "Uploaded soul"})
    share = service.create_share("alice", "agent")
    monkeypatch.setattr(server_state, "ultron", SimpleNamespace(db=db))
    app = FastAPI()
    app.include_router(harness.router)
    with TestClient(app) as client:
        yield client, service, share


@pytest.fixture(params=["token", "short_code"])
def export_path(export_context, request):
    _, _, share = export_context
    if request.param == "token":
        return "/harness/share/export/" + share["token"]
    return "/i/" + share["short_code"]


@pytest.mark.parametrize("product", [None, "", *ALLOWLIST_REGISTRY])
def test_normal_exports_preserve_uploaded_content(export_context, export_path, product):
    client, _, _ = export_context
    params = {} if product is None else {"product": product}
    response = client.get(export_path, params=params)

    assert response.status_code == 200
    assert "Uploaded soul" in response.text
    assert response.headers["content-type"].startswith("text/x-shellscript")
    if product in (None, "", "nanobot"):
        assert "# Files: 1\n" in response.text
    if product == "openclaw":
        assert "Writing BOOTSTRAP.md" in response.text


@pytest.mark.parametrize("path_kind", ["absolute", "relative"])
@pytest.mark.parametrize("product_location", ["query", "snapshot"])
def test_exports_do_not_read_outside_templates(
    export_context, export_path, tmp_path, monkeypatch, path_kind, product_location,
):
    client, service, _ = export_context
    outside = tmp_path / "outside"
    outside.mkdir()
    secret_file = outside / "proof.txt"
    secret_file.write_text("PRIVATE_TEST_FILE_CONTENT", encoding="utf-8")
    product = str(outside)
    if path_kind == "relative":
        product = os.path.relpath(outside, defaults._DEFAULTS_DIR)

    read_paths = []
    original_read_text = Path.read_text

    def record_read(path, *args, **kwargs):
        read_paths.append(path.resolve())
        return original_read_text(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", record_read)
    if product_location == "snapshot":
        # Sync updates the existing share, including its source product.
        service.sync_up("alice", "agent", product, {"SOUL.md": "Uploaded soul"})
        product = "openclaw"
    response = client.get(export_path, params={"product": product})

    assert response.status_code == 200
    assert secret_file.resolve() not in read_paths
    assert "PRIVATE_TEST_FILE_CONTENT" not in response.text
    assert "Uploaded soul" in response.text


def test_defaults_endpoint_rejects_unregistered_directory(tmp_path, monkeypatch):
    (tmp_path / "unknown").mkdir()
    (tmp_path / "unknown" / "proof.txt").write_text("Private", encoding="utf-8")
    monkeypatch.setattr(defaults, "_DEFAULTS_DIR", tmp_path)
    app = FastAPI()
    app.include_router(harness.router)

    with TestClient(app) as client:
        response = client.get("/harness/defaults/unknown")

    assert response.status_code == 200
    assert response.json()["files"] == {}
