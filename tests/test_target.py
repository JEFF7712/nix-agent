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
    monkeypatch.setattr(target_mod, "NIXOS_DEFAULT_DIR", tmp_path)
    t = resolve_target(None, "nixos")
    assert t.flake_dir == str(tmp_path)
    assert t.attr is None


def test_default_dir_missing_flake(monkeypatch, tmp_path):
    monkeypatch.setattr(target_mod, "NIXOS_DEFAULT_DIR", tmp_path / "nope")
    with pytest.raises(TargetError, match="flake_uri"):
        resolve_target(None, "nixos")


def test_default_hm_dir(monkeypatch, tmp_path):
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
