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
    tools = asyncio.run(server.list_tools())
    assert {t.name for t in tools} == EXPECTED_TOOLS
