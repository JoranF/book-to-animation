"""Command line: python -m b2a.cli make --episode next   (or --episode n3-03, or --topic "...")."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from . import assets, music, pipeline, plan as plan_mod, script as script_mod, settings, sfx, trends


def main() -> None:
    parser = argparse.ArgumentParser(prog="b2a")
    sub = parser.add_subparsers(dest="cmd", required=True)
    make = sub.add_parser("make", help="make one Short")
    make.add_argument("--book", default="courage-to-be-disliked")
    make.add_argument("--episode", help="episode id from the plan, or 'next'")
    make.add_argument("--topic", default="", help="free topic instead of an episode")
    make.add_argument("--idea", default="")
    make.add_argument("--script", type=Path, help="use this script.json instead of writing one")
    make.add_argument("--id", help="continue an earlier run")
    sub.add_parser("list", help="list finished Shorts")
    episodes = sub.add_parser("episodes", help="show the episode plan of a book")
    episodes.add_argument("--book", default="courage-to-be-disliked")
    plan = sub.add_parser("plan", help="let Claude draft an episode plan for a book")
    plan.add_argument("--book", required=True)
    trend = sub.add_parser("trends", help="research what works in the niche now (run weekly)")
    trend.add_argument("--book", default="courage-to-be-disliked")
    sub.add_parser("sfx", help="make the retro sound effect library")
    tracks = sub.add_parser("music", help="fill the ACE-Step music library (needs ACESTEP_URL)")
    tracks.add_argument("--mood", action="append", choices=list(music.MOODS))
    lib = sub.add_parser("assets", help="the asset library: list, rebuild, reset, preview")
    lib.add_argument("action", choices=["list", "rebuild", "unmark", "reset", "preview", "new"])
    lib.add_argument("name", nargs="?", help="asset name, e.g. smartphone")
    lib.add_argument("--kind", choices=list(assets.KINDS), default="prop")
    lib.add_argument("--note", default="", help="what should change (rebuild) or what it is (new)")
    lib.add_argument("--now", action="store_true", help="rebuild right away instead of the next time it is used")
    args = parser.parse_args()
    settings.apply()   # the models chosen in the dashboard, if any

    if args.cmd == "make":
        script = json.loads(args.script.read_text()) if args.script else None
        if not (args.episode or args.topic or args.id):
            parser.error("give --episode or --topic")
        meta = pipeline.make_short(args.book, args.topic, args.idea, args.id, script,
                                   progress=lambda step: print(f"[b2a] {step}"), episode_id=args.episode)
        print(json.dumps(meta, indent=2))
    elif args.cmd == "assets":
        if args.action == "list":
            for a in assets.catalog():
                flag = " [rebuild]" if a.get("rebuild") else " [locked]" if a.get("locked") else ""
                print(f"{a['kind']:<9} {a['name']:<22} {a['source']:<15} v{a.get('version', '-')} "
                      f"used {a.get('used', 0)}{flag}  {a.get('description', '')}")
            return
        if not args.name:
            parser.error("give the asset name")
        if args.action == "new":
            asset, made = assets.ensure(args.kind, args.name, args.note)
            print(("made " if made else "reused ") + f"{asset['kind']} '{asset['name']}'")
        elif args.action == "rebuild":
            if args.now:
                assets.mark_rebuild(args.kind, args.name, args.note)
                asset = assets.rebuild(args.kind, args.name, args.note)
                print(f"rebuilt {args.kind} '{args.name}', now v{asset['version']}")
            else:
                assets.mark_rebuild(args.kind, args.name, args.note)
                print(f"{args.kind} '{args.name}' is rebuilt the next time a Short uses it")
        elif args.action == "unmark":
            assets.mark_rebuild(args.kind, args.name, on=False)
        elif args.action == "reset":
            assets.reset(args.kind, args.name)
        elif args.action == "preview":
            asset = assets.get(args.kind, args.name)
            print(assets.make_preview(asset) if asset else f"no {args.kind} '{args.name}'")
    elif args.cmd == "episodes":
        made = pipeline.made_episodes(args.book)
        for ep in plan_mod.episodes(args.book):
            print(f"{'x' if ep['id'] in made else ' '} {ep['id']}  {ep['format']:<12} {ep['hook']}")
    elif args.cmd == "trends":
        result = trends.run(args.book)
        print(result.get("summary", ""))
        print(f"{result['post_count']} posts from {', '.join(result['sources'])}; "
              f"skipped: {'; '.join(result['errors']) or 'none'}")
    elif args.cmd == "sfx":
        for path in sfx.build_library():
            print(path)
    elif args.cmd == "music":
        if not music.acestep_enabled():
            parser.error("set ACESTEP_URL to the ACE-Step service first")
        for path in music.fill_library(args.mood):
            print(path)
    elif args.cmd == "plan":
        path = plan_mod.plan_path(args.book)
        if path.exists():
            parser.error(f"{path} already exists")
        path.write_text(json.dumps(plan_mod.generate_plan(script_mod.load_book(args.book)), indent=1, ensure_ascii=False))
        print(f"Wrote {path}. Read it through before making Shorts from it.")
    else:
        for meta in pipeline.list_shorts():
            print(f"{meta['id']}  {meta['duration_seconds']}s  ${meta['estimated_cost_usd']}  {meta['title']}")


if __name__ == "__main__":
    main()
