import os
from pathlib import Path
import sys

import anyio
from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client


EXPECTED_TOOLS = {
    "eval_config",
    "check",
    "format",
    "build",
    "diff",
    "switch",
    "generations",
    "locate_option",
    "inspect_flake",
}


def test_stdio_server_lists_tools_over_mcp_protocol():
    async def run_smoke():
        env = os.environ.copy()
        src = str(Path.cwd() / "src")
        env["PYTHONPATH"] = (
            f"{src}{os.pathsep}{env['PYTHONPATH']}" if env.get("PYTHONPATH") else src
        )
        params = StdioServerParameters(
            command=sys.executable,
            args=["-m", "nix_agent"],
            cwd=Path.cwd(),
            env=env,
        )
        async with stdio_client(params) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                result = await session.list_tools()
                assert {tool.name for tool in result.tools} == EXPECTED_TOOLS

    anyio.run(run_smoke)
