"""CLI: python -m last_analog_designers fixtures/week.json"""

from __future__ import annotations

import sys
from pathlib import Path

from last_analog_designers.search import format_details, format_table, load_week, run_week, to_json

_FLAGS = {"--verbose", "--json", "--help", "-h"}


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    unknown = [arg for arg in args if arg.startswith("-") and arg not in _FLAGS]
    if unknown:
        print(f"unknown flag: {unknown[0]}", file=sys.stderr)
        print(_usage(), file=sys.stderr)
        return 2
    paths = [arg for arg in args if arg not in _FLAGS]
    if "--help" in args or "-h" in args:
        print(_usage())
        return 0 if len(paths) == 0 else 2
    if len(paths) != 1:
        print(_usage(), file=sys.stderr)
        return 2
    try:
        week = load_week(Path(paths[0]))
        report = run_week(week)
    except (OSError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    if "--json" in args:
        print(to_json(report), end="")
    else:
        print(format_table(report))
        if "--verbose" in args:
            print()
            print(format_details(report))
    return 0


def _usage() -> str:
    return "usage: python -m last_analog_designers [--verbose] [--json] <week.json>"


if __name__ == "__main__":
    raise SystemExit(main())
