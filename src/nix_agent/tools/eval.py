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


def _eval_one(target, candidates, attr: str) -> dict[str, object]:
    # Success envelopes pass output="" because envelope() would otherwise
    # setdefault the raw pre-guard stdout next to the guarded value,
    # defeating the size guard. Failures keep raw output for diagnostics.
    installable = ""
    result = runner.RunResult(ok=False, command=[], stdout="", stderr="")
    for i, candidate in enumerate(candidates):
        installable = f"{config_attr(target, candidate)}.config.{attr}"
        result = runner.run(["nix", "eval", installable, "--json"])
        if result.ok:
            try:
                value = json.loads(result.stdout)
            except json.JSONDecodeError:
                guarded, truncated = guard_value(result.stdout.strip())
                extra: dict[str, object] = {
                    "value": guarded,
                    "json_parse_failed": True,
                    "output": "",
                }
                if truncated:
                    extra["truncated"] = True
                return runner.envelope("ok", installable, result, **extra)
            guarded, truncated = guard_value(value)
            extra = {"value": guarded, "output": ""}
            if truncated:
                extra["truncated"] = True
            return runner.envelope("ok", installable, result, **extra)
        if _missing_config_attr(result.output) and i < len(candidates) - 1:
            continue
        if not _missing_config_attr(result.output):
            raw = runner.run(["nix", "eval", installable])
            if raw.ok:
                guarded, truncated = guard_value(raw.stdout.strip())
                extra = {"value": guarded, "json_fallback": True, "output": ""}
                if truncated:
                    extra["truncated"] = True
                return runner.envelope("ok", installable, raw, **extra)
        break
    return runner.envelope("failed", installable, result)


def eval_config(
    attr: str | list[str],
    flake_uri: str | None = None,
    mode: str = "nixos",
) -> dict[str, object]:
    """Evaluate the final merged value of one or more attrs in the user's
    actual configuration. A list of attrs evaluates each in one tool call
    and returns per-attr results. Values above GUARD_CAP bytes degrade to
    attr names / length / a head slice (truncated: true). The batched
    envelope's resolved_target is the flake ref; the single-attr form's
    resolved_target is the full installable including the attr path."""
    try:
        target = resolve_target(flake_uri, mode)
        candidates = attr_candidates(target)
    except TargetError as exc:
        return {"status": "no_target", "error": str(exc)}

    if isinstance(attr, list):
        if not attr:
            return {
                "status": "invalid_attr",
                "error": "attr list must not be empty",
            }
        results = []
        for one in attr:
            envelope = _eval_one(target, candidates, one)
            entry: dict[str, object] = {
                "attr": one,
                "status": envelope["status"],
            }
            for key in (
                "value",
                "truncated",
                "first_error",
                "error_detail",
                "json_fallback",
                "json_parse_failed",
            ):
                if key in envelope:
                    entry[key] = envelope[key]
            results.append(entry)
        return {
            "status": "ok",
            "resolved_target": target.flake_ref,
            "results": results,
        }
    return _eval_one(target, candidates, attr)
