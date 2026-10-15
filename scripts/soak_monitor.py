"""Run a safe JARVIS resource soak. Default is a ten-second CI smoke."""

from __future__ import annotations

import argparse
import json

from core.soak_monitor import run_soak


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--duration", type=float, default=10.0)
    parser.add_argument("--interval", type=float, default=1.0)
    parser.add_argument("--manual", action="store_true", help="Run the documented 30-minute profile.")
    args = parser.parse_args()
    duration = 1800.0 if args.manual else args.duration
    result = run_soak(duration, args.interval, workload=lambda: sum(index * index for index in range(200)))
    print(json.dumps(result.as_dict(), indent=2))
    return 0 if result.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
