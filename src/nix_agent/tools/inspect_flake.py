import json
from pathlib import Path

from nix_agent import runner
from nix_agent.target import TargetError, resolve_target

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


def inspect_flake(flake_uri: str | None = None) -> dict[str, object]:
    """Structured facts about a config repo in one call: hosts, HM
    integration, module layout, formatter, tooling. The discovery step
    for the /nix-agent-init onboarding skill. Facts that cannot be
    determined are None/'unknown', never guessed."""
    try:
        target = resolve_target(flake_uri, "nixos")
    except TargetError:
        try:
            target = resolve_target(flake_uri, "home-manager")
        except TargetError as exc:
            return {"status": "no_target", "error": str(exc)}

    flake_dir = target.flake_dir
    repo = scan_repo(flake_dir)

    result = runner.run(["nix", "flake", "show", flake_dir, "--json"])
    facts: dict[str, object]
    extra: dict[str, object] = {}
    if result.ok:
        try:
            shown = json.loads(result.stdout)
        except json.JSONDecodeError:
            shown = None
        if isinstance(shown, dict):
            facts = parse_flake_show(shown)
        else:
            facts = {}
            extra["note"] = "flake show output was not valid JSON"
    else:
        facts = {}
        extra["note"] = "flake show failed; evaluated facts unavailable"
        first = runner.extract_first_error(result.output)
        if first:
            extra["first_error"] = first

    hosts = facts.get("hosts")
    home_configurations = facts.get("home_configurations")
    if facts:
        hm_integration = classify_hm(
            bool(repo["hm_in_lock"]), list(home_configurations or [])
        )
        formatter = facts["formatter"]
    else:
        hosts = None
        home_configurations = None
        hm_integration = "unknown"
        formatter = "unknown"

    lint_tools = sorted(
        name for name in ("statix", "deadnix") if runner.resolve_binary(name)
    )
    return {
        "status": "ok",
        "flake_dir": flake_dir,
        "hosts": hosts,
        "home_configurations": home_configurations,
        "hm_integration": hm_integration,
        "module_dirs": repo["module_dirs"],
        "auto_import": repo["auto_import"],
        "formatter": formatter,
        "lint_tools": lint_tools,
        "has_justfile": repo["has_justfile"],
        "has_ci": repo["has_ci"],
        "mcp_json": repo["mcp_json"],
        **extra,
    }
