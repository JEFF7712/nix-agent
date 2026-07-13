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
