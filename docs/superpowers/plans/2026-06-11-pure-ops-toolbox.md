# nix-agent v0.5.0 Pure Ops Toolbox Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the two-tool patch pipeline with seven composable Nix operation tools (`eval_config`, `check`, `format`, `build`, `diff`, `switch`, `generations`) that enhance a capable host agent instead of wrapping its file I/O.

**Architecture:** A shared subprocess runner (`runner.py`) and target resolver (`target.py`) underpin one module per tool family in `src/nix_agent/tools/`. Each tool is a plain function returning a uniform response dict; `server.py` only registers them with FastMCP. File I/O tools and the patch pipeline are deleted outright (breaking, v0.5.0).

**Tech Stack:** Python 3.11+, FastMCP, pytest (subprocess mocked via monkeypatch), Nix flake packaging wrapping statix/deadnix/nixfmt/nvd onto PATH.

**Spec:** `docs/superpowers/specs/2026-06-11-pure-ops-toolbox-design.md`

**Conventions for all tasks:**
- Run tests with `pytest tests/<file> -v` from the repo root (pyproject sets `pythonpath = ["src"]`).
- Commit style follows the repo: `feat:`, `refactor!:`, `docs:`, `test:`, `chore:`. No emojis.
- Tests mock subprocess by monkeypatching `nix_agent.runner.run` (or `subprocess.run` for runner's own tests) — no real nix commands in unit tests.

---

### Task 1: `runner.py` — subprocess wrapper with truncation and first_error

**Files:**
- Create: `src/nix_agent/runner.py`
- Test: `tests/test_runner.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_runner.py
import subprocess

from nix_agent import runner


def test_run_success_combines_streams(monkeypatch):
    def fake_run(argv, capture_output, text, cwd=None):
        return subprocess.CompletedProcess(argv, 0, stdout="out\n", stderr="warn\n")

    monkeypatch.setattr(runner.subprocess, "run", fake_run)
    result = runner.run(["true"])
    assert result.ok
    assert result.stdout == "out\n"
    assert result.output == "out\nwarn"
    assert result.command == ["true"]


def test_run_failure(monkeypatch):
    def fake_run(argv, capture_output, text, cwd=None):
        return subprocess.CompletedProcess(argv, 1, stdout="", stderr="error: boom\n")

    monkeypatch.setattr(runner.subprocess, "run", fake_run)
    result = runner.run(["false"])
    assert not result.ok
    assert "error: boom" in result.output


def test_run_missing_binary(monkeypatch):
    def fake_run(argv, capture_output, text, cwd=None):
        raise FileNotFoundError(argv[0])

    monkeypatch.setattr(runner.subprocess, "run", fake_run)
    result = runner.run(["nvd", "diff"])
    assert not result.ok
    assert "nvd: command not found" in result.output


def test_truncate_output_keeps_head_and_tail():
    text = "a" * 50_000 + "MIDDLE" + "b" * 50_000
    out = runner.truncate_output(text, cap=10_000)
    assert len(out) < 11_000
    assert out.startswith("a")
    assert out.endswith("b")
    assert "truncated" in out
    assert "MIDDLE" not in out


def test_truncate_output_noop_under_cap():
    assert runner.truncate_output("short") == "short"


def test_extract_first_error():
    output = "building...\nerror: attribute 'foo' missing\nerror: second"
    assert runner.extract_first_error(output) == "error: attribute 'foo' missing"
    assert runner.extract_first_error("all fine") is None
    assert runner.extract_first_error("") is None


def test_envelope_failure_includes_first_error():
    result = runner.RunResult(
        ok=False, command=["nix", "eval"], stdout="", stderr="error: nope"
    )
    env = runner.envelope("failed", "/etc/nixos#host", result, extra_field=1)
    assert env["status"] == "failed"
    assert env["resolved_target"] == "/etc/nixos#host"
    assert env["command"] == ["nix", "eval"]
    assert env["first_error"] == "error: nope"
    assert env["extra_field"] == 1


def test_envelope_ok_has_no_first_error():
    result = runner.RunResult(ok=True, command=["x"], stdout="fine", stderr="")
    env = runner.envelope("ok", "t", result)
    assert "first_error" not in env
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_runner.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'nix_agent.runner'`

- [ ] **Step 3: Implement `runner.py`**

```python
# src/nix_agent/runner.py
from dataclasses import dataclass
import os
import shutil
import subprocess

OUTPUT_CAP = 64_000


@dataclass(frozen=True)
class RunResult:
    ok: bool
    command: list[str]
    stdout: str
    stderr: str

    @property
    def output(self) -> str:
        parts = [p for p in (self.stdout.strip(), self.stderr.strip()) if p]
        return "\n".join(parts)


def resolve_binary(name: str) -> str | None:
    """Realpath of a binary on PATH, or None. Sudo NOPASSWD rules match
    the resolved store path, not the PATH name, so sudo'd commands must
    use this."""
    found = shutil.which(name)
    if found is None:
        return None
    return os.path.realpath(found)


def truncate_output(text: str, cap: int = OUTPUT_CAP) -> str:
    if len(text) <= cap:
        return text
    half = cap // 2
    omitted = len(text) - cap
    return (
        text[:half]
        + f"\n... [nix-agent: {omitted} bytes truncated] ...\n"
        + text[-half:]
    )


def run(argv: list[str], cwd: str | None = None) -> RunResult:
    try:
        proc = subprocess.run(argv, capture_output=True, text=True, cwd=cwd)
    except FileNotFoundError:
        return RunResult(
            ok=False,
            command=argv,
            stdout="",
            stderr=f"{argv[0]}: command not found",
        )
    return RunResult(
        ok=proc.returncode == 0,
        command=argv,
        stdout=truncate_output(proc.stdout or ""),
        stderr=truncate_output(proc.stderr or ""),
    )


def extract_first_error(output: str) -> str | None:
    """First line of Nix stderr that looks like an error; the actionable
    signal in an otherwise verbose log."""
    if not output:
        return None
    for line in output.splitlines():
        stripped = line.strip()
        if stripped.startswith("error:") or stripped.startswith("error ("):
            return stripped
    return None


def envelope(
    status: str,
    resolved_target: str,
    result: RunResult,
    **extra: object,
) -> dict[str, object]:
    response: dict[str, object] = {
        "status": status,
        "resolved_target": resolved_target,
        "command": result.command,
        "output": result.output,
    }
    if status == "failed":
        response["first_error"] = extract_first_error(result.output)
    response.update(extra)
    return response
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_runner.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add src/nix_agent/runner.py tests/test_runner.py
git commit -m "feat: add shared subprocess runner with truncation and first_error"
```

---

### Task 2: `target.py` — flake target resolution

**Files:**
- Create: `src/nix_agent/target.py`
- Test: `tests/test_target.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_target.py
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_target.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'nix_agent.target'`

- [ ] **Step 3: Implement `target.py`**

```python
# src/nix_agent/target.py
from dataclasses import dataclass
import os
import pwd
import socket
from pathlib import Path

VALID_MODES = ("nixos", "home-manager")
NIXOS_DEFAULT_DIR = Path("/etc/nixos")


class TargetError(Exception):
    pass


@dataclass(frozen=True)
class Target:
    flake_dir: str
    attr: str | None
    mode: str

    @property
    def flake_ref(self) -> str:
        """For nixos-rebuild/home-manager --flake: those tools pick the
        hostname/user attribute themselves when none is given."""
        if self.attr:
            return f"{self.flake_dir}#{self.attr}"
        return self.flake_dir


def current_user() -> str | None:
    user = os.environ.get("USER")
    if user:
        return user
    try:
        return pwd.getpwuid(os.getuid()).pw_name
    except KeyError:
        return None


def resolve_target(flake_uri: str | None, mode: str) -> Target:
    if mode not in VALID_MODES:
        raise TargetError(
            f"mode must be one of {list(VALID_MODES)}, got {mode!r}"
        )
    if flake_uri is not None:
        dir_part, _, attr = flake_uri.partition("#")
        return Target(flake_dir=dir_part, attr=attr or None, mode=mode)
    if mode == "nixos":
        default_dir = NIXOS_DEFAULT_DIR
    else:
        default_dir = Path.home() / ".config" / "home-manager"
    if not (default_dir / "flake.nix").is_file():
        raise TargetError(
            f"no flake_uri given and {default_dir}/flake.nix does not exist; "
            "pass flake_uri explicitly"
        )
    return Target(flake_dir=str(default_dir), attr=None, mode=mode)


def attr_candidates(target: Target) -> list[str]:
    """Attribute names to try, in order, for nix eval / nix build
    installables (which, unlike nixos-rebuild, need an explicit attr)."""
    if target.attr:
        return [target.attr]
    host = socket.gethostname()
    if target.mode == "nixos":
        return [host]
    user = current_user()
    if not user:
        raise TargetError(
            "could not determine current user for home-manager attribute"
        )
    return [f"{user}@{host}", user]


def config_attr(target: Target, candidate: str) -> str:
    root = (
        "nixosConfigurations"
        if target.mode == "nixos"
        else "homeConfigurations"
    )
    return f'{target.flake_dir}#{root}."{candidate}"'
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_target.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add src/nix_agent/target.py tests/test_target.py
git commit -m "feat: add flake target auto-resolution with explicit override"
```

---

### Task 3: `tools/eval.py` — `eval_config`

**Files:**
- Create: `src/nix_agent/tools/__init__.py` (empty file)
- Create: `src/nix_agent/tools/eval.py`
- Test: `tests/test_eval_config.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_eval_config.py
from nix_agent.runner import RunResult
from nix_agent.tools import eval as eval_mod
from nix_agent.tools.eval import eval_config


def _result(ok, stdout="", stderr="", command=("nix",)):
    return RunResult(ok=ok, command=list(command), stdout=stdout, stderr=stderr)


def test_eval_ok_json(monkeypatch):
    calls = []

    def fake_run(argv, cwd=None):
        calls.append(argv)
        return _result(True, stdout="true\n", command=argv)

    monkeypatch.setattr(eval_mod.runner, "run", fake_run)
    out = eval_config(
        "services.openssh.enable", flake_uri="/etc/nixos#zen", mode="nixos"
    )
    assert out["status"] == "ok"
    assert out["value"] is True
    assert calls[0] == [
        "nix",
        "eval",
        '/etc/nixos#nixosConfigurations."zen".config.services.openssh.enable',
        "--json",
    ]


def test_eval_hm_candidate_fallback(monkeypatch):
    calls = []

    def fake_run(argv, cwd=None):
        calls.append(argv)
        if "rupan@zen" in argv[2]:
            return _result(
                False,
                stderr="error: flake does not provide attribute "
                "'homeConfigurations.\"rupan@zen\"'",
                command=argv,
            )
        return _result(True, stdout='"niri"\n', command=argv)

    monkeypatch.setattr(eval_mod.runner, "run", fake_run)
    monkeypatch.setattr(
        eval_mod, "attr_candidates", lambda t: ["rupan@zen", "rupan"]
    )
    out = eval_config(
        "wayland.windowManager", flake_uri="/x", mode="home-manager"
    )
    assert out["status"] == "ok"
    assert out["value"] == "niri"
    assert len(calls) == 2


def test_eval_non_json_fallback(monkeypatch):
    def fake_run(argv, cwd=None):
        if "--json" in argv:
            return _result(
                False,
                stderr="error: cannot convert a function to JSON",
                command=argv,
            )
        return _result(True, stdout="<LAMBDA>", command=argv)

    monkeypatch.setattr(eval_mod.runner, "run", fake_run)
    out = eval_config("lib.mkIf", flake_uri="/x#h", mode="nixos")
    assert out["status"] == "ok"
    assert out["value"] == "<LAMBDA>"
    assert out["json_fallback"] is True


def test_eval_real_failure(monkeypatch):
    def fake_run(argv, cwd=None):
        return _result(
            False, stderr="error: attribute 'nope' missing", command=argv
        )

    monkeypatch.setattr(eval_mod.runner, "run", fake_run)
    out = eval_config("services.nope", flake_uri="/x#h", mode="nixos")
    assert out["status"] == "failed"
    assert out["first_error"] == "error: attribute 'nope' missing"


def test_eval_no_target(monkeypatch, tmp_path):
    from nix_agent import target as target_mod

    monkeypatch.setattr(target_mod, "NIXOS_DEFAULT_DIR", tmp_path / "nope")
    out = eval_config("a.b", mode="nixos")
    assert out["status"] == "no_target"
    assert "flake_uri" in out["error"]


def test_eval_invalid_mode():
    out = eval_config("a.b", flake_uri="/x", mode="bogus")
    assert out["status"] == "no_target"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_eval_config.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'nix_agent.tools'`

- [ ] **Step 3: Implement `tools/eval.py`** (and create empty `src/nix_agent/tools/__init__.py`)

```python
# src/nix_agent/tools/eval.py
import json

from nix_agent import runner
from nix_agent.target import TargetError, attr_candidates, config_attr, resolve_target


def _missing_config_attr(output: str) -> bool:
    return "does not provide attribute" in output


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
            return runner.envelope(
                "ok", installable, result, value=json.loads(result.stdout)
            )
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_eval_config.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add src/nix_agent/tools/ tests/test_eval_config.py
git commit -m "feat: add eval_config tool for evaluating the live configuration"
```

---

### Task 4: `tools/build.py` — `build` and `diff`

**Files:**
- Create: `src/nix_agent/tools/build.py`
- Test: `tests/test_build_diff.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_build_diff.py
from nix_agent.runner import RunResult
from nix_agent.tools import build as build_mod
from nix_agent.tools.build import build, diff


def _result(ok, stdout="", stderr="", command=("nix",)):
    return RunResult(ok=ok, command=list(command), stdout=stdout, stderr=stderr)


def test_build_nixos_ok(monkeypatch):
    calls = []

    def fake_run(argv, cwd=None):
        calls.append(argv)
        return _result(True, stdout="/nix/store/abc-nixos-system\n", command=argv)

    monkeypatch.setattr(build_mod.runner, "run", fake_run)
    out = build(flake_uri="/etc/nixos#zen", mode="nixos")
    assert out["status"] == "ok"
    assert out["store_path"] == "/nix/store/abc-nixos-system"
    assert calls[0] == [
        "nix",
        "build",
        "--no-link",
        "--print-out-paths",
        '/etc/nixos#nixosConfigurations."zen".config.system.build.toplevel',
    ]


def test_build_hm_uses_activation_package(monkeypatch):
    calls = []

    def fake_run(argv, cwd=None):
        calls.append(argv)
        return _result(True, stdout="/nix/store/abc-hm\n", command=argv)

    monkeypatch.setattr(build_mod.runner, "run", fake_run)
    out = build(flake_uri="/x#rupan", mode="home-manager")
    assert out["status"] == "ok"
    assert ".activationPackage" in calls[0][-1]


def test_build_failure(monkeypatch):
    def fake_run(argv, cwd=None):
        return _result(False, stderr="error: syntax error", command=argv)

    monkeypatch.setattr(build_mod.runner, "run", fake_run)
    out = build(flake_uri="/x#h", mode="nixos")
    assert out["status"] == "failed"
    assert out["first_error"] == "error: syntax error"


def test_build_dry_run_flag(monkeypatch):
    calls = []

    def fake_run(argv, cwd=None):
        calls.append(argv)
        return _result(True, command=argv)

    monkeypatch.setattr(build_mod.runner, "run", fake_run)
    build(flake_uri="/x#h", mode="nixos", dry_run=True)
    assert "--dry-run" in calls[0]
    assert "--print-out-paths" not in calls[0]


def test_diff_runs_nvd(monkeypatch):
    calls = []

    def fake_run(argv, cwd=None):
        calls.append(argv)
        if argv[0] == "nix":
            return _result(True, stdout="/nix/store/new-system\n", command=argv)
        return _result(True, stdout="[U.]  firefox: 130 -> 131", command=argv)

    monkeypatch.setattr(build_mod.runner, "run", fake_run)
    monkeypatch.setattr(build_mod.runner, "resolve_binary", lambda n: f"/bin/{n}")
    monkeypatch.setattr(
        build_mod, "_current_closure", lambda mode: "/run/current-system"
    )
    out = diff(flake_uri="/etc/nixos#zen", mode="nixos")
    assert out["status"] == "ok"
    assert "firefox" in out["diff"]
    assert calls[-1] == ["/bin/nvd", "diff", "/run/current-system", "/nix/store/new-system"]


def test_diff_falls_back_to_diff_closures(monkeypatch):
    calls = []

    def fake_run(argv, cwd=None):
        calls.append(argv)
        if argv[0] == "nix" and argv[1] == "build":
            return _result(True, stdout="/nix/store/new\n", command=argv)
        return _result(True, stdout="diff output", command=argv)

    monkeypatch.setattr(build_mod.runner, "run", fake_run)
    monkeypatch.setattr(build_mod.runner, "resolve_binary", lambda n: None)
    monkeypatch.setattr(build_mod, "_current_closure", lambda mode: "/cur")
    out = diff(flake_uri="/x#h", mode="nixos")
    assert out["status"] == "ok"
    assert calls[-1] == ["nix", "store", "diff-closures", "/cur", "/nix/store/new"]


def test_diff_build_failure_propagates(monkeypatch):
    def fake_run(argv, cwd=None):
        return _result(False, stderr="error: bad", command=argv)

    monkeypatch.setattr(build_mod.runner, "run", fake_run)
    out = diff(flake_uri="/x#h", mode="nixos")
    assert out["status"] == "failed"


def test_diff_no_current_closure(monkeypatch):
    def fake_run(argv, cwd=None):
        return _result(True, stdout="/nix/store/new\n", command=argv)

    monkeypatch.setattr(build_mod.runner, "run", fake_run)
    monkeypatch.setattr(build_mod, "_current_closure", lambda mode: None)
    out = diff(flake_uri="/x#h", mode="home-manager")
    assert out["status"] == "failed"
    assert "current" in out["error"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_build_diff.py -v`
Expected: FAIL with `ImportError` (no `nix_agent.tools.build`)

- [ ] **Step 3: Implement `tools/build.py`**

Note: the spec sketched `home-manager build` + `./result` parsing for HM; this uses `nix build --no-link --print-out-paths` on `.activationPackage` instead — symmetric with NixOS, no symlink litter, same closure.

```python
# src/nix_agent/tools/build.py
import os
from pathlib import Path

from nix_agent import runner
from nix_agent.target import (
    Target,
    TargetError,
    attr_candidates,
    config_attr,
    current_user,
    resolve_target,
)


def closure_installable(target: Target, candidate: str) -> str:
    if target.mode == "nixos":
        return f"{config_attr(target, candidate)}.config.system.build.toplevel"
    return f"{config_attr(target, candidate)}.activationPackage"


def build_closure(target: Target, dry_run: bool = False) -> dict[str, object]:
    """Shared by build(), diff(), and check(level='dry-build')."""
    candidates = attr_candidates(target)
    installable = ""
    result = runner.RunResult(ok=False, command=[], stdout="", stderr="")
    for i, candidate in enumerate(candidates):
        installable = closure_installable(target, candidate)
        argv = ["nix", "build", "--no-link"]
        if dry_run:
            argv.append("--dry-run")
        else:
            argv.append("--print-out-paths")
        argv.append(installable)
        result = runner.run(argv)
        if result.ok:
            extra: dict[str, object] = {}
            if not dry_run:
                extra["store_path"] = result.stdout.strip().splitlines()[-1]
            return runner.envelope("ok", installable, result, **extra)
        if (
            "does not provide attribute" in result.output
            and i < len(candidates) - 1
        ):
            continue
        break
    return runner.envelope("failed", installable, result)


def build(
    flake_uri: str | None = None,
    mode: str = "nixos",
    dry_run: bool = False,
) -> dict[str, object]:
    try:
        target = resolve_target(flake_uri, mode)
    except TargetError as exc:
        return {"status": "no_target", "error": str(exc)}
    return build_closure(target, dry_run=dry_run)


def _current_closure(mode: str) -> str | None:
    if mode == "nixos":
        path = Path("/run/current-system")
        return os.path.realpath(path) if path.exists() else None
    user = current_user()
    candidates = []
    if user:
        candidates.append(
            Path(f"/nix/var/nix/profiles/per-user/{user}/home-manager")
        )
    candidates.append(
        Path.home() / ".local" / "state" / "nix" / "profiles" / "home-manager"
    )
    for path in candidates:
        if path.exists():
            return os.path.realpath(path)
    return None


def diff(
    flake_uri: str | None = None, mode: str = "nixos"
) -> dict[str, object]:
    """Build the new closure and diff it against the live system, so the
    agent can show what a switch would change before switching."""
    try:
        target = resolve_target(flake_uri, mode)
    except TargetError as exc:
        return {"status": "no_target", "error": str(exc)}

    built = build_closure(target)
    if built["status"] != "ok":
        return built
    new_path = str(built["store_path"])

    current = _current_closure(mode)
    if current is None:
        return {
            "status": "failed",
            "resolved_target": built["resolved_target"],
            "error": f"could not locate the current {mode} closure to diff against",
            "store_path": new_path,
        }

    nvd = runner.resolve_binary("nvd")
    if nvd:
        argv = [nvd, "diff", current, new_path]
    else:
        argv = ["nix", "store", "diff-closures", current, new_path]
    result = runner.run(argv)
    status = "ok" if result.ok else "failed"
    return runner.envelope(
        status,
        str(built["resolved_target"]),
        result,
        diff=result.output,
        store_path=new_path,
        current_closure=current,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_build_diff.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add src/nix_agent/tools/build.py tests/test_build_diff.py
git commit -m "feat: add build and diff tools (nvd with diff-closures fallback)"
```

---

### Task 5: `tools/check.py` — validation ladder

**Files:**
- Create: `src/nix_agent/tools/check.py`
- Test: `tests/test_check.py`

- [ ] **Step 1: Capture real linter JSON to validate the fixture shapes**

The statix/deadnix JSON schemas below are best-effort from documentation. Before writing the parsers, verify against the real tools on a throwaway file:

```bash
printf 'let x = 1; in { a = if true then true else false; }\n' > /tmp/lintme.nix
nix run nixpkgs#statix -- check -o json /tmp/lintme.nix
nix run nixpkgs#deadnix -- --output-format json /tmp/lintme.nix
```

If the emitted shapes differ from the fixtures in Step 2, update the fixtures *and* parsers to match reality. The tests must encode what the tools actually emit.

- [ ] **Step 2: Write the failing tests**

```python
# tests/test_check.py
import json

from nix_agent.runner import RunResult
from nix_agent.tools import check as check_mod
from nix_agent.tools.check import _parse_deadnix, _parse_statix, check

# Shapes verified against real tool output in Step 1; update if they differ.
STATIX_FIXTURE = json.dumps(
    [
        {
            "file": "/etc/nixos/configuration.nix",
            "report": [
                {
                    "note": "Useless if-then-else",
                    "code": 1,
                    "severity": "Warn",
                    "diagnostics": [
                        {
                            "at": {
                                "from": {"line": 4, "column": 9},
                                "to": {"line": 4, "column": 40},
                            },
                            "message": "This if-then-else is useless",
                        }
                    ],
                }
            ],
        }
    ]
)

DEADNIX_FIXTURE = (
    '{"file": "/etc/nixos/configuration.nix", "results": '
    '[{"column": 5, "endColumn": 6, "line": 1, "message": '
    '"Unused let binding: x"}]}'
)


def _result(ok, stdout="", stderr="", command=("x",)):
    return RunResult(ok=ok, command=list(command), stdout=stdout, stderr=stderr)


def test_parse_statix():
    findings = _parse_statix(STATIX_FIXTURE)
    assert findings == [
        {
            "tool": "statix",
            "file": "/etc/nixos/configuration.nix",
            "line": 4,
            "column": 9,
            "severity": "Warn",
            "message": "This if-then-else is useless",
        }
    ]


def test_parse_statix_empty_and_garbage():
    assert _parse_statix("") == []
    garbage = _parse_statix("not json at all")
    assert len(garbage) == 1
    assert garbage[0]["tool"] == "statix"
    assert "not json" in garbage[0]["message"]


def test_parse_deadnix():
    findings = _parse_deadnix(DEADNIX_FIXTURE)
    assert findings == [
        {
            "tool": "deadnix",
            "file": "/etc/nixos/configuration.nix",
            "line": 1,
            "column": 5,
            "severity": "warning",
            "message": "Unused let binding: x",
        }
    ]


def test_parse_deadnix_empty():
    assert _parse_deadnix("") == []


def test_check_invalid_level():
    out = check("vibes", flake_uri="/x")
    assert out["status"] == "invalid_level"
    assert "lint" in out["error"]


def test_check_lint_combines_tools(monkeypatch):
    def fake_run(argv, cwd=None):
        if argv[0].endswith("statix"):
            return _result(False, stdout=STATIX_FIXTURE, command=argv)
        return _result(False, stdout=DEADNIX_FIXTURE, command=argv)

    monkeypatch.setattr(check_mod.runner, "run", fake_run)
    monkeypatch.setattr(check_mod.runner, "resolve_binary", lambda n: f"/bin/{n}")
    out = check("lint", flake_uri="/etc/nixos#zen")
    assert out["status"] == "ok"
    assert len(out["findings"]) == 2
    tools = {f["tool"] for f in out["findings"]}
    assert tools == {"statix", "deadnix"}


def test_check_lint_missing_binaries(monkeypatch):
    monkeypatch.setattr(check_mod.runner, "resolve_binary", lambda n: None)
    out = check("lint", flake_uri="/x")
    assert out["status"] == "tool_missing"
    assert set(out["missing"]) == {"statix", "deadnix"}


def test_check_flake(monkeypatch):
    calls = []

    def fake_run(argv, cwd=None):
        calls.append(argv)
        return _result(True, command=argv)

    monkeypatch.setattr(check_mod.runner, "run", fake_run)
    out = check("flake", flake_uri="/etc/nixos#zen")
    assert out["status"] == "ok"
    assert calls[0] == ["nix", "flake", "check", "/etc/nixos"]


def test_check_dry_build_delegates_to_build_closure(monkeypatch):
    seen = {}

    def fake_build_closure(target, dry_run=False):
        seen["dry_run"] = dry_run
        return {"status": "ok", "resolved_target": "x", "command": [], "output": ""}

    monkeypatch.setattr(check_mod, "build_closure", fake_build_closure)
    out = check("dry-build", flake_uri="/x#h")
    assert out["status"] == "ok"
    assert seen["dry_run"] is True


def test_check_dry_activate_nixos(monkeypatch):
    calls = []

    def fake_run(argv, cwd=None):
        calls.append(argv)
        return _result(True, command=argv)

    monkeypatch.setattr(check_mod.runner, "run", fake_run)
    monkeypatch.setattr(
        check_mod.runner, "resolve_binary", lambda n: f"/bin/{n}"
    )
    out = check("dry-activate", flake_uri="/etc/nixos#zen")
    assert out["status"] == "ok"
    assert calls[0] == [
        "sudo", "/bin/nixos-rebuild", "dry-activate", "--flake", "/etc/nixos#zen",
    ]


def test_check_dry_activate_hm_not_applicable():
    out = check("dry-activate", flake_uri="/x", mode="home-manager")
    assert out["status"] == "not_applicable"
    assert "dry-build" in out["hint"]
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `pytest tests/test_check.py -v`
Expected: FAIL with `ImportError` (no `nix_agent.tools.check`)

- [ ] **Step 4: Implement `tools/check.py`**

Note: the spec sketched `nixos-rebuild dry-build` for level='dry-build'; this delegates to `build_closure(dry_run=True)` (`nix build --dry-run`) instead — identical semantics (evaluate + plan, build nothing), one code path shared with `build`/`diff`, and it works for Home Manager too.

```python
# src/nix_agent/tools/check.py
import json

from nix_agent import runner
from nix_agent.target import Target, TargetError, resolve_target
from nix_agent.tools.build import build_closure

LEVELS = ("lint", "flake", "dry-build", "dry-activate")


def _parse_statix(stdout: str) -> list[dict[str, object]]:
    if not stdout.strip():
        return []
    try:
        entries = json.loads(stdout)
    except json.JSONDecodeError:
        return [
            {
                "tool": "statix",
                "file": None,
                "line": None,
                "column": None,
                "severity": "unknown",
                "message": stdout.strip(),
            }
        ]
    if not isinstance(entries, list):
        entries = [entries]
    findings: list[dict[str, object]] = []
    for entry in entries:
        file = entry.get("file")
        for report in entry.get("report", []):
            note = report.get("note", "")
            severity = report.get("severity", "Warn")
            for diag in report.get("diagnostics", []):
                at = diag.get("at", {}).get("from", {})
                findings.append(
                    {
                        "tool": "statix",
                        "file": file,
                        "line": at.get("line"),
                        "column": at.get("column"),
                        "severity": severity,
                        "message": diag.get("message") or note,
                    }
                )
    return findings


def _parse_deadnix(stdout: str) -> list[dict[str, object]]:
    findings: list[dict[str, object]] = []
    for line in stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        for item in entry.get("results", []):
            findings.append(
                {
                    "tool": "deadnix",
                    "file": entry.get("file"),
                    "line": item.get("line"),
                    "column": item.get("column"),
                    "severity": "warning",
                    "message": item.get("message"),
                }
            )
    return findings


def _lint(target: Target) -> dict[str, object]:
    statix = runner.resolve_binary("statix")
    deadnix = runner.resolve_binary("deadnix")
    missing = [
        name
        for name, path in (("statix", statix), ("deadnix", deadnix))
        if path is None
    ]
    if missing:
        return {
            "status": "tool_missing",
            "resolved_target": target.flake_dir,
            "missing": missing,
            "error": f"lint tools not on PATH: {', '.join(missing)}",
        }

    findings: list[dict[str, object]] = []
    commands: list[list[str]] = []
    outputs: list[str] = []

    statix_result = runner.run([statix, "check", "-o", "json", target.flake_dir])
    commands.append(statix_result.command)
    outputs.append(statix_result.output)
    findings.extend(_parse_statix(statix_result.stdout))

    deadnix_result = runner.run(
        [deadnix, "--output-format", "json", target.flake_dir]
    )
    commands.append(deadnix_result.command)
    outputs.append(deadnix_result.output)
    findings.extend(_parse_deadnix(deadnix_result.stdout))

    return {
        "status": "ok",
        "resolved_target": target.flake_dir,
        "command": commands,
        "output": "\n".join(o for o in outputs if o),
        "findings": findings,
        "finding_count": len(findings),
    }


def check(
    level: str,
    flake_uri: str | None = None,
    mode: str = "nixos",
) -> dict[str, object]:
    """Validation ladder, fast to slow: lint -> flake -> dry-build ->
    dry-activate. Linters exiting non-zero just means findings exist;
    status stays 'ok' with structured findings attached."""
    if level not in LEVELS:
        return {
            "status": "invalid_level",
            "error": f"level must be one of {list(LEVELS)}, got {level!r}",
        }
    try:
        target = resolve_target(flake_uri, mode)
    except TargetError as exc:
        return {"status": "no_target", "error": str(exc)}

    if level == "lint":
        return _lint(target)

    if level == "flake":
        result = runner.run(["nix", "flake", "check", target.flake_dir])
        return runner.envelope(
            "ok" if result.ok else "failed", target.flake_dir, result
        )

    if level == "dry-build":
        return build_closure(target, dry_run=True)

    # dry-activate
    if target.mode == "home-manager":
        return {
            "status": "not_applicable",
            "resolved_target": target.flake_ref,
            "hint": "home-manager has no dry-activate; use level='dry-build'",
        }
    nixos_rebuild = runner.resolve_binary("nixos-rebuild") or "nixos-rebuild"
    result = runner.run(
        ["sudo", nixos_rebuild, "dry-activate", "--flake", target.flake_ref]
    )
    return runner.envelope(
        "ok" if result.ok else "failed", target.flake_ref, result
    )
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_check.py -v`
Expected: all PASS

- [ ] **Step 6: Commit**

```bash
git add src/nix_agent/tools/check.py tests/test_check.py
git commit -m "feat: add check tool with lint/flake/dry-build/dry-activate ladder"
```

---

### Task 6: `tools/fmt.py` — `format`

**Files:**
- Create: `src/nix_agent/tools/fmt.py`
- Test: `tests/test_format.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_format.py
from nix_agent.runner import RunResult
from nix_agent.tools import fmt as fmt_mod
from nix_agent.tools.fmt import format_nix


def _result(ok, stdout="", stderr="", command=("x",)):
    return RunResult(ok=ok, command=list(command), stdout=stdout, stderr=stderr)


def test_format_explicit_paths(monkeypatch):
    calls = []

    def fake_run(argv, cwd=None):
        calls.append(argv)
        return _result(True, command=argv)

    monkeypatch.setattr(fmt_mod.runner, "run", fake_run)
    monkeypatch.setattr(fmt_mod.runner, "resolve_binary", lambda n: "/bin/nixfmt")
    out = format_nix(paths=["/etc/nixos/a.nix", "/etc/nixos/b.txt"])
    assert out["status"] == "ok"
    assert out["formatter"] == "nixfmt"
    assert calls[0] == ["/bin/nixfmt", "/etc/nixos/a.nix"]
    assert out["skipped"] == ["/etc/nixos/b.txt"]


def test_format_explicit_paths_nixfmt_missing(monkeypatch):
    monkeypatch.setattr(fmt_mod.runner, "resolve_binary", lambda n: None)
    out = format_nix(paths=["/x/a.nix"])
    assert out["status"] == "tool_missing"
    assert out["missing"] == ["nixfmt"]


def test_format_whole_flake_uses_nix_fmt(monkeypatch, tmp_path):
    (tmp_path / "flake.nix").write_text("{}")
    calls = []

    def fake_run(argv, cwd=None):
        calls.append((argv, cwd))
        return _result(True, command=argv)

    monkeypatch.setattr(fmt_mod.runner, "run", fake_run)
    out = format_nix(flake_uri=str(tmp_path))
    assert out["status"] == "ok"
    assert out["formatter"] == "nix fmt"
    assert calls[0] == (["nix", "fmt"], str(tmp_path))


def test_format_falls_back_to_nixfmt_when_no_flake_formatter(
    monkeypatch, tmp_path
):
    (tmp_path / "flake.nix").write_text("{}")
    (tmp_path / "module.nix").write_text("{}")
    calls = []

    def fake_run(argv, cwd=None):
        calls.append(argv)
        if argv[:2] == ["nix", "fmt"]:
            return _result(
                False,
                stderr="error: flake does not provide attribute 'formatter'",
                command=argv,
            )
        return _result(True, command=argv)

    monkeypatch.setattr(fmt_mod.runner, "run", fake_run)
    monkeypatch.setattr(fmt_mod.runner, "resolve_binary", lambda n: "/bin/nixfmt")
    out = format_nix(flake_uri=str(tmp_path))
    assert out["status"] == "ok"
    assert out["formatter"] == "nixfmt"
    formatted = calls[-1]
    assert formatted[0] == "/bin/nixfmt"
    assert str(tmp_path / "flake.nix") in formatted
    assert str(tmp_path / "module.nix") in formatted


def test_format_no_target(monkeypatch, tmp_path):
    from nix_agent import target as target_mod

    monkeypatch.setattr(target_mod, "NIXOS_DEFAULT_DIR", tmp_path / "nope")
    out = format_nix()
    assert out["status"] == "no_target"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_format.py -v`
Expected: FAIL with `ImportError` (no `nix_agent.tools.fmt`)

- [ ] **Step 3: Implement `tools/fmt.py`**

Note: spec signature is `format(paths=None, flake_uri=None)`; a `mode` param is added solely so default-directory resolution works when both are omitted.

```python
# src/nix_agent/tools/fmt.py
from pathlib import Path

from nix_agent import runner
from nix_agent.target import TargetError, resolve_target


def _format_with_nixfmt(paths: list[str]) -> dict[str, object]:
    nixfmt = runner.resolve_binary("nixfmt")
    if nixfmt is None:
        return {
            "status": "tool_missing",
            "missing": ["nixfmt"],
            "error": "nixfmt not on PATH",
        }
    nix_paths = [p for p in paths if p.endswith(".nix")]
    skipped = [p for p in paths if not p.endswith(".nix")]
    results = []
    ok = True
    for path in nix_paths:
        result = runner.run([nixfmt, path])
        ok = ok and result.ok
        results.append(
            {"path": path, "ok": result.ok, "output": result.output}
        )
    return {
        "status": "ok" if ok else "failed",
        "formatter": "nixfmt",
        "results": results,
        "skipped": skipped,
    }


def format_nix(
    paths: list[str] | None = None,
    flake_uri: str | None = None,
    mode: str = "nixos",
) -> dict[str, object]:
    """Format .nix files. Explicit paths -> nixfmt per file. Whole flake
    -> `nix fmt` (respects the flake's own formatter), falling back to
    nixfmt over every .nix file when the flake defines no formatter."""
    if paths:
        response = _format_with_nixfmt(paths)
        response.setdefault("resolved_target", paths)
        return response

    try:
        target = resolve_target(flake_uri, mode)
    except TargetError as exc:
        return {"status": "no_target", "error": str(exc)}

    result = runner.run(["nix", "fmt"], cwd=target.flake_dir)
    if result.ok:
        return runner.envelope(
            "ok", target.flake_dir, result, formatter="nix fmt"
        )
    if "formatter" not in result.output:
        return runner.envelope(
            "failed", target.flake_dir, result, formatter="nix fmt"
        )

    all_nix = sorted(
        str(p) for p in Path(target.flake_dir).rglob("*.nix")
    )
    response = _format_with_nixfmt(all_nix)
    response["resolved_target"] = target.flake_dir
    return response
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_format.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add src/nix_agent/tools/fmt.py tests/test_format.py
git commit -m "feat: add format tool preferring the flake's own nix fmt"
```

---

### Task 7: `tools/switch.py` — `switch` and `generations`

**Files:**
- Create: `src/nix_agent/tools/switch.py`
- Test: `tests/test_switch_generations.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_switch_generations.py
from nix_agent.runner import RunResult
from nix_agent.tools import switch as switch_mod
from nix_agent.tools.switch import generations, switch


def _result(ok, stdout="", stderr="", command=("x",)):
    return RunResult(ok=ok, command=list(command), stdout=stdout, stderr=stderr)


NIX_ENV_LISTING = """\
  41   2026-06-01 10:00:00
  42   2026-06-10 09:30:00   (current)
"""

HM_LISTING = """\
2026-06-10 09:31 : id 88 -> /nix/store/new-hm-gen
2026-06-01 10:01 : id 87 -> /nix/store/old-hm-gen
"""


def test_switch_nixos(monkeypatch):
    calls = []
    gens = iter(["/nix/var/.../system-42-link", "/nix/var/.../system-43-link"])

    def fake_run(argv, cwd=None):
        calls.append(argv)
        return _result(True, command=argv)

    monkeypatch.setattr(switch_mod.runner, "run", fake_run)
    monkeypatch.setattr(
        switch_mod.runner, "resolve_binary", lambda n: f"/bin/{n}"
    )
    monkeypatch.setattr(
        switch_mod, "_current_generation", lambda mode: next(gens)
    )
    out = switch(flake_uri="/etc/nixos#zen")
    assert out["status"] == "ok"
    assert out["rollback_generation"] == "/nix/var/.../system-42-link"
    assert out["current_generation"] == "/nix/var/.../system-43-link"
    assert calls[0] == [
        "sudo", "/bin/nixos-rebuild", "switch", "--flake", "/etc/nixos#zen",
    ]


def test_switch_hm_no_sudo(monkeypatch):
    calls = []

    def fake_run(argv, cwd=None):
        calls.append(argv)
        return _result(True, command=argv)

    monkeypatch.setattr(switch_mod.runner, "run", fake_run)
    monkeypatch.setattr(switch_mod, "_current_generation", lambda mode: None)
    out = switch(flake_uri="/x#rupan", mode="home-manager")
    assert out["status"] == "ok"
    assert calls[0] == ["home-manager", "switch", "--flake", "/x#rupan"]


def test_switch_failure_keeps_rollback(monkeypatch):
    def fake_run(argv, cwd=None):
        return _result(False, stderr="error: activation failed", command=argv)

    monkeypatch.setattr(switch_mod.runner, "run", fake_run)
    monkeypatch.setattr(
        switch_mod.runner, "resolve_binary", lambda n: f"/bin/{n}"
    )
    monkeypatch.setattr(switch_mod, "_current_generation", lambda mode: "gen-42")
    out = switch(flake_uri="/x#h")
    assert out["status"] == "failed"
    assert out["rollback_generation"] == "gen-42"
    assert out["first_error"] == "error: activation failed"


def test_generations_list_nixos(monkeypatch):
    def fake_run(argv, cwd=None):
        assert argv == [
            "nix-env", "--list-generations", "-p", "/nix/var/nix/profiles/system",
        ]
        return _result(True, stdout=NIX_ENV_LISTING, command=argv)

    monkeypatch.setattr(switch_mod.runner, "run", fake_run)
    out = generations()
    assert out["status"] == "ok"
    assert out["generations"] == [
        {"id": 41, "date": "2026-06-01 10:00:00", "current": False},
        {"id": 42, "date": "2026-06-10 09:30:00", "current": True},
    ]


def test_generations_list_hm(monkeypatch):
    def fake_run(argv, cwd=None):
        return _result(True, stdout=HM_LISTING, command=argv)

    monkeypatch.setattr(switch_mod.runner, "run", fake_run)
    out = generations(mode="home-manager")
    assert out["status"] == "ok"
    assert out["generations"] == [
        {
            "id": 88,
            "date": "2026-06-10 09:31",
            "path": "/nix/store/new-hm-gen",
            "current": True,
        },
        {
            "id": 87,
            "date": "2026-06-01 10:01",
            "path": "/nix/store/old-hm-gen",
            "current": False,
        },
    ]


def test_generations_rollback_nixos(monkeypatch):
    calls = []

    def fake_run(argv, cwd=None):
        calls.append(argv)
        return _result(True, command=argv)

    monkeypatch.setattr(switch_mod.runner, "run", fake_run)
    monkeypatch.setattr(
        switch_mod.runner, "resolve_binary", lambda n: f"/bin/{n}"
    )
    monkeypatch.setattr(switch_mod, "_current_generation", lambda mode: "gen")
    out = generations(action="rollback")
    assert out["status"] == "ok"
    assert calls[0] == ["sudo", "/bin/nixos-rebuild", "switch", "--rollback"]


def test_generations_rollback_hm_activates_previous(monkeypatch):
    calls = []

    def fake_run(argv, cwd=None):
        calls.append(argv)
        if argv[0] == "home-manager":
            return _result(True, stdout=HM_LISTING, command=argv)
        return _result(True, command=argv)

    monkeypatch.setattr(switch_mod.runner, "run", fake_run)
    out = generations(action="rollback", mode="home-manager")
    assert out["status"] == "ok"
    assert calls[-1] == ["/nix/store/old-hm-gen/activate"]


def test_generations_rollback_hm_no_previous(monkeypatch):
    single = "2026-06-10 09:31 : id 88 -> /nix/store/only-gen\n"

    def fake_run(argv, cwd=None):
        return _result(True, stdout=single, command=argv)

    monkeypatch.setattr(switch_mod.runner, "run", fake_run)
    out = generations(action="rollback", mode="home-manager")
    assert out["status"] == "failed"
    assert "previous" in out["error"]


def test_generations_invalid_action():
    out = generations(action="explode")
    assert out["status"] == "invalid_action"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_switch_generations.py -v`
Expected: FAIL with `ImportError` (no `nix_agent.tools.switch`)

- [ ] **Step 3: Implement `tools/switch.py`**

```python
# src/nix_agent/tools/switch.py
import os
import re
from pathlib import Path

from nix_agent import runner
from nix_agent.target import TargetError, current_user, resolve_target

SYSTEM_PROFILE = "/nix/var/nix/profiles/system"

_NIX_ENV_LINE = re.compile(
    r"^\s*(\d+)\s+(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\s*(\(current\))?\s*$"
)
_HM_LINE = re.compile(
    r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}) : id (\d+) -> (\S+)$"
)


