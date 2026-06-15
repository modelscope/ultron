# Copyright (c) ModelScope Contributors. All rights reserved.
"""Implementations of the ``ultron`` CLI subcommands."""
import getpass
import io
import sys
import zipfile
from pathlib import Path
from typing import Dict

from ultron.services.harness.allowlist import ALLOWLIST_REGISTRY
from ultron.services.harness.defaults import get_defaults
from ultron.services.harness.merge import merge_resources

from . import config
from .client import ApiError, UltronClient


def _fail(message: str) -> int:
    print(f"error: {message}", file=sys.stderr)
    return 1


def _frameworks() -> str:
    return ", ".join(sorted(ALLOWLIST_REGISTRY))


def cmd_login(args) -> int:
    server = config.resolve_server(args.server)
    if not server:
        return _fail("no server given; pass --server or set ULTRON_SERVER")
    username = args.username or input("Username: ").strip()
    password = args.password or getpass.getpass("Password: ")
    if not username or not password:
        return _fail("username and password are required")

    client = UltronClient(server)
    try:
        token = client.login(username, password)
    except ApiError as e:
        return _fail(f"login failed ({e.detail})")
    path = config.save(server, username, token)
    print(f"Logged in as {username} @ {server}")
    print(f"Credentials saved to {path}")
    return 0


def _build_allowlist(framework: str, name: str, local_dir):
    spec_cls = ALLOWLIST_REGISTRY[framework]
    local = Path(local_dir).expanduser() if local_dir else None
    return spec_cls(agent_name=name, local_dir=local)


