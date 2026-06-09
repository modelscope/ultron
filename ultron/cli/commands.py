# Copyright (c) ModelScope Contributors. All rights reserved.
"""Implementations of the ``ultron`` CLI subcommands."""
import base64
import getpass
import sys
from pathlib import Path
from typing import Dict

from ultron.services.harness.allowlist import ALLOWLIST_REGISTRY

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
        actions = [
            {
                "action": "update",
                "path": rel,
                "type": "normal",
                "size": len(content.encode("utf-8")),
                "content": base64.b64encode(content.encode("utf-8")).decode("ascii"),
                "encoding": "base64",
            }
            for rel, content in sorted(resources.items())
        ]
        message = args.message or f"upload {framework}/{args.name}"
        result = client.commit(username, args.name, actions, message)
    except ApiError as e:
        return _fail(f"upload failed ({e.detail})")

    data = result.get("data", {})
    print(
        f"\nUploaded {data.get('files', len(resources))} file(s) to "
        f"{username}/{args.name} (revision {data.get('Revision', '?')})."
    )
    return 0
