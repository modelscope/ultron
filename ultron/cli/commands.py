# Copyright (c) ModelScope Contributors. All rights reserved.
"""Implementations of the ``ultron`` CLI subcommands."""
import getpass
import os
import sys
import zipfile
from pathlib import Path
from typing import Dict, Optional

from ultron.services.harness.allowlist import (
    ALLOWLIST_REGISTRY,
    ALL_AGENT_NAME,
    DEFAULT_AGENT_NAME,
    GLOBAL_AGENT_NAME,
)
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


def _resolve_remote(repo: Optional[str] = None, name: Optional[str] = None, framework: str = "", username: str = ""):
    """Resolve remote target as (group, repo_name).

    - repo contains '/' → split into (group, repo_name), ignore username
    - repo without '/' → (username, repo)
    - repo is None/empty → derive from name+framework using _repo_name logic
    """
    if repo:
        if "/" in repo:
            parts = repo.split("/", 1)
            return parts[0], parts[1]
        return username, repo
    # No explicit repo → derive from framework + name
    derived = _repo_name(framework, name or "")
    return username, derived


def _resolve_local_name(name: Optional[str], framework: str, local_dir=None):
    """Resolve local agent name when --name is omitted.

    Returns (resolved_name, error_message).
    - If name is given → use it directly.
    - If omitted → check list_agents():
      - 0 or only 'default' → use GLOBAL_AGENT_NAME (shared files only)
      - exactly 1 non-default agent → auto-select it
      - multiple → return error
    """
    if name:
        return name, None

    # Build a temporary spec to discover agents.
    spec_cls = ALLOWLIST_REGISTRY[framework]
    local = Path(local_dir).expanduser() if local_dir else None
    tmp_spec = spec_cls(agent_name=DEFAULT_AGENT_NAME, local_dir=local)
    agents = tmp_spec.list_agents()

    # Filter out "default" to find real sub-agents.
    real_agents = [a for a in agents if a != DEFAULT_AGENT_NAME]

    if len(real_agents) == 0:
        return GLOBAL_AGENT_NAME, None
    if len(real_agents) == 1:
        return real_agents[0], None
    return None, (
        f"multiple sub-agents found: {', '.join(agents)}. "
        f"Please specify --name to select one."
    )


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


def cmd_list(args) -> int:
    """List remote agent repositories."""
    server = config.resolve_server(getattr(args, 'server', None))
    token = config.resolve_token(getattr(args, 'token', None))
    if not server:
        return _fail("not logged in. Run 'ultron login' first or pass --server.")

    client = UltronClient(server, token)
    try:
        result = client.list_agents(
            owner=getattr(args, 'owner', None),
            page_number=getattr(args, 'page_number', 1),
            page_size=getattr(args, 'page_size', 10),
        )
    except ApiError as e:
        return _fail(_api_error_message(e, "list"))
    except Exception as e:
        return _fail(f"list failed: {e}")

    items = result.get("items") or []
    total = result.get("total_count", len(items))

    if not items:
        print("(no agent repositories found)")
        return 0

    headers = ['repo_id', 'framework', 'visibility', 'updated']
    rows = []
    for item in items:
        owner_name = item.get('Path') or item.get('path') or ''
        repo_name = item.get('Name') or item.get('name') or ''
        repo_id = f'{owner_name}/{repo_name}' if owner_name else repo_name
        fw = item.get('Framework') or item.get('framework') or '-'
        vis = item.get('Visibility') or item.get('visibility') or '-'
        updated = item.get('LastUpdatedDate') or item.get('last_updated_date') or '-'
        if isinstance(updated, str) and 'T' in updated:
            updated = updated.split('T')[0]
        rows.append((repo_id, fw, vis, updated))

    col_widths = [len(h) for h in headers]
    for row in rows:
        for i, val in enumerate(row):
            col_widths[i] = max(col_widths[i], len(str(val)))

    fmt = '  '.join(f'{{:<{w}}}' for w in col_widths)
    print(fmt.format(*headers))
    print(fmt.format(*['-' * w for w in col_widths]))
    for row in rows:
        print(fmt.format(*[str(v) for v in row]))

    print(f'\npage {getattr(args, "page_number", 1)} / total {total} (page_size={getattr(args, "page_size", 10)})')
    return 0


def cmd_status(args) -> int:
    """List discoverable sub-agents for a framework."""
    framework = args.framework
    if framework not in ALLOWLIST_REGISTRY:
        return _fail(f"unknown framework '{framework}'. Available: {_frameworks()}")

    spec = _build_allowlist(framework, DEFAULT_AGENT_NAME, getattr(args, 'local_dir', None))
    agents = spec.list_agents()
    print(f"Agents for {framework}:")
    for a in agents:
        tmp = _build_allowlist(framework, a, getattr(args, 'local_dir', None))
        files = tmp.collect_bytes()
        print(f"  {a} — {len(files)} file(s), root: {tmp.workspace_root}")
        for rel in sorted(files):
            print(f"    {rel}")
    return 0