def _current_generation(mode: str) -> str | None:
    if mode == "nixos":
        path = Path(SYSTEM_PROFILE)
        return os.path.realpath(path) if path.exists() else None
    user = current_user()
    candidates = []
    if user:
        candidates.append(
            Path(f"/nix/var/nix/profiles/per-user/{user}/home-manager")
        )
    candidates.append(
        Path.home() / ".local" / "state" / "nix" / "profiles" / "home-manager"
    )
    for path in candidates:
        if path.exists():
            return os.path.realpath(path)
    return None


def switch(
    flake_uri: str | None = None, mode: str = "nixos"
) -> dict[str, object]:
    """Switch with no implicit validation gate; the agent composes
    check -> diff -> switch itself. rollback_generation is always
    recorded first so a bad switch can be undone."""
    try:
        target = resolve_target(flake_uri, mode)
    except TargetError as exc:
        return {"status": "no_target", "error": str(exc)}

    rollback = _current_generation(mode)
    if mode == "nixos":
        nixos_rebuild = runner.resolve_binary("nixos-rebuild") or "nixos-rebuild"
        argv = ["sudo", nixos_rebuild, "switch", "--flake", target.flake_ref]
    else:
        argv = ["home-manager", "switch", "--flake", target.flake_ref]
    result = runner.run(argv)
    return runner.envelope(
        "ok" if result.ok else "failed",
        target.flake_ref,
        result,
        rollback_generation=rollback,
        current_generation=_current_generation(mode),
    )


