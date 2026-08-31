#!/usr/bin/env python3
"""Small shell bridge for the shared PID-owned usage-ledger lock."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import mborch  # noqa: E402


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="action", required=True)
    acquire = sub.add_parser("acquire")
    acquire.add_argument("--lock", required=True)
    acquire.add_argument("--owner-pid", required=True, type=int)
    acquire.add_argument("--timeout", type=float, default=5.0)
    acquire.add_argument("--poll", type=float, default=0.02)
    acquire.add_argument("--stale-grace", type=float, default=1.0)
    release = sub.add_parser("release")
    release.add_argument("--lock", required=True)
    release.add_argument("--owner-pid", required=True, type=int)
    release.add_argument("--token", required=True)
    args = parser.parse_args(argv)
    lock = Path(args.lock)
    if args.action == "acquire":
        try:
            token = mborch.acquire_directory_lock(
                lock,
                timeout_seconds=args.timeout,
                poll_seconds=args.poll,
                stale_grace_seconds=args.stale_grace,
                owner_pid=args.owner_pid,
            )
        except (OSError, TimeoutError, ValueError) as exc:
            print(f"ledger-lock: {exc}", file=sys.stderr)
            return 1
        print(token)
        return 0
    return 0 if mborch.release_directory_lock(
        lock, args.token, owner_pid=args.owner_pid,
    ) else 1


if __name__ == "__main__":
    raise SystemExit(main())
