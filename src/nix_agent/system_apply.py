import subprocess


def run_dry_activate(flake_uri: str) -> str:
    try:
        result = subprocess.run(
            ["sudo", "nixos-rebuild", "dry-activate", "--flake", flake_uri],
            check=True,
            capture_output=True,
            text=True,
        )
        return result.stdout
    except subprocess.CalledProcessError as exc:
        return (exc.stderr or "").strip()


def run_switch(flake_uri: str) -> str:
    result = subprocess.run(
        ["sudo", "nixos-rebuild", "switch", "--flake", flake_uri],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout
