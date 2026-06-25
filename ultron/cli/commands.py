# Copyright (c) ModelScope Contributors. All rights reserved.
"""Implementations of the ``ultron`` CLI subcommands."""
import getpass
import os
import sys
import zipfile
from pathlib import Path
from typing import Dict

from ultron.services.harness.allowlist import ALLOWLIST_REGISTRY, ALL_AGENT_NAME
from ultron.services.harness.defaults import get_defaults
from ultron.services.harness.merge import merge_resources

from . import config
from .client import ApiError, UltronClient


def _fail(message: str) -> int:
    print(f"Error: {message}", file=sys.stderr)
    return 1


def _api_error_message(e: ApiError, action: str = "request") -> str:
    """Return a user-friendly message based on the HTTP status code."""
    if e.status == 401:
        return "authentication failed. Run 'ultron login' to refresh your token."
    if e.status == 403:
        return "permission denied. You do not have access to this resource."
    if e.status == 404:
        return "resource not found. Check the repository name and try again."
    if e.status >= 500:
        return "server encountered an issue. Please wait a moment and try again."
    return f"{action} failed (HTTP {e.status}: {e.detail})"


def _repo_name(framework: str, name: str) -> str:
    """Derive the remote repository name from framework and sub-agent name.

    - name is "all" or empty: use framework alone (``all`` is the default scope)
    - Both provided: ``{framework}-{name}``
    - Only one provided: use that value directly
    - Neither provided: ``"default"``
    """
    fw = (framework or "").strip()
    n = (name or "").strip()
    # "all" means full-scope sync — not a distinct sub-agent, so omit from repo name.
    if n == ALL_AGENT_NAME:
        n = ""
    if fw and n:
        return f"{fw}-{n}"
    if fw:
        return fw
    if n:
        return n
    return "default"


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

    repo = _repo_name(framework, args.name)
    # Step 1: upload files -> get file_id
    try:
        file_id = client.upload_file(resources)
        # Step 2: create/update agent with file_id
        result = client.create_repo(
            username, repo, framework,
            system_prompt_files=file_id,
        )
    except ApiError as e:
        return _fail(_api_error_message(e, "upload"))

    print(
        f"\nUploaded {len(resources)} file(s) to "
        f"{username}/{repo}."
    )
    return 0


