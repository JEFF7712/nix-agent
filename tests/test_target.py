from pathlib import Path

import pytest

from nix_agent import target as target_mod
from nix_agent.target import (
    Target,
    TargetError,
    attr_candidates,
    config_attr,
    constrain_privileged_target,
    is_remote_flake_ref,
    resolve_target,
)


def test_explicit_uri_with_attr():
    t = resolve_target("/home/me/flake#myhost", "nixos")
    assert t == Target(flake_dir="/home/me/flake", attr="myhost", mode="nixos")
    assert t.flake_ref == "/home/me/flake#myhost"


def test_explicit_uri_without_attr():
    t = resolve_target("/home/me/flake", "nixos")
    assert t.attr is None
    assert t.flake_ref == "/home/me/flake"


def test_invalid_mode():
    with pytest.raises(TargetError, match="mode"):
        resolve_target(None, "darwin")


def test_default_nixos_dir(monkeypatch, tmp_path):
    (tmp_path / "flake.nix").write_text("{}")
    monkeypatch.delenv("NIX_AGENT_FLAKE", raising=False)
    monkeypatch.setattr(target_mod, "NIXOS_DEFAULT_DIR", tmp_path)
    t = resolve_target(None, "nixos")
    assert t.flake_dir == str(tmp_path)
    assert t.attr is None


def test_default_dir_missing_flake(monkeypatch, tmp_path):
    monkeypatch.delenv("NIX_AGENT_FLAKE", raising=False)
    monkeypatch.setattr(target_mod, "NIXOS_DEFAULT_DIR", tmp_path / "nope")
    monkeypatch.setattr(Path, "home", lambda: tmp_path / "empty-home")
    with pytest.raises(TargetError, match="no flake.nix found"):
        resolve_target(None, "nixos")


def test_home_fallback_dir(monkeypatch, tmp_path):
    monkeypatch.delenv("NIX_AGENT_FLAKE", raising=False)
    monkeypatch.setattr(target_mod, "NIXOS_DEFAULT_DIR", tmp_path / "nope")
    home_nixos = tmp_path / "nixos"
    home_nixos.mkdir()
    (home_nixos / "flake.nix").write_text("{}")
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    t = resolve_target(None, "nixos")
    assert t.flake_dir == str(home_nixos)
    assert t.attr is None


def test_env_override(monkeypatch):
    monkeypatch.setenv("NIX_AGENT_FLAKE", "/home/me/nixos#laptop")
    t = resolve_target(None, "nixos")
    assert t.flake_dir == "/home/me/nixos"
    assert t.attr == "laptop"


def test_explicit_uri_beats_env(monkeypatch):
    monkeypatch.setenv("NIX_AGENT_FLAKE", "/env/flake#env")
    t = resolve_target("/explicit#host", "nixos")
    assert t.flake_dir == "/explicit"
    assert t.attr == "host"


def test_hm_env_override_specific(monkeypatch):
    monkeypatch.setenv("NIX_AGENT_FLAKE", "/sys#host")
    monkeypatch.setenv("NIX_AGENT_HM_FLAKE", "/hm#user")
    t = resolve_target(None, "home-manager")
    assert t.flake_dir == "/hm"
    assert t.attr == "user"


def test_default_hm_dir(monkeypatch, tmp_path):
    monkeypatch.delenv("NIX_AGENT_FLAKE", raising=False)
    monkeypatch.delenv("NIX_AGENT_HM_FLAKE", raising=False)
    hm_dir = tmp_path / ".config" / "home-manager"
    hm_dir.mkdir(parents=True)
    (hm_dir / "flake.nix").write_text("{}")
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    t = resolve_target(None, "home-manager")
    assert t.flake_dir == str(hm_dir)


def test_attr_candidates_nixos(monkeypatch):
    monkeypatch.setattr(target_mod.socket, "gethostname", lambda: "zen")
    t = Target(flake_dir="/etc/nixos", attr=None, mode="nixos")
    assert attr_candidates(t) == ["zen"]


def test_attr_candidates_hm_fallback(monkeypatch):
    monkeypatch.setattr(target_mod.socket, "gethostname", lambda: "zen")
    monkeypatch.setenv("USER", "rupan")
    t = Target(flake_dir="/x", attr=None, mode="home-manager")
    assert attr_candidates(t) == ["rupan@zen", "rupan"]


def test_attr_candidates_explicit_attr_wins():
    t = Target(flake_dir="/x", attr="other", mode="home-manager")
    assert attr_candidates(t) == ["other"]


def test_config_attr_quoting():
    t = Target(flake_dir="/x", attr=None, mode="home-manager")
    assert config_attr(t, "rupan@zen") == '/x#homeConfigurations."rupan@zen"'
    t2 = Target(flake_dir="/etc/nixos", attr=None, mode="nixos")
    assert config_attr(t2, "zen") == '/etc/nixos#nixosConfigurations."zen"'


def test_is_remote_flake_ref():
    assert is_remote_flake_ref("github:example/nixos")
    assert is_remote_flake_ref("gitlab:foo/bar")
    assert is_remote_flake_ref("sourcehut:~user/repo")
    assert is_remote_flake_ref("git+https://example.com/nixos.git")
    assert is_remote_flake_ref("http://example.com/nixos")
    assert is_remote_flake_ref("https://example.com/nixos")
    assert is_remote_flake_ref("ssh://git@example.com/nixos")
    assert is_remote_flake_ref("flake:nixpkgs")
    assert not is_remote_flake_ref("/home/me/nixos")
    assert not is_remote_flake_ref("~/nixos")
    assert not is_remote_flake_ref(".")


def _early_exit(out):
    assert out is not None
    assert "command" not in out
    assert "output" not in out
    assert "raw_bytes" not in out
    assert "returned_bytes" not in out
    return out


