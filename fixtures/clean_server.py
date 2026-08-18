import sys
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("clean-demo-server")


@mcp.tool()
def add_numbers(a: int, b: int) -> int:
    """Add two numbers together."""
    print(f"DEBUG: adding {a} + {b}", file=sys.stderr)
    return a + b


@mcp.tool()
def get_greeting(name: str) -> str:
    """Return a friendly greeting for the given name."""
    return f"Hello, {name}!"


@mcp.tool()
def divide(a: int, b: int) -> float:
    """Divide a by b."""
    return a / b


if __name__ == "__main__":
    mcp.run(transport="stdio")
