import json

from nix_agent import runner
from nix_agent.target import TargetError, attr_candidates, config_attr, resolve_target


def _missing_config_attr(output: str) -> bool:
    return "does not provide attribute" in output


GUARD_CAP = 2048


def guard_value(value: object) -> tuple[object, bool]:
    """Cap the context cost of a value: over GUARD_CAP bytes of JSON, an
    attrset degrades to its attr names, a list to its length, a scalar to
    a head slice. Returns (value, truncated)."""
    try:
        encoded = json.dumps(value)
    except (TypeError, ValueError):
        encoded = str(value)
    if len(encoded) <= GUARD_CAP:
        return value, False
    if isinstance(value, dict):
        return {
            "attr_names": sorted(value),
            "truncated": True,
            "hint": "value exceeds the size guard; eval a child attr",
        }, True
    if isinstance(value, list):
        return {
            "length": len(value),
            "truncated": True,
            "hint": "value exceeds the size guard; eval a narrower attr or index",
        }, True
    text = value if isinstance(value, str) else encoded
    return text[:GUARD_CAP] + "... [nix-agent: truncated]", True


def eval_config(
    attr: str,
    flake_uri: str | None = None,
    mode: str = "nixos",
) -> dict[str, object]:
    """Evaluate the final merged value of an attr in the user's actual
    configuration. Complements mcp-nixos: that documents what an option
    means; this reports what this machine resolved it to."""
    try:
        target = resolve_target(flake_uri, mode)
        candidates = attr_candidates(target)
    except TargetError as exc:
        return {"status": "no_target", "error": str(exc)}

    installable = ""
    result = runner.RunResult(ok=False, command=[], stdout="", stderr="")
    for i, candidate in enumerate(candidates):
        installable = f"{config_attr(target, candidate)}.config.{attr}"
        result = runner.run(["nix", "eval", installable, "--json"])
        if result.ok:
            try:
                value = json.loads(result.stdout)
            except json.JSONDecodeError:
                return runner.envelope(
                    "ok",
                    installable,
                    result,
                    value=result.stdout.strip(),
                    json_parse_failed=True,
                )
            return runner.envelope("ok", installable, result, value=value)
        if _missing_config_attr(result.output) and i < len(candidates) - 1:
            continue
        if not _missing_config_attr(result.output):
            raw = runner.run(["nix", "eval", installable])
            if raw.ok:
                return runner.envelope(
                    "ok",
                    installable,
                    raw,
                    value=raw.stdout.strip(),
                    json_fallback=True,
                )
        break
    return runner.envelope("failed", installable, result)
