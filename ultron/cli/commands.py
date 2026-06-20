# Copyright (c) ModelScope Contributors. All rights reserved.
"""Implementations of the ``ultron`` CLI subcommands."""
import getpass
import os
import sys
import zipfile
from pathlib import Path
from typing import Dict

from ultron.services.harness.allowlist import ALLOWLIST_REGISTRY
from ultron.services.harness.defaults import get_defaults
from ultron.services.harness.merge import merge_resources

from . import config
from .client import ApiError, UltronClient
from .sync import zip_resources


def _fail(message: str) -> int:
    print(f"error: {message}", file=sys.stderr)
    return 1


def _frameworks() -> str:
    return ", ".join(sorted(ALLOWLIST_REGISTRY))


def cmd_login(args) -> int:
    server = config.resolve_server(args.server)
    if not server:
        return _fail("no server given; pass --server or set ULTRON_SERVER")
    token = args.token or os.environ.get("ULTRON_TOKEN", "").strip()
    if not token:
        token = getpass.getpass("Token: ").strip()
    if not token:
        return _fail("token is required (pass --token, set ULTRON_TOKEN, or enter interactively)")

    client = UltronClient(server)
    try:
        username = client.login(token)
    except ApiError as e:
        return _fail(f"login failed ({e.detail})")
    if not username:
        return _fail("login succeeded but server returned no username")
    path = config.save(server, username, token)
    print(f"Logged in as {username} @ {server}")
    print(f"Credentials saved to {path}")
    return 0


def _build_allowlist(framework: str, name: str, local_dir):
    spec_cls = ALLOWLIST_REGISTRY[framework]
    local = Path(local_dir).expanduser() if local_dir else None
    return spec_cls(agent_name=name, local_dir=local)


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

    # Step 1: upload zip file -> get file_id
    zip_bytes = zip_resources(resources)
    file_id = client.upload_file(zip_bytes)
    # Step 2: create/update agent with file_id
    result = client.create_repo(
        username, args.name, framework,
        system_prompt_files=file_id,
    )

    print(
        f"\nUploaded {len(resources)} file(s) "
        f"({len(zip_bytes)} B zip) to "
        f"{username}/{args.name}."
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


def cmd_watch(args) -> int:
    """Sync agent files from cloud and start background file watcher."""
    from .cache import cache_dir, pid_file
    from .sync import apply_sync, backup_local, diff_files, download_cloud
    from .watcher import daemonize, watch_loop

    framework = args.framework
    if framework not in ALLOWLIST_REGISTRY:
        return _fail(f"unknown framework '{framework}'. Available: {_frameworks()}")
    if not args.name:
        return _fail("--name is required")

    server = config.resolve_server(args.server)
    token = config.resolve_token(args.token)
    username = config.resolve_username()
    if not server or not token:
        return _fail("not logged in. Run 'ultron login' first.")
    if not username:
        return _fail("missing username; run 'ultron login' again.")

    # Check if already running.
    pf = pid_file()
    if pf.exists():
        return _fail(f"watch already running (PID file: {pf}). Run 'ultron stop' first.")

    spec = _build_allowlist(framework, args.name, args.local_dir)
    client = UltronClient(server, token)

    # Step 1: Backup local files.
    print(f"Backing up local files for {framework}/{args.name}...")
    backup_path = backup_local(spec, args.name)
    print(f"  Backup saved: {backup_path}")

    # Step 2: Download cloud files.
    print(f"Downloading cloud files for {username}/{args.name}...")
    try:
        cloud_files = download_cloud(client, username, args.name)
    except ApiError as e:
        if e.status == 404:
            print("  Repository not found on cloud. Skipping sync.")
            cloud_files = {}
        else:
            return _fail(f"download failed ({e.detail})")

    # Step 3: Diff and apply.
    if cloud_files:
        local_files = spec.collect()
        diff = diff_files(local_files, cloud_files)
        if not diff.empty:
            print(f"\nSync changes (cloud -> local):")
            print(f"  Delete {len(diff.to_delete)}, Add {len(diff.to_add)}, "
                  f"Overwrite {len(diff.to_overwrite)}")
            changes = apply_sync(spec, diff, cloud_files, backup_path)
            print(f"  Applied {changes} change(s).")
        else:
            print("  Local files are in sync with cloud.")
    else:
        print("  No cloud files to sync.")

    # Step 4: Enter background watch mode.
    interval = getattr(args, "interval", 3) or 3
    print(f"\nEntering background watch mode (interval={interval}s)...")
    print(f"  Logs: {cache_dir() / 'logs' / 'watch.log'}")
    print(f"  Stop: ultron stop")

    daemonize(watch_loop, spec, client, username, args.name, framework, interval)
    # If we reach here, we are the parent process (daemon forked successfully).
    print(f"  Watch started (PID file: {pf}).")
    return 0


def cmd_stop(args) -> int:
    """Stop the background watch process."""
    from .watcher import stop_daemon

    stopped = stop_daemon()
    if stopped:
        print("Watch process stopped.")
    else:
        print("No watch process running.")
    return 0


def cmd_recover(args) -> int:
    """Recover agent files from a backup zip in the cache directory."""
    from .cache import cache_dir

    framework = args.framework
    if framework not in ALLOWLIST_REGISTRY:
        return _fail(f"unknown framework '{framework}'. Available: {_frameworks()}")

    filename = args.filename
    zip_path = cache_dir() / filename
    if not zip_path.exists():
        # Try exact path if user gave full path.
        zip_path = Path(filename)
    if not zip_path.exists():
        return _fail(f"backup file not found: {filename} (looked in {cache_dir()})")

    name = args.name
    if not name:
        # Infer name from filename: "my-agent_20260609_143022.zip" -> "my-agent"
        stem = zip_path.stem  # e.g. "my-agent_20260609_143022"
        parts = stem.rsplit("_", 2)
        name = parts[0] if len(parts) >= 3 else stem

    spec = _build_allowlist(framework, name, args.local_dir)
    root = spec.workspace_root

    print(f"Recovering {zip_path.name} -> {root}")
    count = 0
    with zipfile.ZipFile(zip_path, "r") as zf:
        for info in zf.infolist():
            if info.is_dir():
                continue
            target = root / info.filename
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(zf.read(info.filename))
            print(f"  {info.filename}")
            count += 1

    print(f"\nRecovered {count} file(s) to {root}.")
    return 0