def _list_nixos() -> dict[str, object]:
    result = runner.run(
        ["nix-env", "--list-generations", "-p", SYSTEM_PROFILE]
    )
    if not result.ok:
        return runner.envelope("failed", SYSTEM_PROFILE, result)
    gens = []
    for line in result.stdout.splitlines():
        match = _NIX_ENV_LINE.match(line)
        if match:
            gens.append(
                {
                    "id": int(match.group(1)),
                    "date": match.group(2),
                    "current": match.group(3) is not None,
                }
            )
    return runner.envelope("ok", SYSTEM_PROFILE, result, generations=gens)


def _list_hm() -> tuple[dict[str, object], list[dict[str, object]]]:
    result = runner.run(["home-manager", "generations"])
    if not result.ok:
        return runner.envelope("failed", "home-manager profile", result), []
    gens = []
    for i, line in enumerate(result.stdout.splitlines()):
        match = _HM_LINE.match(line.strip())
        if match:
            gens.append(
                {
                    "id": int(match.group(2)),
                    "date": match.group(1),
                    "path": match.group(3),
                    "current": i == 0,
                }
            )
    envelope = runner.envelope(
        "ok", "home-manager profile", result, generations=gens
    )
    return envelope, gens


def generations(
    action: str = "list", mode: str = "nixos"
) -> dict[str, object]:
    if action not in ("list", "rollback"):
        return {
            "status": "invalid_action",
            "error": f"action must be 'list' or 'rollback', got {action!r}",
        }
    if mode not in ("nixos", "home-manager"):
        return {
            "status": "no_target",
            "error": f"mode must be 'nixos' or 'home-manager', got {mode!r}",
        }

    if action == "list":
        if mode == "nixos":
            return _list_nixos()
        envelope, _ = _list_hm()
        return envelope

    # rollback
    if mode == "nixos":
        nixos_rebuild = runner.resolve_binary("nixos-rebuild") or "nixos-rebuild"
        result = runner.run(["sudo", nixos_rebuild, "switch", "--rollback"])
        return runner.envelope(
            "ok" if result.ok else "failed",
            SYSTEM_PROFILE,
            result,
            current_generation=_current_generation(mode),
        )
    _, gens = _list_hm()
    if len(gens) < 2:
        return {
            "status": "failed",
            "resolved_target": "home-manager profile",
            "error": "no previous home-manager generation to roll back to",
        }
    previous = gens[1]
    result = runner.run([f"{previous['path']}/activate"])
    return runner.envelope(
        "ok" if result.ok else "failed",
        "home-manager profile",
        result,
        activated_generation=previous,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_switch_generations.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add src/nix_agent/tools/switch.py tests/test_switch_generations.py
git commit -m "feat: add switch and generations tools with HM rollback"
```

---

### Task 8: Rewrite `server.py`, delete the patch pipeline

**Files:**
- Modify: `src/nix_agent/server.py` (full rewrite)
- Delete: `src/nix_agent/models.py`, `src/nix_agent/patching.py`, `src/nix_agent/inspect.py`, `src/nix_agent/system_apply.py`, `tests/test_apply_patch_set.py`
- Modify: `tests/test_imports.py`
- Test: `tests/test_server.py` (new)

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_server.py
import asyncio

from nix_agent.server import build_server

EXPECTED_TOOLS = {
    "eval_config",
    "check",
    "format",
    "build",
    "diff",
    "switch",
    "generations",
}


def test_server_exposes_exactly_the_seven_tools():
    server = build_server()
    tools = asyncio.run(server.get_tools())
    assert set(tools.keys()) == EXPECTED_TOOLS
```

Also update `tests/test_imports.py`:

```python
# tests/test_imports.py
from nix_agent.server import build_server


def test_build_server_exists():
    assert callable(build_server)


def test_old_modules_are_gone():
    import importlib.util

    for gone in ("nix_agent.models", "nix_agent.patching",
                 "nix_agent.inspect", "nix_agent.system_apply"):
        assert importlib.util.find_spec(gone) is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_server.py tests/test_imports.py -v`
Expected: `test_server_exposes_exactly_the_seven_tools` FAILS (old tools present), `test_old_modules_are_gone` FAILS (modules still exist)

Note: if `server.get_tools()` is not the right FastMCP API in the installed version, check with `python -c "from fastmcp import FastMCP; help(FastMCP)"` and use the equivalent listing method — the assertion (exactly these seven names) stays the same.

- [ ] **Step 3: Rewrite `server.py` and delete old modules**

```python
# src/nix_agent/server.py
from fastmcp import FastMCP
from fastmcp.tools.tool import Tool

from nix_agent.tools.build import build, diff
from nix_agent.tools.check import check
from nix_agent.tools.eval import eval_config
from nix_agent.tools.fmt import format_nix
from nix_agent.tools.switch import generations, switch

_TOOLS = [
    (
        eval_config,
        "eval_config",
        "Evaluate the final merged value of an attribute in the user's "
        "actual NixOS/Home Manager configuration via `nix eval` "
        "(e.g. attr='services.openssh.enable'). flake_uri and mode "
        "auto-resolve when omitted.",
    ),
    (
        check,
        "check",
        "Validation ladder for the configuration, fast to slow: "
        "level='lint' (statix+deadnix, structured findings), 'flake' "
        "(nix flake check), 'dry-build' (evaluate and plan the closure "
        "build), 'dry-activate' (NixOS only, shows what activation "
        "would change).",
    ),
    (
        format_nix,
        "format",
        "Format .nix files. With paths: nixfmt per file. Without: "
        "`nix fmt` in the flake directory, falling back to nixfmt on "
        "all .nix files when the flake defines no formatter.",
    ),
    (
        build,
        "build",
        "Build the full system/HM closure without activating it. "
        "Returns the output store path.",
    ),
    (
        diff,
        "diff",
        "Build the new closure and diff it against the running system "
        "(nvd, falling back to nix store diff-closures): package "
        "additions, removals, version changes. Use before switch.",
    ),
    (
        switch,
        "switch",
        "Activate the configuration (sudo nixos-rebuild switch / "
        "home-manager switch). Records rollback_generation first. No "
        "implicit validation: run check/diff first as needed.",
    ),
    (
        generations,
        "generations",
        "action='list': enumerate system/HM generations with dates and "
        "current marker. action='rollback': revert to the previous "
        "generation.",
    ),
]


def build_server() -> FastMCP:
    server = FastMCP("nix-agent")
    for fn, name, description in _TOOLS:
        server.add_tool(Tool.from_function(fn, name=name, description=description))
    return server
```

Delete the old modules and their test:

```bash
git rm src/nix_agent/models.py src/nix_agent/patching.py src/nix_agent/inspect.py src/nix_agent/system_apply.py tests/test_apply_patch_set.py
```

- [ ] **Step 4: Run the full suite**

Run: `pytest -v`
Expected: all PASS, no references to deleted modules anywhere (`rg "system_apply|patching|PatchSet|inspect_state" src/ tests/` returns nothing)

- [ ] **Step 5: Commit**

```bash
git add src/nix_agent/server.py tests/test_server.py tests/test_imports.py
git commit -m "refactor!: replace patch pipeline with seven-tool nix ops surface"
```

---

### Task 9: Packaging — flake bundles the external tools, version 0.5.0

**Files:**
- Modify: `flake.nix`
- Modify: `pyproject.toml`

- [ ] **Step 1: Update `pyproject.toml`**

Change version and description:

```toml
[project]
name = "nix-agent"
version = "0.5.0"
description = "MCP server exposing composable NixOS/Home Manager operations: eval, lint, format, build, diff, switch, generations."
```

(rest of the file unchanged)

- [ ] **Step 2: Update `flake.nix`**

Change the package version to `0.5.0` and replace the wrapper/devShell tool set. The wrapped PATH is what makes lint/diff work out of the box:

```nix
postFixup = ''
  wrapProgram "$out/bin/nix-agent" \
    --prefix PATH : "${lib.makeBinPath [
      pkgs.statix
      pkgs.deadnix
      pkgs.nixfmt-rfc-style
      pkgs.nvd
    ]}"
'';
```

And in `devShells.default`, replace `pkgs.nixpkgs-fmt` with:

```nix
buildInputs = [
  python
  pkgs.python3Packages.pytest
  pkgs.statix
  pkgs.deadnix
  pkgs.nixfmt-rfc-style
  pkgs.nvd
];
```

Also update the flake `description` to: `"MCP server and companion skill exposing composable NixOS operations"`.

- [ ] **Step 3: Validate the flake**

Run: `nix flake check` (builds the package, runs `checks.default`)
Expected: success. If `nixfmt-rfc-style` has been renamed in current nixpkgs (it is `nixfmt` upstream as of 2025), `nix flake check` will say so — use whichever attr evaluates; verify with `nix eval nixpkgs#nixfmt-rfc-style.pname` vs `nix eval nixpkgs#nixfmt.pname`.

- [ ] **Step 4: Commit**

```bash
git add flake.nix pyproject.toml
git commit -m "chore: bump to 0.5.0, bundle statix/deadnix/nixfmt/nvd in wrapper"
```

---

### Task 10: Rewrite the companion skill

**Files:**
- Modify: `skills/nix-agent/SKILL.md` (full rewrite)
- Check: `skills/nix-agent/TESTING.md` — update any references to removed tools

- [ ] **Step 1: Replace `skills/nix-agent/SKILL.md` with:**

```markdown
---
name: nix-agent
description: Use when a user wants to change NixOS packages, options, modules, or local configuration and the host exposes the nix-agent MCP server (usually alongside mcp-nixos).
---

# Nix Agent

## Overview

`nix-agent` is a pure Nix operations toolbox. It does NOT read or write
files — use your own file tools (Read/Edit/Write) for that. It gives you
the NixOS-specific operations: evaluate the live config, lint, format,
validate, build, diff, switch, and manage generations.

Division of labor:
- **Your native tools** — read and edit `.nix` files.
- **`mcp-nixos`** — discover packages and options (what exists, what it means).
- **`nix-agent`** — operate on the user's actual configuration (what their machine resolves, whether it builds, what a switch would change).

## Tool Surface

All tools auto-resolve the target when `flake_uri` is omitted
(`/etc/nixos#<hostname>` for NixOS, `~/.config/home-manager` for Home
Manager) and echo back `resolved_target` and the exact `command` run.
Pass `mode="home-manager"` for HM configs.

