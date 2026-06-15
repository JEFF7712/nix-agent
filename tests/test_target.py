from pathlib import Path

import pytest

from nix_agent import target as target_mod
from nix_agent.target import (
    Target,
    TargetError,
    attr_candidates,
    config_attr,
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
    assert (
        config_attr(t, "rupan@zen")
        == '/x#homeConfigurations."rupan@zen"'
    )
    t2 = Target(flake_dir="/etc/nixos", attr=None, mode="nixos")
    assert config_attr(t2, "zen") == '/etc/nixos#nixosConfigurations."zen"'
