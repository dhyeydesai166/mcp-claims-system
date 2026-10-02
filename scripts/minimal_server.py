from mcp.server.mcpserver import MCPServer

mcp = MCPServer("equipment-ping")


@mcp.tool(structured_output=False)
def ping(name: str) -> str:
    """Return pong plus the given name.
    Used only to prove the client reached the server.
    This is a test tool."""
    return f"pong {name}"


if __name__ == "__main__":
    mcp.run(transport="stdio")
