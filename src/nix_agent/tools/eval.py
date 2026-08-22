import json

from nix_agent import hostattr, runner
from nix_agent.target import TargetError, attr_candidates, config_attr, resolve_target


def _missing_config_attr(output: str) -> bool:
    return hostattr.missing_flake_attr(output)


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


def _ok_eval(
    installable: str, result: runner.RunResult, value: object, **extra: object
) -> dict[str, object]:
    guarded, truncated = guard_value(value)
    payload: dict[str, object] = {"value": guarded, "output": "", **extra}
    if truncated:
        payload["truncated"] = True
    return runner.envelope("ok", installable, result, **payload)


def _eval_installable(target, candidate: str, attr: str) -> dict[str, object]:
    # Success envelopes pass output="" because envelope() would otherwise
    # setdefault the raw pre-guard stdout next to the guarded value,
    # defeating the size guard. Failures keep raw output for diagnostics.
    installable = f"{config_attr(target, candidate)}.config.{attr}"
    result = runner.run(["nix", "eval", installable, "--json"])
    if result.ok:
        try:
            value = json.loads(result.stdout)
        except json.JSONDecodeError:
            return _ok_eval(
                installable,
                result,
                result.stdout.strip(),
                json_parse_failed=True,
            )
        return _ok_eval(installable, result, value)
    if not _missing_config_attr(result.output):
        raw = runner.run(["nix", "eval", installable])
        if raw.ok:
            return _ok_eval(installable, raw, raw.stdout.strip(), json_fallback=True)
    return runner.envelope("failed", installable, result)


def _eval_one(
    target,
    candidates,
    attr: str,
    *,
    mode: str = "nixos",
    allow_hm_retry: bool = True,
) -> dict[str, object]:
    pending = list(candidates)
    tried: list[str] = []
    failed: dict[str, object] | None = None
    idx = 0
    while idx < len(pending):
        candidate = pending[idx]
        tried.append(candidate)
        envelope = _eval_installable(target, candidate, attr)
        if envelope["status"] == "ok":
            return envelope
        failed = envelope
        output = str(envelope.get("output") or "")
        if _missing_config_attr(output):
            if idx < len(pending) - 1:
                idx += 1
                continue
            more, unknown = hostattr.extra_hosts_or_unknown(target, tried)
            if more:
                pending.extend(more)
                idx += 1
                continue
            if unknown is not None:
                return unknown
        break

    hm = hostattr.nixos_hm_attr(attr, mode) if allow_hm_retry else None
    if hm:
        rewritten = _eval_one(
            target, tried or pending, hm, mode=mode, allow_hm_retry=False
        )
        if rewritten.get("status") == "ok":
            rewritten["requested_attr"] = attr
            rewritten["hm_rewritten"] = True
            return rewritten
        if rewritten.get("status") == "unknown_host":
            return rewritten

    return failed or {
        "status": "failed",
        "error": f"could not evaluate {attr}",
    }


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
        raw_total = 0
        for one in attr:
            envelope = _eval_one(target, candidates, one, mode=mode)
            raw_total += envelope.get("raw_bytes") or 0
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
                "hm_rewritten",
                "requested_attr",
                "hosts",
                "hostname",
                "hint",
            ):
                if key in envelope:
                    entry[key] = envelope[key]
            results.append(entry)
        # Each _eval_one already ran through envelope(), which stamped
        # raw_bytes on it; summing those per-attr sizes is essentially free,
        # so the batched envelope reports a real (not omitted) raw_bytes.
        response: dict[str, object] = {
            "status": "ok",
            "resolved_target": target.flake_ref,
            "results": results,
            "raw_bytes": raw_total,
        }
        if results and all(entry.get("status") != "ok" for entry in results):
            response["status"] = "failed"
            first = next(
                (entry["first_error"] for entry in results if entry.get("first_error")),
                None,
            )
            if first is not None:
                response["first_error"] = first
        return runner.account(response)
    return _eval_one(target, candidates, attr, mode=mode)
