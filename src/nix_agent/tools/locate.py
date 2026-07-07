import json

from nix_agent import runner
from nix_agent.target import TargetError, attr_candidates, config_attr, resolve_target
from nix_agent.tools.eval import guard_value

# tryEval cannot catch toJSON's hard error on functions, so serializability
# is decided by type-checking (scrub), not by attempting serialization.
# Derivations (sets with outPath) collapse to their store path; recursion
# is depth-capped so huge attrsets stay cheap to force.
_APPLY = """
opt:
let
  scrub = depth: v:
    let t = builtins.typeOf v; in
    if t == "lambda" then "<function>"
    else if t == "set" && v ? outPath then builtins.toString v.outPath
    else if depth == 0 then (if t == "set" || t == "list" then "<" + t + ">" else v)
    else if t == "list" then map (scrub (depth - 1)) v
    else if t == "set" then builtins.mapAttrs (n: x: scrub (depth - 1) x) v
    else v;
  force = v:
    let r = builtins.tryEval (builtins.deepSeq v v); in
    if r.success then r.value else "<unevaluable>";
in
if (opt._type or null) == "option" then {
  is_option = true;
  declarations = opt.declarations or [];
  definitions = map
    (d: { file = d.file; value = force (scrub 3 d.value); })
    (opt.definitionsWithLocations or []);
} else {
  is_option = false;
  declarations = [];
  definitions = [];
}
"""

_NOT_AN_OPTION_HINT = (
    "not a defined option on this configuration; for plain config values "
    "use eval_config, for option discovery use mcp-nixos"
)


def _missing_attr(output: str) -> bool:
    return "does not provide attribute" in output


def _config_root_exists(target, candidate: str) -> bool:
    probe = runner.run(
        [
            "nix",
            "eval",
            f"{config_attr(target, candidate)}.options",
            "--apply",
            "o: true",
            "--json",
        ]
    )
    return probe.ok


def locate_option(
    attr: str,
    flake_uri: str | None = None,
    mode: str = "nixos",
) -> dict[str, object]:
    """Where does this configuration set an option: the files declaring it
    and every file defining it, with the value each contributes. The
    bridge between mcp-nixos (what options exist) and editing (which file
    to change)."""
    try:
        target = resolve_target(flake_uri, mode)
        candidates = attr_candidates(target)
    except TargetError as exc:
        return {"status": "no_target", "error": str(exc)}

    installable = ""
    result = runner.RunResult(ok=False, command=[], stdout="", stderr="")
    for i, candidate in enumerate(candidates):
        installable = f"{config_attr(target, candidate)}.options.{attr}"
        result = runner.run(["nix", "eval", installable, "--apply", _APPLY, "--json"])
        if result.ok:
            break
        if _missing_attr(result.output) and i < len(candidates) - 1:
            continue
        break

    if not result.ok:
        # nix echoes the full requested attrpath whether the option or the
        # host attr is what's missing; probing the options root is the only
        # way to tell a bad option apart from a bad flake_uri/hostname.
        if _missing_attr(result.output) and _config_root_exists(target, candidate):
            return {
                "status": "not_an_option",
                "resolved_target": installable,
                "attr": attr,
                "hint": _NOT_AN_OPTION_HINT,
            }
        return runner.envelope("failed", installable, result, attr=attr)

    try:
        located = json.loads(result.stdout)
    except json.JSONDecodeError:
        return runner.envelope(
            "failed",
            installable,
            result,
            attr=attr,
            error="locate output was not valid JSON",
        )
    if not located.get("is_option"):
        return {
            "status": "not_an_option",
            "resolved_target": installable,
            "attr": attr,
            "hint": _NOT_AN_OPTION_HINT,
        }

    definitions = []
    for definition in located.get("definitions", []):
        value, truncated = guard_value(definition.get("value"))
        entry: dict[str, object] = {
            "file": definition.get("file"),
            "value": value,
        }
        if truncated:
            entry["truncated"] = True
        definitions.append(entry)
    response: dict[str, object] = {
        "status": "ok",
        "resolved_target": installable,
        "command": result.command,
        "attr": attr,
        "declarations": located.get("declarations", []),
        "definitions": definitions,
        "raw_bytes": (
            result.raw_bytes
            if result.raw_bytes is not None
            else len(result.stdout) + len(result.stderr)
        ),
    }
    return runner.account(response)
