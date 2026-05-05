"""CLI for listing Lightning AI studios."""

from __future__ import annotations

import argparse
import sys

from take_me_cloud.base import format_studios, list_existing_studios


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="take-me-cloud",
        description="List Lightning AI studios.",
        epilog="Requires LIGHTNING_API_KEY and LIGHTNING_USER_ID to be set.",
    )
    parser.add_argument("--list", "-ls", action="store_true", help="List accessible studios")
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

    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())