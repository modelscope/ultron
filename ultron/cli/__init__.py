# Copyright (c) ModelScope Contributors. All rights reserved.
"""``ultron`` command-line interface.

Subcommands:

* ``ultron login``  -- authenticate against an ultron server and store the token.
* ``ultron upload`` -- locate a sub-agent's files for a framework and upload them
  to the agent repository.
"""
import argparse
import sys

from .commands import cmd_convert, cmd_download, cmd_login, cmd_recover, cmd_stop, cmd_upload, cmd_watch


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ultron",
        description="Ultron command-line interface.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # ---- login ----
    p_login = sub.add_parser("login", help="Authenticate with an API token.")
    p_login.add_argument("--server", help="Server URL, e.g. http://localhost:9999")
    p_login.add_argument("--token", help="API token (prompted if omitted). Also reads ULTRON_TOKEN env.")
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

    # ---- download ----
    p_dl = sub.add_parser(
        "download",
        help="Download a sub-agent's files from the agent repository to disk.",
    )
    p_dl.add_argument(
        "--name", "-n", required=True,
        help="Repository / sub-agent name to download.",
    )
    p_dl.add_argument(
        "--framework", "-f",
        help="Source framework / bot type (default: read from the stored repository).",
    )
    p_dl.add_argument(
        "--target", "-t",
        help="Convert to this framework's format before writing (default: same as source).",
    )
    p_dl.add_argument(
        "--local_dir", "-d",
        help="Override the workspace root to write into (default: framework's path).",
    )
    p_dl.add_argument("--server", help="Server URL override.")
    p_dl.add_argument("--token", help="API token override.")
    p_dl.add_argument(
        "--dry-run", action="store_true",
        help="Show the files that would be written without writing.",
    )
    p_dl.set_defaults(func=cmd_download)

    # ---- convert (local only, no network) ----
    p_cv = sub.add_parser(
        "convert",
        help="Convert a local workspace from one framework's format to another.",
    )
    p_cv.add_argument(
        "--from", dest="source", required=True,
        help="Source framework / bot type to read.",
    )
    p_cv.add_argument(
        "--to", dest="target", required=True,
        help="Target framework / bot type to write.",
    )
    p_cv.add_argument(
        "--name", "-n",
        help="Sub-agent name (selects source files; default 'default').",
    )
    p_cv.add_argument(
        "--local_dir", "-d",
        help="Source workspace root to read (default: source framework's path).",
    )
    p_cv.add_argument(
        "--out", "-o",
        help="Destination directory to write (default: target framework's path).",
    )
    p_cv.add_argument(
        "--dry-run", action="store_true",
        help="Show the converted files without writing.",
    )
    p_cv.set_defaults(func=cmd_convert)

    # ---- watch ----
    p_watch = sub.add_parser(
        "watch",
        help="Sync agent files from cloud and watch for local changes.",
    )
    p_watch.add_argument(
        "--framework", "-f", required=True,
        help="Agent framework / bot type.",
    )
    p_watch.add_argument(
        "--name", "-n", required=True,
        help="Sub-agent / repository name.",
    )
    p_watch.add_argument("--local_dir", "-d", help="Override workspace root.")
    p_watch.add_argument("--server", help="Server URL override.")
    p_watch.add_argument("--token", help="API token override.")
    p_watch.add_argument(
        "--interval", type=int, default=60,
        help="Sync poll interval in seconds (default: 60).",
    )
    p_watch.set_defaults(func=cmd_watch)

    # ---- stop ----
    p_stop = sub.add_parser("stop", help="Stop the background watch process.")
    p_stop.set_defaults(func=cmd_stop)

    # ---- recover ----
    p_recover = sub.add_parser(
        "recover",
        help="Recover agent files from a backup zip in ~/.ultron/cache/.",
    )
    p_recover.add_argument(
        "filename",
        help="Backup zip filename (e.g. my-agent_20260609_143022.zip).",
    )
    p_recover.add_argument(
        "--framework", "-f", required=True,
        help="Agent framework (needed to locate workspace root).",
    )
    p_recover.add_argument("--name", "-n", help="Agent name (inferred from filename if omitted).")
    p_recover.add_argument("--local_dir", "-d", help="Override workspace root.")
    p_recover.set_defaults(func=cmd_recover)

    return parser


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
