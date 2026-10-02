import asyncio
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def main() -> None:
    params = StdioServerParameters(
        command=sys.executable,
        args=["scripts/minimal_server.py"],
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            print("tools:", [tool.name for tool in tools.tools])
            result = await session.call_tool("ping", {"name": "equipment"})
            texts = [block.text for block in result.content if getattr(block, "text", None)]
            print("\n".join(texts) if texts else result)


if __name__ == "__main__":
    asyncio.run(main())