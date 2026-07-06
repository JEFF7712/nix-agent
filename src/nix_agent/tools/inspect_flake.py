import json
from pathlib import Path

MODULE_DIR_CANDIDATES = (
    "modules",
    "modules/nixos",
    "modules/home-manager",
    "modules/darwin",
    "nixos/modules",
    "home",
    "hosts",
    "overlays",
    "pkgs",
    "profiles",
)


def parse_flake_show(shown: dict) -> dict[str, object]:
    """Hosts, homeConfigurations, and formatter from `nix flake show --json`."""
    formatter = "none"
    for per_system in (shown.get("formatter") or {}).values():
        name = str(per_system.get("name", ""))
        if "treefmt" in name:
            formatter = "treefmt"
        elif "nixfmt" in name:
            formatter = "nixfmt"
        elif name:
            formatter = name
        break
    return {
        "hosts": sorted(shown.get("nixosConfigurations") or {}),
        "home_configurations": sorted(shown.get("homeConfigurations") or {}),
        "formatter": formatter,
    }


def classify_hm(hm_in_lock: bool, home_configurations: list) -> str:
    if home_configurations:
        return "standalone"
    if hm_in_lock:
        return "integrated"
    return "none"


def scan_repo(flake_dir: str) -> dict[str, object]:
    """File heuristics that need no evaluation. Unreadable inputs degrade
    to 'unknown' rather than guessing."""
    root = Path(flake_dir)

    hm_in_lock = False
    lock_path = root / "flake.lock"
    if lock_path.is_file():
        try:
            nodes = json.loads(lock_path.read_text()).get("nodes", {})
            hm_in_lock = "home-manager" in nodes
        except (json.JSONDecodeError, OSError):
            pass

    auto_import = "unknown"
    flake_path = root / "flake.nix"
    if flake_path.is_file():
        try:
            text = flake_path.read_text()
            auto_import = "import-tree" if "import-tree" in text else "none"
        except OSError:
            pass

    module_dirs = [
        candidate
        for candidate in MODULE_DIR_CANDIDATES
        if (root / candidate).is_dir() and any((root / candidate).glob("*.nix"))
    ]

    workflows = root / ".github" / "workflows"
    has_ci = workflows.is_dir() and any(
        list(workflows.glob("*.yml")) + list(workflows.glob("*.yaml"))
    )

    return {
        "hm_in_lock": hm_in_lock,
        "auto_import": auto_import,
        "module_dirs": module_dirs,
        "has_justfile": any(
            (root / name).is_file() for name in ("justfile", "Justfile", ".justfile")
        ),
        "has_ci": has_ci,
        "mcp_json": "present" if (root / ".mcp.json").is_file() else "absent",
    }