def cmd_download(args) -> int:
    if not args.name:
        return _fail("--name is required (the repository / sub-agent name)")
    if not args.framework:
        return _fail("--framework is required for download (to derive repo name)")

    framework = args.framework
    if framework not in ALLOWLIST_REGISTRY:
        return _fail(f"unknown framework '{framework}'. Available: {_frameworks()}")

    server = config.resolve_server(args.server)
    token = config.resolve_token(args.token)
    username = config.resolve_username()
    if not server or not token:
        return _fail("not logged in. Run 'ultron login' first (or set ULTRON_SERVER/ULTRON_TOKEN).")
    if not username:
        return _fail("missing username; run 'ultron login' again.")

    repo = _repo_name(framework, args.name)
    client = UltronClient(server, token)
    try:
        info = client.repo_info(username, repo)
        if info is None:
            return _fail(f"repository {username}/{repo} not found.")
        paths = client.list_repo_files(username, repo)
        if not paths:
            return _fail(f"repository {username}/{repo} has no files.")
        # List then fetch each file via its download link, one at a time.
        resources = {
            p: client.download_repo_file(username, repo, p) for p in paths
        }
    except ApiError as e:
        return _fail(_api_error_message(e, "download"))

    # Optional format conversion (source framework -> target framework).
    target_fw = args.target or framework
    if target_fw not in ALLOWLIST_REGISTRY:
        return _fail(f"unknown target framework '{target_fw}'. Available: {_frameworks()}")
    if target_fw != framework:
        resources = _convert(resources, framework, target_fw)
        print(f"Converted {framework} -> {target_fw} ({len(resources)} file(s)).")

    spec = _build_allowlist(target_fw, args.name, args.local_dir)
    root = spec.workspace_root
    print(f"{len(resources)} file(s) for {username}/{repo} (framework={target_fw}):")
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
    """Start background bidirectional sync for agent files."""
    from .cache import pid_file
    from .watcher import daemonize, watch_loop

    framework = args.framework
    if framework not in ALLOWLIST_REGISTRY:
        return _fail(f"unknown framework '{framework}'. Available: {_frameworks()}")

    # Default --name to "all" (full-scope sync).
    name = args.name or ALL_AGENT_NAME

    server = config.resolve_server(args.server)
    token = config.resolve_token(args.token)
    username = config.resolve_username()
    if not server or not token:
        return _fail("not logged in. Run 'ultron login' first.")
    if not username:
        return _fail("missing username; run 'ultron login' again.")

    # Ensure no stale watch processes are running.
    pf = pid_file()
    if pf.exists():
        from .watcher import stop_daemon
        stop_daemon()

    spec = _build_allowlist(framework, name, args.local_dir)
    client = UltronClient(server, token)

    # Guard: file-per-agent frameworks must use --name all for watch.
    if not spec.supports_individual_watch and name != ALL_AGENT_NAME:
        return _fail(
            f"'{framework}' has shared files across sub-agents; "
            f"watch only supports '--name all' to avoid sync conflicts. "
            f"Use 'ultron upload/download -n {name}' for individual sub-agent operations."
        )

    repo = _repo_name(framework, name)

    # Guard: check remote repo framework matches local.
    try:
        info = client.repo_info(username, repo)
        if info:
            remote_fw = info.get("Framework") or info.get("framework") or ""
            if remote_fw and remote_fw != framework:
                return _fail(
                    f"framework mismatch: local={framework}, remote={remote_fw}. "
                    f"Use 'ultron convert' or 'ultron download --target' for cross-framework sync."
                )
    except ApiError as e:
        if e.status in (403, 401):
            return _fail(_api_error_message(e, "watch"))
        pass  # repo not found or unreachable — proceed, first push will create it

    interval = 120
    push_only = not getattr(args, "pull", False)
    print(f"Starting sync for {username}/{repo} (interval={interval}s)...")
    print(f"  Framework: {framework}")
    print(f"  Root: {spec.workspace_root}")
    if push_only:
        print(f"  Mode: push-only (local → remote, will NOT pull remote changes)")
    else:
        print(f"  Mode: bidirectional (local ↔ remote, WILL pull remote changes to local)")
    print(f"  Logs: {pid_file().parent / 'logs' / 'watch.log'}")
    print(f"  Stop: ultron stop")

    daemonize(watch_loop, spec, client, username, repo, framework, interval, push_only=push_only)
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
    """Restore agent files from a backup zip.

    Supports:
      - ``ultron restore last``        → restore the most recent backup
      - ``ultron restore <filename>``   → restore a specific backup (with/without .zip)
      - ``ultron restore --list``       → list all available backups
    """
    from .cache import cache_dir
    import datetime as _dt

    cdir = cache_dir()

    # Collect all backup zips in cache dir (pattern: *_YYYYMMDD_HHMMSS.zip)
    backups = sorted(
        (f for f in cdir.iterdir() if f.suffix == ".zip" and f.is_file()),
        key=lambda f: f.stat().st_mtime,
    )

    # --list mode: enumerate backups and exit
    if args.list:
        if not backups:
            print("No backups found.")
            return 0
        print(f"Backups in {cdir}:\n")
        last = backups[-1]
        for f in backups:
            mtime = _dt.datetime.fromtimestamp(f.stat().st_mtime)
            marker = "  [LAST]" if f == last else ""
            print(f"  {f.name}  ({mtime:%Y-%m-%d %H:%M:%S}){marker}")
        print(f"\n{len(backups)} backup(s) total.")
        return 0

    # Restore mode: need a target
    target = args.target
    if not target:
        return _fail("specify a target: 'last' or a backup filename. Use --list to see available backups.")

    # Resolve target to a zip path
    if target == "last":
        if not backups:
            return _fail("no backups found.")
        zip_path = backups[-1]
    else:
        # Normalize: add .zip if missing
        fname = target if target.endswith(".zip") else f"{target}.zip"
        zip_path = cdir / fname
        if not zip_path.exists():
            # Try as absolute/relative path
            zip_path = Path(target)
        if not zip_path.exists():
            return _fail(f"backup not found: {fname} (looked in {cdir})")

    # Determine framework and workspace root
    framework = args.framework
    if framework and framework not in ALLOWLIST_REGISTRY:
        return _fail(f"unknown framework '{framework}'. Available: {_frameworks()}")

    name = args.name
    if not name:
        # Infer name from filename: "qoder_20260609_143022.zip" -> "qoder"
        stem = zip_path.stem
        parts = stem.rsplit("_", 2)
        name = parts[0] if len(parts) >= 3 else stem

    if not framework:
        # Try to infer framework from the name (e.g., "qoder" -> framework "qoder")
        if name in ALLOWLIST_REGISTRY:
            framework = name
        else:
            return _fail("cannot infer framework. Pass --framework explicitly.")

    spec = _build_allowlist(framework, "all", args.local_dir)
    root = spec.workspace_root

    # ---- Step 1: Backup current local files before any modification ----
    from .sync import backup_local
    current_resources = spec.collect()
    if current_resources:
        pre_restore_backup = backup_local(spec, name)
        print(f"Pre-restore backup: {pre_restore_backup.name}")
    else:
        print("No existing files to backup.")

    # ---- Step 2: Determine which files are in the zip ----
    with zipfile.ZipFile(zip_path, "r") as zf:
        zip_entries = set(
            info.filename for info in zf.infolist() if not info.is_dir()
        )

    # ---- Step 3: Delete local files that are NOT in the zip ----
    deleted = 0
    for rel in sorted(current_resources.keys()):
        if rel not in zip_entries:
            target_file = root / rel
            if target_file.exists():
                target_file.unlink()
                print(f"  Removed: {rel}")
                deleted += 1

    # ---- Step 4: Extract zip (overwrite matched files) ----
    resolved_root = root.resolve()
    print(f"Restoring {zip_path.name} -> {resolved_root}")
    restored = 0
    with zipfile.ZipFile(zip_path, "r") as zf:
        for info in zf.infolist():
            if info.is_dir():
                continue
            file_target = (resolved_root / info.filename).resolve()
            if not file_target.is_relative_to(resolved_root):
                print(f"  Skipped (path traversal): {info.filename}")
                continue
            file_target.parent.mkdir(parents=True, exist_ok=True)
            file_target.write_bytes(zf.read(info.filename))
            print(f"  Restored: {info.filename}")
            restored += 1

    print(f"\nRestored {restored} file(s), removed {deleted} extra file(s).")
    return 0
