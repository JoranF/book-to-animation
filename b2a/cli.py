"""Command line: python -m b2a.cli make --book courage-to-be-disliked --topic "Separation of tasks"."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from . import pipeline


def main() -> None:
    parser = argparse.ArgumentParser(prog="b2a")
    sub = parser.add_subparsers(dest="cmd", required=True)
    make = sub.add_parser("make", help="make one Short")
    make.add_argument("--book", default="courage-to-be-disliked")
    make.add_argument("--topic", required=True)
    make.add_argument("--idea", default="")
    make.add_argument("--script", type=Path, help="use this script.json instead of writing one")
    make.add_argument("--id", help="continue an earlier run")
    sub.add_parser("list", help="list finished Shorts")
    args = parser.parse_args()

    if args.cmd == "make":
        script = json.loads(args.script.read_text()) if args.script else None
        meta = pipeline.make_short(args.book, args.topic, args.idea, args.id, script,
                                   progress=lambda step: print(f"[b2a] {step}"))
        print(json.dumps(meta, indent=2))
    else:
        for meta in pipeline.list_shorts():
            print(f"{meta['id']}  {meta['duration_seconds']}s  ${meta['estimated_cost_usd']}  {meta['title']}")


if __name__ == "__main__":
    main()