- `eval_config(attr, flake_uri?, mode?)` — final merged value of any
  config attribute on THIS machine (after all modules/overlays).
  `mcp-nixos` tells you what an option means; this tells you what it is.
- `check(level, flake_uri?, mode?)` — validation ladder, fast to slow:
  `"lint"` (statix + deadnix, structured findings), `"flake"`,
  `"dry-build"`, `"dry-activate"` (NixOS only).
- `format(paths?, flake_uri?, mode?)` — `nix fmt` / nixfmt.
- `build(flake_uri?, mode?)` — build the closure, no activation.
- `diff(flake_uri?, mode?)` — what a switch would change (package
  adds/removes/version bumps). Show this to the user before switching.
- `switch(flake_uri?, mode?)` — activate. Records `rollback_generation`.
- `generations(action="list"|"rollback", mode?)` — list or roll back.

## Recommended Workflow

1. Discovery (if needed): query `mcp-nixos` for packages/options;
   `eval_config` to see what the user's machine currently resolves.
2. Edit `.nix` files with your native file tools.
3. `format()` then `check("lint")` — fix findings worth fixing.
4. `check("dry-build")` — catches eval/build errors cheaply. On failure,
   `first_error` has the actionable line.
5. `diff()` — show the user what will change.
6. `switch()` — report the result and `rollback_generation`.
7. On regret: `generations(action="rollback")`.

