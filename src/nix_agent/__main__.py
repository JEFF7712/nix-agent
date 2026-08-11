import argparse
import json
from pathlib import Path
import sys

from nix_agent.server import build_server


def main() -> None:
    parser = argparse.ArgumentParser(prog="nix-agent")
    sub = parser.add_subparsers(dest="command")
    inspect = sub.add_parser(
        "inspect-flake",
        help="Print structured facts about a config repo as JSON (onboarding).",
    )
    inspect.add_argument("flake_uri", nargs="?", default=None)

    usage = sub.add_parser(
        "usage",
        help="Summarize local MCP tool usage from the JSONL usage log.",
    )
    usage.add_argument(
        "--path",
        type=Path,
        default=None,
        help="Usage log path (default: $NIX_AGENT_USAGE_LOG_PATH or "
        "$XDG_STATE_HOME/nix-agent/usage.jsonl).",
    )
    usage.add_argument(
        "--json",
        action="store_true",
        help="Print the summary as JSON instead of text.",
    )

    args = parser.parse_args()

    if args.command == "inspect-flake":
        from nix_agent.tools.inspect_flake import inspect_flake

        json.dump(inspect_flake(args.flake_uri), sys.stdout, indent=2)
        sys.stdout.write("\n")
        return

    if args.command == "usage":
        from nix_agent import metrics

        path = args.path if args.path is not None else metrics.log_path()
        summary = metrics.summarize(metrics.load_events(path))
        if args.json:
            payload = dict(summary)
            payload["path"] = str(path)
            json.dump(payload, sys.stdout, indent=2)
            sys.stdout.write("\n")
        else:
            sys.stdout.write(metrics.format_summary(summary, path=path))
        return

    build_server().run(transport="stdio")


if __name__ == "__main__":
    main()
