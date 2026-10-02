import asyncio
import os
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def main() -> None:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1] / "src")
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "claims.server"],
        env=env,
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            print("tools:", [tool.name for tool in tools.tools])
            result = await session.call_tool(
                "get_employee_info",
                {"employee_id": "E101"},
            )
            texts = []
            for block in result.content:
                text = getattr(block, "text", None)
                if isinstance(text, str):
                    texts.append(text)
            print("\n".join(texts) if texts else result)


if __name__ == "__main__":
    asyncio.run(main())