def cmd_upload(args) -> int:
    framework = args.framework
    if framework not in ALLOWLIST_REGISTRY:
        return _fail(f"unknown framework '{framework}'. Available: {_frameworks()}")

    # Resolve local agent name (auto-select if only one).
    local_name, err = _resolve_local_name(args.name, framework, args.local_dir)
    if err:
        return _fail(err)

    spec = _build_allowlist(framework, local_name, args.local_dir)
    root = spec.workspace_root
    resources: Dict[str, bytes] = spec.collect_bytes()
    if not resources:
        display_name = local_name if local_name != GLOBAL_AGENT_NAME else "global"
        return _fail(
            f"no files found for {framework}/{display_name} under {root}. "
            f"Check the path or pass --local_dir."
        )

    total_bytes = sum(len(v) for v in resources.values())
    print(f"Found {len(resources)} file(s) ({total_bytes} bytes) under {root}:")
    for rel in sorted(resources):
        print(f"  {rel} ({len(resources[rel])} B)")

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

    # Resolve remote target.
    # Use the resolved local_name for remote derivation (handles auto-select).
    effective_name = local_name if local_name != GLOBAL_AGENT_NAME else None
    group, repo = _resolve_remote(
        repo=getattr(args, 'repo', None),
        name=effective_name,
        framework=framework,
        username=username,
    )

    # Step 1: upload files via commit interface
    try:
        from .sync import push_resources
        push_resources(client, group, repo, framework, resources)
    except ApiError as e:
        return _fail(_api_error_message(e, "upload"))
    except Exception as e:
        return _fail(f"upload failed: {e}")

    print(
        f"\nUploaded {len(resources)} file(s) to "
        f"{group}/{repo}."
    )
    return 0


