import asyncio

from nix_agent.server import build_server

EXPECTED_TOOLS = {
    "build",
    "diff",
    "switch",
    "generations",
    "eval_config",
    "locate_option",
    "check",
}


def test_server_exposes_exactly_the_expected_tools():
    server = build_server()
    if hasattr(server, "list_tools"):
        tools = asyncio.run(server.list_tools())
    else:
        tools = asyncio.run(server.get_tools()).values()
    assert {t.name for t in tools} == EXPECTED_TOOLS


def test_diff_tool_description_defaults_to_apply():
    server = build_server()
    if hasattr(server, "list_tools"):
        tools = asyncio.run(server.list_tools())
        description = next(t.description for t in tools if t.name == "diff")
    else:
        tools = asyncio.run(server.get_tools())
        description = tools["diff"].description
    assert "unless the user asked only to preview" in description
    assert "Preview before switch" not in description