Steps 3–5 are judgment calls, not gates — for a trivial change, going
straight to `switch` is fine. Compose what the situation needs.

## Failure Handling

- `status="failed"` — read `first_error` first, full `output` second.
  Fix the config and retry; don't retry blindly.
- `status="no_target"` — pass an explicit `flake_uri`.
- `status="tool_missing"` — the named binary isn't on PATH (only
  happens outside the flake-packaged install).

## Hard Rules

- Never write secret payloads into config files; reference secrets via
  sops-nix/agenix and only edit references.
- Never call `switch` when the user asked only to check or preview;
  `diff` is the preview.
```

- [ ] **Step 2: Update `skills/nix-agent/TESTING.md`**

Read it; rewrite any walkthroughs that call `inspect_state`/`apply_patch_set` to use the new tools (the file is a manual test checklist — mirror the Recommended Workflow above).

- [ ] **Step 3: Run the distribution tests**

Run: `pytest tests/test_cli.py tests/test_distribution.py -v`
Expected: PASS (skill file still exists with `name: nix-agent`)

- [ ] **Step 4: Commit**

```bash
git add skills/nix-agent/SKILL.md skills/nix-agent/TESTING.md
git commit -m "docs: rewrite companion skill for the composable tool surface"
```

---

### Task 11: Update README, CLAUDE.md, agent-install docs

**Files:**
- Modify: `README.md`
- Modify: `CLAUDE.md`
- Modify: `docs/agent-install.md`

- [ ] **Step 1: README.md**

Replace the "Tool surface" section (lines ~85–95) with the seven-tool table (same content as SKILL.md's Tool Surface, table form). Replace "Basic workflow" with the edit-with-native-tools → format → check → diff → switch flow. Update the intro line to "a local MCP server that gives AI agents composable NixOS operations: eval, lint, format, build, diff, switch, generations." Keep install sections unchanged. In "Design notes", replace the patch-oriented bullets with:

```markdown
## Design notes

