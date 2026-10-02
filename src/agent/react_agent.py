import asyncio
import os
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


def server_parameters() -> StdioServerParameters:
    env = os.environ.copy()
    root = Path(__file__).resolve().parents[2]
    env["PYTHONPATH"] = str(root / "src")
    return StdioServerParameters(
        command=sys.executable,
        args=["-m", "claims.server"],
        env=env,
    )


async def main() -> None:
    employee_id = "E101"
    request = "I need a monitor."
    print("employee_id:", employee_id)
    print("request:", request)
    async with stdio_client(server_parameters()) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(
                "get_employee_info",
                {"employee_id": employee_id},
            )
            texts = []
            for block in result.content:
                text = getattr(block, "text", None)
                if isinstance(text, str):
                    texts.append(text)
            print("\n".join(texts) if texts else result)


if __name__ == "__main__":
    asyncio.run(main())
