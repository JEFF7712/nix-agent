import json
import re

from nix_agent import hostattr, runner
from nix_agent.target import (
    Target,
    TargetError,
    attr_candidates,
    config_attr,
    resolve_target,
)


def _missing_config_attr(output: str) -> bool:
    return hostattr.missing_flake_attr(output)


GUARD_CAP = 2048

# Agents often pass a full flake attr path or a leading `config.`; both
# would otherwise be appended after `.config.` and miss.
_ATTR_PREFIX = re.compile(
    r'^(?:(?:nixos|home)Configurations\.("[^"]+"|[^."]+)\.)?config\.(?=.)'
)


def split_attr(attr: str) -> tuple[str | None, str]:
    """(embedded host or None, attr relative to the host's config)."""
    match = _ATTR_PREFIX.match(attr)
    if match is None:
        return None, attr
    host = match.group(1)
    return (host.strip('"') if host else None), attr[match.end() :]


def parse_attrpath(attr: str) -> list[str] | None:
    """Split a Nix dot-separated attrpath into segment names, supporting
    double-quoted segments (e.g. ``systemd.services."kiosk-rotate".enable``).
    Returns None for empty segments, unclosed quotes, or ``${`` interpolation."""
    if not attr or "${" in attr:
        return None
    parts: list[str] = []
    n = len(attr)
    i = 0
    while i < n:
        if attr[i] == ".":
            return None
        if attr[i] == '"':
            i += 1
            buf: list[str] = []
            closed = False
            while i < n:
                ch = attr[i]
                if ch == "\\" and i + 1 < n:
                    nxt = attr[i + 1]
                    buf.append(
                        "\n"
                        if nxt == "n"
                        else "\t"
                        if nxt == "t"
                        else "\r"
                        if nxt == "r"
                        else nxt
                    )
                    i += 2
                    continue
                if ch == '"':
                    i += 1
                    closed = True
                    break
                buf.append(ch)
                i += 1
            if not closed:
                return None
            parts.append("".join(buf))
        else:
            start = i
            while i < n and attr[i] not in '." \t\n\r':
                i += 1
            if i == start:
                return None
            parts.append(attr[start:i])
        if i < n:
            if attr[i] != ".":
                return None
            i += 1
            if i == n:
                return None
    return parts if parts else None