- nix-agent does no file I/O. The host agent's own file tools are better
  at reading and editing; nix-agent only provides the Nix operations
  around them.
- No in-MCP approval gates. Path restrictions belong to the host's
  permission system; rollback safety belongs to Nix generations.
- Every response echoes `resolved_target` and the exact `command` run —
  nothing is silently implicit.
- Do not write secret payloads into configs — reference secrets via
  sops-nix or agenix.
- Fully non-interactive switch requires privileged automation; see
  `docs/privileged-automation.md`.
```

- [ ] **Step 2: CLAUDE.md**

Rewrite points 2 and 3 of the operational notes to describe the seven tools and the compose-it-yourself workflow (mirror SKILL.md, condensed). Point 1's purpose sentence becomes: "nix-agent is the local operations half of the two-server workflow. It evaluates, lints, formats, builds, diffs, switches, and manages generations for NixOS/Home Manager configs. The agent edits files with its own tools; package/option discovery stays in mcp-nixos."

- [ ] **Step 3: docs/agent-install.md**

Read it; update any tool-surface descriptions and permission examples that reference `inspect_state`/`apply_patch_set` to the new tool names. Installation mechanics (flake, MCP registration, sudo NOPASSWD rule for `nixos-rebuild`) stay the same.

- [ ] **Step 4: Check for stragglers**

Run: `rg -l "apply_patch_set|inspect_state|PatchSet" --glob '!docs/superpowers/**'`
Expected: no matches (spec/plan under docs/superpowers/ may mention them historically; that's fine).

- [ ] **Step 5: Commit**

```bash
git add README.md CLAUDE.md docs/agent-install.md
git commit -m "docs: update README, CLAUDE.md, and install docs for v0.5.0 surface"
```

---

### Task 12: Final verification

- [ ] **Step 1: Full test suite**

Run: `pytest -v`
Expected: all PASS

- [ ] **Step 2: Flake build + check**

Run: `nix flake check`
Expected: success (package builds with the new wrapper)

- [ ] **Step 3: Smoke-test the server starts**

Run: `python -c "from nix_agent.server import build_server; s = build_server(); print('ok')"`
Expected: prints `ok`

- [ ] **Step 4: Live smoke test (this machine is NixOS)**

These hit the real system read-only — safe:

```bash
python - <<'EOF'
from nix_agent.tools.eval import eval_config
from nix_agent.tools.check import check
from nix_agent.tools.switch import generations
print(eval_config("networking.hostName"))
print(check("lint"))
print(generations())
EOF
```

Expected: `eval_config` returns the actual hostname with `status: ok`; `check("lint")` returns findings (possibly empty) with `status: ok`; `generations()` lists real system generations. Do NOT run `switch` as part of this plan.

- [ ] **Step 5: Commit any fixes, then tag readiness**

If the smoke test surfaced parser fixes, commit them as `fix:` commits. Final state: clean `git status`, green `pytest`, green `nix flake check`.
```
