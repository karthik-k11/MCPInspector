from mcp.server.fastmcp import FastMCP


mcp = FastMCP("MCPInspector demo")


@mcp.tool()
def add(a: int, b: int) -> int:
    """Add two integers and return their sum."""
    return a + b


@mcp.resource("demo://status")
def server_status() -> str:
    """Return a simple server health response."""
    return "ready"


@mcp.prompt()
def explain(value: str) -> str:
    """Create a short explanation request for a value."""
    return f"Explain this value: {value}"


if __name__ == "__main__":
    mcp.run(transport="stdio")
