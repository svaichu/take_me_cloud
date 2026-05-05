"""CLI for listing Lightning AI studios."""

from __future__ import annotations

import argparse
import sys

from take_me_cloud.base import format_studios, list_existing_studios, lock_lightning_ssh_config


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="take-me-cloud",
        description="Manage Lightning AI studio access.",
        epilog="Requires LIGHTNING_API_KEY and LIGHTNING_USER_ID to be set.",
    )
    parser.add_argument("--list", "-ls", action="store_true", help="List accessible studios")
    parser.add_argument(
        "--lock-ssh",
        action="store_true",
        help="Sync Lightning studio SSH entries in ~/.ssh/config while preserving non-Lightning hosts",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.list:
        try:
            print(format_studios(list_existing_studios()))
            return 0
        except (ValueError, RuntimeError) as exc:
            print(f"take-me-cloud: {exc}", file=sys.stderr)
            return 1

    if args.lock_ssh:
        try:
            studios = list_existing_studios()
            kept_non_lightning, synced_lightning = lock_lightning_ssh_config(studios)
            print(
                "SSH config synchronized "
                f"(lightning_hosts={synced_lightning}, non_lightning_hosts_preserved={kept_non_lightning})."
            )
            return 0
        except (ValueError, RuntimeError, OSError) as exc:
            print(f"take-me-cloud: {exc}", file=sys.stderr)
            return 1

    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())