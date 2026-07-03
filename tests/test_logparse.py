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
