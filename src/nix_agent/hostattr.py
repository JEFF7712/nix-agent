"""Hostname and Home Manager attr recovery so agents do not stall."""

from nix_agent.target import (
    Target,
    TargetError,
    attr_candidates,
    hm_user_attr,
    matched_hosts,
    unknown_host_envelope,
)
from nix_agent.tools.inspect_flake import list_flake_configs


def missing_flake_attr(output: str) -> bool:
    return "does not provide attribute" in output


def extra_hosts_or_unknown(
    target: Target, tried: list[str]
) -> tuple[list[str], dict | None]:
    """More config names to try after a missing-attr failure, or unknown_host.

    Explicit `flake_uri#attr` is never silently rewritten; implicit hostname
    guesses may fall back to a unique flake host or a unique prefix/suffix
    match.
    """
    hosts = list_flake_configs(target.flake_dir, target.mode)
    if hosts is None:
        return [], None
    if target.attr is not None:
        if target.attr in hosts:
            return [], None
        return [], unknown_host_envelope(
            hostname=target.attr,
            hosts=hosts,
            flake_dir=target.flake_dir,
            mode=target.mode,
        )
    guess = tried[-1] if tried else ""
    more = [name for name in matched_hosts(guess, hosts) if name not in tried]
    if more:
        return more, None
    if guess in hosts:
        return [], None
    return [], unknown_host_envelope(
        hostname=guess,
        hosts=hosts,
        flake_dir=target.flake_dir,
        mode=target.mode,
    )


def bind_implicit_host(target: Target) -> Target | dict[str, object]:
    """Fill in target.attr from flake hosts when the caller omitted it."""
    if target.attr:
        return target
    hosts = list_flake_configs(target.flake_dir, target.mode)
    if hosts is None:
        return target
    try:
        candidates = attr_candidates(target)
    except TargetError:
        candidates = []
    for candidate in candidates:
        if candidate in hosts:
            return Target(flake_dir=target.flake_dir, attr=candidate, mode=target.mode)
    guess = candidates[0] if candidates else ""
    matched = matched_hosts(guess, hosts)
    if len(matched) == 1:
        return Target(flake_dir=target.flake_dir, attr=matched[0], mode=target.mode)
    return unknown_host_envelope(
        hostname=guess,
        hosts=hosts,
        flake_dir=target.flake_dir,
        mode=target.mode,
    )


def nixos_hm_attr(attr: str, mode: str) -> str | None:
    if mode != "nixos":
        return None
    return hm_user_attr(attr)
