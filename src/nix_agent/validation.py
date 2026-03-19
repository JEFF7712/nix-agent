from pathlib import Path


def needs_nix_format(path: str | Path) -> bool:
    return Path(path).suffix == ".nix"