def cmd_download(args) -> int:
    if not getattr(args, 'repo', None):
        return _fail("--repo is required for download (the remote repository name)")
    if not args.framework:
        return _fail("--framework is required for download")

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

    # Resolve remote target.
    group, repo = _resolve_remote(
        repo=args.repo,
        name=args.name,
        framework=framework,
        username=username,
    )

    client = UltronClient(server, token)
    try:
        info = client.repo_info(group, repo)
        if info is None:
            return _fail(f"repository {group}/{repo} not found.")
        paths = client.list_repo_files(group, repo)
        if not paths:
            return _fail(f"repository {group}/{repo} has no files.")
        # NOTE: downloads as text (str). Binary files (images, etc.) may lose
        # fidelity when decoded as text. A future binary-aware path is needed
        # for full parity with upload's collect_bytes.
        resources = {
            p: client.download_repo_file(group, repo, p) for p in paths
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

    # Resolve local agent name for writing.
    local_name = args.name or DEFAULT_AGENT_NAME
    spec = _build_allowlist(target_fw, local_name, args.local_dir)
    root = spec.workspace_root

    # Filter downloaded resources by allowlist patterns.
    patterns = spec.resolved_patterns()
    filtered = {k: v for k, v in resources.items() if spec.matches(k, patterns)}
    skipped = set(resources.keys()) - set(filtered.keys())
    if skipped:
        print(f"Skipped {len(skipped)} file(s) not matching allowlist:")
        for s in sorted(skipped):
            print(f"  [skip] {s}")

    if not filtered:
        return _fail("no downloaded files match the local allowlist patterns.")

    print(f"{len(filtered)} file(s) for {group}/{repo} (framework={target_fw}):")
    for rel in sorted(filtered):
        print(f"  {rel} -> {root / rel}")

    if args.dry_run:
        print("\n[dry-run] nothing written.")
        return 0

    written = spec.apply(filtered)
    print(f"\nWrote {len(written)} file(s) under {root}.")
    return 0


def convert_workspace(
    src_spec, source_fw: str, target_fw: str, dst_spec, dry_run: bool = False
) -> int:
    """Shared convert logic: merge → filter defaults → backup → write.

    Returns 0 on success, 1 on failure.
    """
    src_root = src_spec.workspace_root
    resources = src_spec.collect()
    if not resources:
        return _fail(
            f"no {source_fw} files found under {src_root}."
        )

    # Convert via merge_resources to get full action details
    if source_fw == target_fw:
        converted = resources
        default_paths = set()
    else:
        result = merge_resources(
            incoming=resources,
            source_product=source_fw,
            target_product=target_fw,
            source_defaults=get_defaults(source_fw),
            target_defaults=get_defaults(target_fw),
        )
        default_paths = {
            a.path for a in result.actions if a.action == 'default'
        }
        converted = result.merged_files

    dst_root = dst_spec.workspace_root

    # Filter out default-only files: don't create or overwrite with empty templates
    effective = {k: v for k, v in converted.items() if k not in default_paths}
    skipped_defaults = sorted(default_paths & set(converted.keys()))

    print(
        f"Convert {source_fw}/{src_spec.agent_name} ({src_root}) -> "
        f"{target_fw}/{dst_spec.agent_name} ({dst_root}): "
        f"{len(resources)} in, {len(effective)} out"
    )
    for rel in sorted(effective):
        print(f"  {rel} -> {dst_root / rel}")
    if skipped_defaults:
        print(f"  ({len(skipped_defaults)} default template(s) skipped: "
              f"{', '.join(skipped_defaults)})")

    if dry_run:
        print("\n[dry-run] nothing written.")
        return 0

    if not effective:
        print("\nNo effective files to write (all were default templates).")
        return 0

    # Backup existing target files before overwriting
    from .sync import backup_local
    existing = dst_spec.collect()
    if existing:
        backup_path = backup_local(dst_spec, f"{target_fw}_{dst_spec.agent_name}")
        print(f"  Backup: {backup_path}")

    written = dst_spec.apply(effective)
    print(f"\nWrote {len(written)} file(s) under {dst_root}.")
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
    dst_spec = _build_allowlist(target_fw, name, args.out_dir)
    return convert_workspace(src_spec, source_fw, target_fw, dst_spec, dry_run=args.dry_run)


def cmd_watch(args) -> int:
    """Start background bidirectional sync for agent files."""
    from .cache import pid_file
    from .watcher import daemonize, watch_loop

    framework = args.framework
    if framework not in ALLOWLIST_REGISTRY:
        return _fail(f"unknown framework '{framework}'. Available: {_frameworks()}")

    # Resolve local agent name: if --name not given, default to ALL mode.
    if args.name:
        local_name, err = _resolve_local_name(args.name, framework, args.local_dir)
        if err:
            return _fail(err)
    else:
        local_name = ALL_AGENT_NAME

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

    spec = _build_allowlist(framework, local_name, args.local_dir)
    client = UltronClient(server, token)

    # Guard: file-per-agent frameworks with a specific agent name.
    if (not spec.supports_individual_watch
            and local_name not in (GLOBAL_AGENT_NAME, ALL_AGENT_NAME, DEFAULT_AGENT_NAME)):
        return _fail(
            f"'{framework}' has shared files across sub-agents; "
            f"watch only supports global/default mode to avoid sync conflicts. "
            f"Use 'ultron upload/download -n {local_name}' for individual sub-agent operations."
        )

    # Resolve remote target.
    effective_name = args.name if args.name else None
    group, repo = _resolve_remote(
        repo=getattr(args, 'repo', None),
        name=effective_name,
        framework=framework,
        username=username,
    )

    # Guard: check remote repo framework matches local.
    try:
        info = client.repo_info(group, repo)
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
        # repo not found or unreachable — proceed, first push will create it

    interval = 120
    push_only = not getattr(args, "pull", False)
    print(f"Starting sync for {group}/{repo} (interval={interval}s)...")
    print(f"  Framework: {framework}")
    print(f"  Root: {spec.workspace_root}")
    if push_only:
        print(f"  Mode: push-only (local \u2192 remote, will NOT pull remote changes)")
    else:
        print(f"  Mode: bidirectional (local \u2194 remote, WILL pull remote changes to local)")
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
        # Filter by framework/name if provided (filename: {fw}_{name}_{date}_{time}.zip)
        fw_filter = getattr(args, 'framework', None)
        name_filter = getattr(args, 'name', None)
        if fw_filter or name_filter:
            filtered = []
            for f in backups:
                parts = f.stem.rsplit("_", 2)
                prefix = parts[0] if len(parts) >= 3 else f.stem
                delim = "_" if "_" in prefix else "-"
                parts_fw = prefix.split(delim, 1)
                fw = parts_fw[0]
                name = parts_fw[1] if len(parts_fw) > 1 else ""
                if fw_filter and fw != fw_filter:
                    continue
                if name_filter and name != name_filter:
                    continue
                filtered.append(f)
            backups = filtered

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

    # Filter backups by framework/name if provided
    fw_filter = getattr(args, 'framework', None)
    name_filter = getattr(args, 'name', None)
    if fw_filter or name_filter:
        filtered = []
        for f in backups:
            parts = f.stem.rsplit("_", 2)
            prefix = parts[0] if len(parts) >= 3 else f.stem
            delim = "_" if "_" in prefix else "-"
            parts_fw = prefix.split(delim, 1)
            fw = parts_fw[0]
            name = parts_fw[1] if len(parts_fw) > 1 else ""
            if fw_filter and fw != fw_filter:
                continue
            if name_filter and name != name_filter:
                continue
            filtered.append(f)
        backups = filtered

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