def test_constrain_remote_rejected(monkeypatch):
    monkeypatch.delenv("NIX_AGENT_ALLOW_REMOTE", raising=False)
    t = Target(flake_dir="github:example/nixos", attr="host", mode="nixos")
    out = _early_exit(constrain_privileged_target(t, mode="nixos"))
    assert out["status"] == "remote_ref_rejected"
    assert "NIX_AGENT_ALLOW_REMOTE" not in str(out)


def test_constrain_pin_lock(monkeypatch, tmp_path):
    pin = tmp_path / "nixos"
    pin.mkdir()
    (pin / "flake.nix").write_text("{ }\n")
    monkeypatch.setenv("NIX_AGENT_FLAKE", f"{pin}#laptop")
    t = Target(flake_dir="/tmp/other", attr="host", mode="nixos")
    out = _early_exit(constrain_privileged_target(t, mode="nixos"))
    assert out["status"] == "target_locked"
    assert out["pin"] == f"{pin}#laptop"


def test_constrain_same_dir_different_attr(monkeypatch, tmp_path):
    pin = tmp_path / "nixos"
    pin.mkdir()
    (pin / "flake.nix").write_text("{ }\n")
    monkeypatch.setenv("NIX_AGENT_FLAKE", f"{pin}#laptop")
    t = Target(flake_dir=str(pin), attr="other", mode="nixos")
    assert constrain_privileged_target(t, mode="nixos") is None


def test_constrain_realpath_and_trailing_slash(monkeypatch, tmp_path):
    pin = tmp_path / "nixos"
    pin.mkdir()
    (pin / "flake.nix").write_text("{ }\n")
    monkeypatch.setenv("NIX_AGENT_FLAKE", f"{pin}/")
    t = Target(
        flake_dir=str(tmp_path / "other" / ".." / "nixos"),
        attr="h",
        mode="nixos",
    )
    assert constrain_privileged_target(t, mode="nixos") is None


def test_constrain_nixos_pin_does_not_lock_hm(monkeypatch, tmp_path):
    nixos = tmp_path / "nixos"
    nixos.mkdir()
    (nixos / "flake.nix").write_text("{ }\n")
    hm = tmp_path / "home-manager"
    hm.mkdir()
    (hm / "flake.nix").write_text("{ }\n")
    monkeypatch.setenv("NIX_AGENT_FLAKE", f"{nixos}#laptop")
    monkeypatch.delenv("NIX_AGENT_HM_FLAKE", raising=False)
    t = Target(flake_dir=str(hm), attr="me", mode="home-manager")
    assert constrain_privileged_target(t, mode="home-manager") is None


def test_constrain_hm_pin_locks_hm(monkeypatch, tmp_path):
    hm = tmp_path / "home-manager"
    hm.mkdir()
    (hm / "flake.nix").write_text("{ }\n")
    other = tmp_path / "other"
    other.mkdir()
    (other / "flake.nix").write_text("{ }\n")
    monkeypatch.setenv("NIX_AGENT_HM_FLAKE", str(hm))
    t = Target(flake_dir=str(other), attr="me", mode="home-manager")
    out = _early_exit(constrain_privileged_target(t, mode="home-manager"))
    assert out["status"] == "target_locked"
    assert out["pin"] == str(hm)


def test_constrain_allow_remote(monkeypatch):
    monkeypatch.setenv("NIX_AGENT_ALLOW_REMOTE", "1")
    monkeypatch.delenv("NIX_AGENT_FLAKE", raising=False)
    t = Target(flake_dir="github:example/nixos", attr="host", mode="nixos")
    assert constrain_privileged_target(t, mode="nixos") is None


def test_constrain_allow_remote_truthy_yes(monkeypatch):
    monkeypatch.setenv("NIX_AGENT_ALLOW_REMOTE", "YES")
    monkeypatch.delenv("NIX_AGENT_FLAKE", raising=False)
    t = Target(flake_dir="github:example/nixos", attr="host", mode="nixos")
    assert constrain_privileged_target(t, mode="nixos") is None


def test_constrain_allow_remote_still_pin_locked(monkeypatch, tmp_path):
    pin = tmp_path / "nixos"
    pin.mkdir()
    (pin / "flake.nix").write_text("{ }\n")
    monkeypatch.setenv("NIX_AGENT_ALLOW_REMOTE", "1")
    monkeypatch.setenv("NIX_AGENT_FLAKE", str(pin))
    t = Target(flake_dir="github:example/nixos", attr="host", mode="nixos")
    out = _early_exit(constrain_privileged_target(t, mode="nixos"))
    assert out["status"] == "target_locked"


def test_constrain_relative_rejected(monkeypatch):
    monkeypatch.delenv("NIX_AGENT_FLAKE", raising=False)
    t = Target(flake_dir=".", attr=None, mode="nixos")
    out = _early_exit(constrain_privileged_target(t, mode="nixos"))
    assert out["status"] == "no_target"


def test_constrain_tilde_expands(monkeypatch, tmp_path):
    nixos = tmp_path / "nixos"
    nixos.mkdir()
    (nixos / "flake.nix").write_text("{ }\n")
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("NIX_AGENT_FLAKE", raising=False)
    t = Target(flake_dir="~/nixos", attr=None, mode="nixos")
    assert constrain_privileged_target(t, mode="nixos") is None


def test_hm_resolution_still_falls_back_to_nixos_pin(monkeypatch):
    monkeypatch.setenv("NIX_AGENT_FLAKE", "/sys#host")
    monkeypatch.delenv("NIX_AGENT_HM_FLAKE", raising=False)
    t = resolve_target(None, "home-manager")
    assert t.flake_dir == "/sys"
    assert t.attr == "host"
