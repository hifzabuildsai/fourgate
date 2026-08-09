"""
A deliberately broken MCP server, for demoing Fourgate's checks.

Bug 1: a stray print() statement pollutes stdout, which breaks the
       JSON-RPC stream on stdio transport (Concept from the Connector-Native
       Apps course: "any non-JSON output to stdout breaks the parser").
Bug 2: the add_numbers tool does no input validation, so a string where a
       number is expected causes an unhandled crash instead of a clean
       schema-validation error.
"""
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("broken-demo-server")


@mcp.tool()
def add_numbers(a: int, b: int) -> int:
    """Add two numbers together."""
    # BUG 1: this print() goes to stdout, polluting the JSON-RPC stream.
    print(f"DEBUG: adding {a} + {b}")

    # BUG 2: no validation -- if the caller (or a confused LLM) sends a
    # string here, this throws an unhandled TypeError instead of a clean
    # schema-validation error the client can recover from.
    return a + b


@mcp.tool()
def get_greeting(name: str) -> str:
    """Return a friendly greeting for the given name."""
    return f"Hello, {name}!"


@mcp.tool()
def divide(a: int, b: int) -> float:
    """Divide a by b."""
    # BUG 3: a real crash the type schema can never catch, because 0 is a
    # perfectly valid integer. This is the value-edge-case failure the
    # course warns about: an LLM WILL eventually pass b=0.
    return a / b


if __name__ == "__main__":
    mcp.run(transport="stdio")