def _zip_resources(resources: Dict[str, str]) -> bytes:
    """Pack ``{rel_path: text}`` into a deterministic in-memory zip."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for rel, content in sorted(resources.items()):
            zf.writestr(rel, content)
    return buf.getvalue()


def _convert(resources: dict, source_fw: str, target_fw: str) -> dict:
    """Convert workspace resources from one framework's format to another.

    Reuses the server-side cross-product migration (``merge_resources``), so the
    output paths follow the target framework's conventions. A no-op when source
    and target are the same.
    """
    if source_fw == target_fw:
        return resources
    result = merge_resources(
        incoming=resources,
        source_product=source_fw,
        target_product=target_fw,
        source_defaults=get_defaults(source_fw),
        target_defaults=get_defaults(target_fw),
    )
    return result.merged_files


def cmd_upload(args) -> int:
    framework = args.framework
    if framework not in ALLOWLIST_REGISTRY:
        return _fail(f"unknown framework '{framework}'. Available: {_frameworks()}")

    # --list: enumerate discoverable sub-agents and exit (no name required).
    if args.list:
        spec = _build_allowlist(framework, args.name or "default", args.local_dir)
        agents = spec.list_agents()
        print(f"Sub-agents for {framework}:")
        for a in agents:
            print(f"  {a}")
        return 0

    if not args.name:
        return _fail("--name is required (the internal sub-agent name)")

    spec = _build_allowlist(framework, args.name, args.local_dir)
    root = spec.workspace_root
    resources: Dict[str, str] = spec.collect()
    if not resources:
        return _fail(
            f"no files found for {framework}/{args.name} under {root}. "
            f"Check the path or pass --local_dir."
        )

    total_bytes = sum(len(c.encode("utf-8")) for c in resources.values())
    print(f"Found {len(resources)} file(s) ({total_bytes} bytes) under {root}:")
    for rel in sorted(resources):
        print(f"  {rel} ({len(resources[rel].encode('utf-8'))} B)")

    if args.dry_run:
        print("\n[dry-run] nothing uploaded.")
        return 0

    server = config.resolve_server(args.server)
    token = config.resolve_token(args.token)
    username = config.resolve_username()
    if not server or not token:
        return _fail("not logged in. Run 'ultron login' first (or set ULTRON_SERVER/ULTRON_TOKEN).")
    if not username:
        return _fail("missing username; run 'ultron login' again.")

    client = UltronClient(server, token)
    try:
        if not client.check_repo(username, args.name):
            client.create_repo(username, args.name, framework)
            print(f"Created repository {username}/{args.name} (framework={framework}).")
        # Pack the whole sub-agent directory into one zip so the server gets a
        # complete snapshot and can apply deletes, not just per-file updates.
        zip_bytes = _zip_resources(resources)
        message = args.message or f"upload {framework}/{args.name}"
        result = client.upload_zip(
            username, args.name, framework, zip_bytes, message
        )
    except ApiError as e:
        return _fail(f"upload failed ({e.detail})")

    data = result.get("data", {})
    print(
        f"\nUploaded {data.get('files', len(resources))} file(s) "
        f"({len(zip_bytes)} B zip) to "
        f"{username}/{args.name} (revision {data.get('Revision', '?')})."
    )
    return 0


def cmd_download(args) -> int:
    if not args.name:
        return _fail("--name is required (the repository / sub-agent name)")

    server = config.resolve_server(args.server)
    token = config.resolve_token(args.token)
    username = config.resolve_username()
    if not server or not token:
        return _fail("not logged in. Run 'ultron login' first (or set ULTRON_SERVER/ULTRON_TOKEN).")
    if not username:
        return _fail("missing username; run 'ultron login' again.")

    client = UltronClient(server, token)
    try:
        info = client.repo_info(username, args.name)
        if info is None:
            return _fail(f"repository {username}/{args.name} not found.")
        # Framework: explicit flag wins, else the value stored on the repo.
        framework = args.framework or info.get("Framework", "")
        if framework not in ALLOWLIST_REGISTRY:
            return _fail(
                f"unknown framework '{framework}'. Pass --framework explicitly. "
                f"Available: {_frameworks()}"
            )
        paths = client.list_repo_files(username, args.name)
        if not paths:
            return _fail(f"repository {username}/{args.name} has no files.")
        # List then fetch each file via its download link, one at a time.
        resources = {
            p: client.download_repo_file(username, args.name, p) for p in paths
        }
    except ApiError as e:
        return _fail(f"download failed ({e.detail})")

    # Optional format conversion (source framework -> target framework).
    target_fw = args.target or framework
    if target_fw not in ALLOWLIST_REGISTRY:
        return _fail(f"unknown target framework '{target_fw}'. Available: {_frameworks()}")
    if target_fw != framework:
        resources = _convert(resources, framework, target_fw)
        print(f"Converted {framework} -> {target_fw} ({len(resources)} file(s)).")

    spec = _build_allowlist(target_fw, args.name, args.local_dir)
    root = spec.workspace_root
    print(f"{len(resources)} file(s) for {username}/{args.name} (framework={target_fw}):")
    for rel in sorted(resources):
        print(f"  {rel} -> {root / rel}")

    if args.dry_run:
        print("\n[dry-run] nothing written.")
        return 0

    written = spec.apply(resources)
    print(f"\nWrote {len(written)} file(s) under {root}.")
    return 0


def cmd_convert(args) -> int:
    """Local-only format conversion: read a workspace, convert, write it out."""
    source_fw = args.source
    target_fw = args.target
    for fw, label in ((source_fw, "--from"), (target_fw, "--to")):
        if fw not in ALLOWLIST_REGISTRY:
            return _fail(f"unknown framework '{fw}' for {label}. Available: {_frameworks()}")

    name = args.name or "default"
    src_spec = _build_allowlist(source_fw, name, args.local_dir)
    src_root = src_spec.workspace_root
    resources = src_spec.collect()
    if not resources:
        return _fail(
            f"no {source_fw} files found under {src_root}. Check the path or pass --local_dir."
        )

    converted = _convert(resources, source_fw, target_fw)

    # Destination: --out wins, else the target framework's workspace root.
    if args.out:
        dst_spec = _build_allowlist(target_fw, name, args.out)
    else:
        dst_spec = _build_allowlist(target_fw, name, None)
    dst_root = dst_spec.workspace_root

    print(
        f"Convert {source_fw} ({src_root}) -> {target_fw} ({dst_root}): "
        f"{len(resources)} in, {len(converted)} out"
    )
    for rel in sorted(converted):
        print(f"  {rel} -> {dst_root / rel}")

    if args.dry_run:
        print("\n[dry-run] nothing written.")
        return 0

    written = dst_spec.apply(converted)
    print(f"\nWrote {len(written)} file(s) under {dst_root}.")
    return 0