def _nix_str_literal(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"').replace("$", "\\$")
    return f'"{escaped}"'


def _batch_apply_expr(specs: dict[str, dict[str, object]]) -> str:
    specs_literal = _nix_str_literal(json.dumps(specs))
    return f"""
cfg:
let
  specs = builtins.fromJSON {specs_literal};
  scrub = depth: v:
    let r = builtins.tryEval v; in
    if !r.success then {{ ok = false; retry = true; }}
    else
      let t = builtins.typeOf r.value; in
      if t == "lambda" then {{ ok = false; retry = true; }}
      else if t == "int" || t == "float" || t == "bool" || t == "string" || t == "null" then
        {{ ok = true; value = r.value; }}
      else if t == "path" then
        {{ ok = true; value = builtins.toString r.value; }}
      else if t == "set" && ((r.value._type or null) == "derivation" || r.value ? outPath) then
        let o = builtins.tryEval (builtins.toString r.value.outPath); in
        if o.success then {{ ok = true; value = o.value; }} else {{ ok = false; retry = true; }}
      else if depth <= 0 then {{ ok = false; retry = true; }}
      else if t == "list" then
        let len = builtins.length r.value; in
        if len > 512 then
          {{ ok = true; preguarded = true; value = {{ length = len; truncated = true; hint = "value exceeds the size guard; eval a narrower attr or index"; }}; }}
        else
          let items = map (scrub (depth - 1)) r.value; in
          if builtins.all (x: x.ok && !(x.preguarded or false)) items then
            {{ ok = true; value = map (x: x.value) items; }}
          else {{ ok = false; retry = true; }}
      else if t == "set" then
        let
          names = builtins.attrNames r.value;
          len = builtins.length names;
        in
        if len > 128 then
          {{ ok = true; preguarded = true; value = {{ attr_names = names; truncated = true; hint = "value exceeds the size guard; eval a child attr"; }}; }}
        else
          let
            step = acc: n:
              if !acc.ok then acc
              else
                let c = scrub (depth - 1) r.value.${{n}}; in
                if c.ok && !(c.preguarded or false) then
                  {{ ok = true; value = acc.value // {{ ${{n}} = c.value; }}; }}
                else {{ ok = false; retry = true; }};
          in builtins.foldl' step {{ ok = true; value = {{}}; }} names
      else {{ ok = false; retry = true; }};
  select = cur: parts:
    if parts == [] then scrub 6 cur
    else
      let r = builtins.tryEval cur; in
      if !r.success || builtins.typeOf r.value != "set" then {{ ok = false; retry = true; }}
      else
        let h = builtins.head parts; in
        if !(r.value ? ${{h}}) then {{ ok = false; missing = h; }}
        else select r.value.${{h}} (builtins.tail parts);
  evalSpec = spec:
    let primary = select cfg spec.parts; in
    if primary.ok || (primary.retry or false) || spec.hm_parts == null then primary
    else
      let alt = select cfg spec.hm_parts; in
      if alt.ok then alt // {{ hm_rewritten = true; }}
      else if (alt.retry or false) then alt
      else primary;
in builtins.mapAttrs (_: evalSpec) specs
"""


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
    if extra.get("json_fallback") or extra.get("json_parse_failed"):
        payload["hint"] = (
            "Value is Nix text, not structured JSON; it may contain unevaluated "
            "option errors. Request narrower leaf attributes with eval_config."
        )
        if truncated:
            payload["hint"] = "Value is incomplete and truncated. " + str(
                payload["hint"]
            )
    elif truncated:
        payload["hint"] = (
            "Value is incomplete and truncated; request a child attribute "
            "or list index with eval_config."
        )
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
            envelope["_candidate"] = candidate
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


def _batch_probe(
    target: Target,
    candidates: list[str],
    specs: dict[str, dict[str, object]],
) -> tuple[str | None, dict[str, dict[str, object]] | None, int, dict[str, object] | None]:
    """Evaluate all parseable batch specs in one ``nix eval --apply`` call.
    Returns ``(winning_candidate, batch_map_or_None, raw_bytes, unknown_host_or_None)``."""
    expr = _batch_apply_expr(specs)
    pending = list(candidates)
    tried: list[str] = []
    raw_total = 0
    idx = 0
    while idx < len(pending):
        candidate = pending[idx]
        tried.append(candidate)
        installable = f"{config_attr(target, candidate)}.config"
        result = runner.run(["nix", "eval", installable, "--apply", expr, "--json"])
        raw_total += (
            result.raw_bytes
            if result.raw_bytes is not None
            else len(result.stdout) + len(result.stderr)
        )
        if result.ok:
            try:
                parsed = json.loads(result.stdout)
            except json.JSONDecodeError:
                return candidate, None, raw_total, None
            if (
                isinstance(parsed, dict)
                and set(parsed.keys()) == set(specs.keys())
                and all(isinstance(v, dict) and "ok" in v for v in parsed.values())
            ):
                return candidate, parsed, raw_total, None
            return candidate, None, raw_total, None
        if _missing_config_attr(result.output):
            if idx < len(pending) - 1:
                idx += 1
                continue
            more, unknown = hostattr.extra_hosts_or_unknown(target, tried)
            if more:
                pending.extend(more)
                idx += 1
                continue
            if unknown is not None:
                return None, None, raw_total, unknown
        return None, None, raw_total, None
    return None, None, raw_total, None


def _entry_from_batch_hit(
    one: str, rel: str, hit: dict[str, object]
) -> dict[str, object]:
    entry: dict[str, object] = {"attr": one, "status": "ok"}
    if rel != one:
        entry["evaluated_attr"] = rel
    if hit.get("preguarded"):
        entry["value"] = hit["value"]
        entry["truncated"] = True
        entry["hint"] = (
            "Value is incomplete and truncated; request a child attribute "
            "or list index with eval_config."
        )
    else:
        guarded, truncated = guard_value(hit.get("value"))
        entry["value"] = guarded
        if truncated:
            entry["truncated"] = True
            entry["hint"] = (
                "Value is incomplete and truncated; request a child attribute "
                "or list index with eval_config."
            )
    if hit.get("hm_rewritten"):
        entry["hm_rewritten"] = True
        entry["requested_attr"] = rel
    return entry


def eval_config(
    attr: str | list[str],
    flake_uri: str | None = None,
    mode: str = "nixos",
) -> dict[str, object]:
    """Evaluate the final merged value of one or more attrs in the user's
    actual configuration. A list of attrs evaluates in a single Nix call
    when possible (falling back per-attr on errors or unserializable values)
    and returns per-attr results. Values above GUARD_CAP bytes degrade to
    attr names / length / a head slice (truncated: true). The batched
    envelope's resolved_target is the flake ref; the single-attr form's
    resolved_target is the full installable including the attr path."""
    try:
        target = resolve_target(flake_uri, mode)
        candidates = attr_candidates(target)
    except TargetError as exc:
        return {"status": "no_target", "error": str(exc)}

    requested = attr if isinstance(attr, list) else [attr]
    split = [split_attr(one) for one in requested]
    hosts = {host for host, _ in split if host}
    if len(hosts) == 1 and not target.attr:
        host = hosts.pop()
        target = Target(flake_dir=target.flake_dir, attr=host, mode=target.mode)
        candidates = [host]
    relative = {one: rest for one, (_, rest) in zip(requested, split, strict=True)}

    if isinstance(attr, list):
        if not attr:
            return {
                "status": "invalid_attr",
                "error": "attr list must not be empty",
            }
        results: list[dict[str, object]] = []
        raw_total = 0
        batch_map: dict[str, dict[str, object]] | None = None

        if len(attr) >= 2:
            specs: dict[str, dict[str, object]] = {}
            for idx, one in enumerate(attr):
                rel = relative[one]
                parts = parse_attrpath(rel)
                if parts is not None:
                    hm_rel = hostattr.nixos_hm_attr(rel, mode)
                    hm_parts = parse_attrpath(hm_rel) if hm_rel else None
                    specs[str(idx)] = {"parts": parts, "hm_parts": hm_parts}
            if specs:
                winning_host, batch_map, probe_raw, unknown = _batch_probe(
                    target, candidates, specs
                )
                if unknown is not None:
                    return unknown
                raw_total += probe_raw
                if winning_host and not target.attr:
                    target = Target(
                        flake_dir=target.flake_dir,
                        attr=winning_host,
                        mode=target.mode,
                    )
                    candidates = [winning_host]

        for idx, one in enumerate(attr):
            rel = relative[one]
            hit = batch_map.get(str(idx)) if batch_map is not None else None
            if hit is not None and hit.get("ok") is True:
                results.append(_entry_from_batch_hit(one, rel, hit))
                continue
            if (
                hit is not None
                and hit.get("ok") is False
                and not hit.get("retry")
                and isinstance(hit.get("missing"), str)
            ):
                missing_name = str(hit["missing"])
                failed_entry: dict[str, object] = {
                    "attr": one,
                    "status": "failed",
                    "first_error": f"error: attribute '{missing_name}' missing",
                }
                if rel != one:
                    failed_entry["evaluated_attr"] = rel
                results.append(failed_entry)
                continue

            envelope = _eval_one(target, candidates, rel, mode=mode)
            if envelope.get("status") == "unknown_host":
                return envelope
            winning = envelope.pop("_candidate", None)
            if winning and not target.attr:
                target = Target(
                    flake_dir=target.flake_dir, attr=str(winning), mode=target.mode
                )
                candidates = [str(winning)]
            raw_bytes = envelope.get("raw_bytes")
            if isinstance(raw_bytes, int):
                raw_total += raw_bytes
            entry: dict[str, object] = {
                "attr": one,
                "status": envelope["status"],
            }
            if rel != one:
                entry["evaluated_attr"] = rel
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
        failed_count = sum(entry["status"] != "ok" for entry in results)
        status = "ok"
        if failed_count:
            status = "failed" if failed_count == len(results) else "partial"
        response: dict[str, object] = {
            "status": status,
            "resolved_target": target.flake_ref,
            "results": results,
            "failed_count": failed_count,
            "succeeded_count": len(results) - failed_count,
            "raw_bytes": raw_total,
        }
        if failed_count:
            first = next(
                (entry["first_error"] for entry in results if entry.get("first_error")),
                None,
            )
            if first is not None:
                response["first_error"] = first
        return runner.account(response)
    response = _eval_one(target, candidates, relative[attr], mode=mode)
    if relative[attr] != attr and response.get("status") != "unknown_host":
        response["requested_attr"] = attr
        runner.account(response)
    return response
