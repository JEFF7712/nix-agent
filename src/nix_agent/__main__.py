import argparse
import json
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

    args = parser.parse_args()

    if args.command == "inspect-flake":
        from nix_agent.tools.inspect_flake import inspect_flake

        json.dump(inspect_flake(args.flake_uri), sys.stdout, indent=2)
        sys.stdout.write("\n")
        return

    build_server().run(transport="stdio")


if __name__ == "__main__":
    main()
