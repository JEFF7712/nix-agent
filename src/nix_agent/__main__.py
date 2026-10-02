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

    bootstrap = sub.add_parser(
        "bootstrap-rebuild",
        help="First privileged switch: sudo -n, or print a one-shot TTY command.",
    )
    bootstrap.add_argument("flake_uri", nargs="?", default=None)
    bootstrap.add_argument(
        "--mode",
        default="nixos",
        choices=("nixos", "home-manager"),
    )

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
    usage.add_argument(
        "--compare-shell",
        action="store_true",
        help="Also scan interactive shell histories for direct nix commands "
        "and compare against MCP tool calls.",
    )

    args = parser.parse_args()

    if args.command == "inspect-flake":
        from nix_agent.runner import strip_accounting
        from nix_agent.tools.inspect_flake import inspect_flake

        json.dump(
            strip_accounting(inspect_flake(args.flake_uri)),
            sys.stdout,
            indent=2,
        )
        sys.stdout.write("\n")
        return

    if args.command == "bootstrap-rebuild":
        from nix_agent.bootstrap import bootstrap_rebuild
        from nix_agent.runner import strip_accounting

        payload = strip_accounting(bootstrap_rebuild(args.flake_uri, mode=args.mode))
        json.dump(payload, sys.stdout, indent=2)
        sys.stdout.write("\n")
        status = payload.get("status")
        if status == "needs_bootstrap":
            raise SystemExit(2)
        if status not in {"ok", "degraded"}:
            raise SystemExit(1)
        return

    if args.command == "usage":
        from nix_agent import metrics

        path = args.path if args.path is not None else metrics.log_path()
        summary = metrics.summarize(metrics.load_events(path))
        shell = metrics.scan_shell_history() if args.compare_shell else None
        if args.json:
            payload = dict(summary)
            payload["path"] = str(path)
            if shell is not None:
                payload["shell"] = shell
            json.dump(payload, sys.stdout, indent=2)
            sys.stdout.write("\n")
        else:
            sys.stdout.write(metrics.format_summary(summary, path=path))
            if shell is not None:
                sys.stdout.write(metrics.format_comparison(summary, shell))
        return

    build_server().run(transport="stdio")


if __name__ == "__main__":
    main()
