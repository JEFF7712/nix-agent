from nix_agent import logparse

EVAL_ERROR = """\
error:
       … while calling the 'seq' builtin
         at /nix/store/abc-source/lib/modules.nix:334:18:
       … while evaluating a branch condition
         at /nix/store/abc-source/lib/lists.nix:57:9:
       error: attribute 'foo' missing
         at /home/user/nixos/modules/net.nix:12:5:
           11|   config = {
           12|     networking.hostName = cfg.foo;
             |     ^
"""


def test_extract_error_detail_full():
    detail = logparse.extract_error_detail(EVAL_ERROR)
    assert detail == {
        "message": "attribute 'foo' missing",
        "file": "/home/user/nixos/modules/net.nix",
        "line": 12,
        "column": 5,
        "trace": [
            "while calling the 'seq' builtin",
            "while evaluating a branch condition",
        ],
    }


def test_extract_error_detail_requires_location():
    assert logparse.extract_error_detail("error: something broke") is None
    assert logparse.extract_error_detail("") is None
    assert logparse.extract_error_detail(None) is None


def test_extract_error_detail_trace_capped():
    frames = "\n".join(
        f"       … while evaluating frame {i}\n         at /f{i}.nix:1:1:"
        for i in range(8)
    )
    text = frames + "\n       error: boom\n         at /home/u/x.nix:3:7:"
    detail = logparse.extract_error_detail(text)
    assert detail["message"] == "boom"
    assert detail["file"] == "/home/u/x.nix"
    assert len(detail["trace"]) == 5


def test_extract_error_detail_location_before_message():
    # some nix versions print the final location above the deepest error line
    text = (
        "       … while evaluating x\n"
        "         at /home/u/y.nix:9:2:\n"
        "       error: infinite recursion encountered"
    )
    detail = logparse.extract_error_detail(text)
    assert detail["message"] == "infinite recursion encountered"
    assert detail["file"] == "/home/u/y.nix"
    assert detail["line"] == 9


def test_extract_error_detail_no_cross_block_location():
    text = (
        "       error: first failure\n"
        "         at /home/u/first.nix:1:1:\n"
        "       error: second failure with no location"
    )
    assert logparse.extract_error_detail(text) is None


BUILD_FAILURE = """\
building '/nix/store/aaa-dep.drv'...
error: builder for '/nix/store/bbb-leaf-1.0.drv' failed with exit code 1;
       last 10 log lines:
       > make: *** [Makefile:2: all] Error 1
       For full logs, run 'nix log /nix/store/bbb-leaf-1.0.drv'.
error: 1 dependencies of derivation '/nix/store/ccc-system.drv' failed to build
"""


def test_extract_failed_drvs():
    assert logparse.extract_failed_drvs(BUILD_FAILURE) == [
        "/nix/store/bbb-leaf-1.0.drv"
    ]


def test_extract_failed_drvs_dedup_and_order():
    text = (
        BUILD_FAILURE
        + BUILD_FAILURE
        + (
            "error: builder for '/nix/store/ddd-other-2.0.drv' failed with exit code 2\n"
        )
    )
    assert logparse.extract_failed_drvs(text) == [
        "/nix/store/bbb-leaf-1.0.drv",
        "/nix/store/ddd-other-2.0.drv",
    ]


def test_extract_failed_drvs_none():
    assert logparse.extract_failed_drvs("error: attribute 'x' missing") == []
    assert logparse.extract_failed_drvs("") == []


def test_tail_lines():
    text = "\n".join(f"line{i}" for i in range(100))
    out = logparse.tail_lines(text, n=40)
    assert out.endswith("line99")
    assert "line59" not in out.splitlines()[0]
    assert "60 leading lines omitted" in out
    assert logparse.tail_lines("a\nb", n=40) == "a\nb"


NVD_OUTPUT = """\
<<< /run/current-system
>>> /nix/store/zzz-nixos-system-laptop
Version changes:
[U.]  #1  firefox  128.0 -> 129.0
[C.]  #2  linux    6.6.30 -> 6.6.32
Added packages:
[A+]  #1  htop  3.3.0
Removed packages:
[R-]  #1  tmux  3.4
Closure size: 1234 -> 1250 paths.
"""

DIFF_CLOSURES_OUTPUT = """\
firefox: 128.0 → 129.0, \x1b[31;1m12.3 KiB\x1b[0m
htop: ∅ → 3.3.0, \x1b[31;1m512.4 KiB\x1b[0m
tmux: 3.4 → ∅, \x1b[32;1m-800.1 KiB\x1b[0m
libfoo: \x1b[31;1m8.8 KiB\x1b[0m
"""


def test_parse_nvd():
    packages = logparse.parse_nvd(NVD_OUTPUT)
    assert packages == {
        "added": [{"name": "htop", "version": "3.3.0"}],
        "removed": [{"name": "tmux", "version": "3.4"}],
        "changed": [
            {"name": "firefox", "old": "128.0", "new": "129.0"},
            {"name": "linux", "old": "6.6.30", "new": "6.6.32"},
        ],
    }


def test_parse_nvd_unrecognized_returns_none():
    assert logparse.parse_nvd("random text\nno sections here") is None


NVD_SELECTION_OUTPUT = """\
<<< /nix/var/nix/profiles/system-740-link
>>> /nix/var/nix/profiles/system-741-link
Version changes:
[U.]  #1  firefox  128.0 -> 129.0
Selection state changes:
[C+]  #1  age   1.3.1, 1.3.1-fish-completions
[C+]  #2  sops  3.13.1, 3.13.1-fish-completions
Closure size: 4355 -> 4359 (26 paths added, 22 paths removed, delta +4, disk usage +51.5MiB).
"""


def test_parse_nvd_ignores_unknown_sections():
    packages = logparse.parse_nvd(NVD_SELECTION_OUTPUT)
    assert packages["changed"] == [{"name": "firefox", "old": "128.0", "new": "129.0"}]
    assert all(
        "fish-completions" not in str(p) for lst in packages.values() for p in lst
    )


def test_parse_diff_closures():
    packages = logparse.parse_diff_closures(DIFF_CLOSURES_OUTPUT)
    assert packages == {
        "added": [{"name": "htop", "version": "3.3.0"}],
        "removed": [{"name": "tmux", "version": "3.4"}],
        "changed": [{"name": "firefox", "old": "128.0", "new": "129.0"}],
    }


def test_parse_diff_closures_unrecognized_returns_none():
    assert logparse.parse_diff_closures("nothing matching") is None
