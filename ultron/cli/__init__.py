# Copyright (c) ModelScope Contributors. All rights reserved.
"""``ultron`` command-line interface.

Subcommands:

* ``ultron login``  -- authenticate against an ultron server and store the token.
* ``ultron upload`` -- locate a sub-agent's files for a framework and upload them
  to the agent repository.
"""
import argparse
import sys

from .commands import cmd_login, cmd_upload


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ultron",
        description="Ultron command-line interface.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # ---- login ----
    p_login = sub.add_parser("login", help="Authenticate and store an API token.")
    p_login.add_argument("--server", help="Server URL, e.g. http://localhost:9999")
    p_login.add_argument("--username", help="Username (prompted if omitted).")
    p_login.add_argument("--password", help="Password (prompted if omitted).")
    p_login.set_defaults(func=cmd_login)

    # ---- upload ----
    p_up = sub.add_parser(
        "upload",
        help="Upload a framework sub-agent's files to the agent repository.",
    )
    p_up.add_argument(
        "--framework", "-f", required=True,
        help="Agent framework / bot type (e.g. qoder, qwenpaw, nanobot).",
    )
    p_up.add_argument(
        "--name", "-n",
        help="Internal sub-agent name; also the repository name (agent_id).",
    )
    p_up.add_argument(
        "--local_dir", "-d",
        help="Override the workspace root to scan (default: framework's path).",
    )
    p_up.add_argument("--message", "-m", help="Commit message.")
    p_up.add_argument("--server", help="Server URL override.")
    p_up.add_argument("--token", help="API token override.")
    p_up.add_argument(
        "--list", action="store_true",
        help="List sub-agents discovered on disk for the framework and exit.",
    )
    p_up.add_argument(
        "--dry-run", action="store_true",
        help="Show the files that would be uploaded without uploading.",
    )
    p_up.set_defaults(func=cmd_upload)

    return parser


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
