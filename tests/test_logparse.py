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
