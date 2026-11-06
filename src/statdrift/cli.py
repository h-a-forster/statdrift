"""Command line: battery, envs, run, notes, diff."""

from __future__ import annotations

import argparse

from . import __version__, notes, report, study


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="statdrift", description=__doc__)
    parser.add_argument("--version", action="version", version=__version__)
    commands = parser.add_subparsers(dest="command", required=True)

    commands.add_parser("battery", help="rebuild battery.json and check it against the pin")
    envs = commands.add_parser("envs", help="write, lock and sync the pinned environments")
    envs.add_argument("--only", help="substring of an environment name")
    envs.add_argument("--check", action="store_true", help="run `uv lock --check` per env")
    envs.add_argument("--clean", action="store_true", help="delete the .venv directories")
    run = commands.add_parser("run", help="run the battery in the pinned environments")
    run.add_argument("--only", help="substring of an environment name")
    run.add_argument("--repeat", action="store_true", help="write to results/repeat/")
    commands.add_parser("repeat", help="compare results/ with results/repeat/")
    commands.add_parser("notes", help="fetch any missing release notes and hash them all")
    commands.add_parser("diff", help="write the summaries from the result files")
    args = parser.parse_args(argv)

    if not (study.ROOT / "configs" / "study.toml").exists():
        parser.error(f"no study under {study.ROOT}: run statdrift from a repository checkout")
    if args.command == "battery":
        from . import battery

        print(battery.write(study.ROOT / "battery"))
    elif args.command == "envs":
        for env in study.select(study.environments(study.load_config()), args.only):
            if args.check:
                study.check_lock(env)
            elif args.clean:
                study.clean_env(env)
            else:
                study.create_env(env)
            print(env.name, flush=True)
    elif args.command == "run":
        study.run_all(args.only, repeat=args.repeat)
    elif args.command == "repeat":
        records = report.repeatability(study.ROOT, study.load_config())
        print(sum(r["identical"] for r in records.values()), "of", len(records), "identical")
    elif args.command == "notes":
        notes.download(study.load_config(), study.ROOT)
    elif args.command == "diff":
        report.write()
    return 0
