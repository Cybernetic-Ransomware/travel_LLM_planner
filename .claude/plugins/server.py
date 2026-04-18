import json

import httpx

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool


BASE_URL = "http://localhost:8080"

server = Server(name="MCP_endpoint")


@server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="get_places",
            description="Fetch places from the travel-planner API",
            inputSchema={
                "type": "object",
                "properties": {
                    "skipped": {
                        "type": "boolean",
                        "description": "Filter places by skipped status"
                    }
                },
                "required": []
            }
        )
    ]


@server.call_tool()
async def call_tool(tool_name: str, arguments: dict) -> list[TextContent]:
    if tool_name == "get_places":
        skipped = arguments.get("skipped", False)
        async with httpx.AsyncClient(base_url=BASE_URL) as client:
            response = await client.get(
                "/api/v1/core/gmaps/places",
                params={"skipped": str(skipped).lower()},
                headers={"accept": "application/json"},
            )
            response.raise_for_status()
            return [TextContent(type="text", text=json.dumps(response.json(), indent=2))]
    raise ValueError(f"Unknown tool: {tool_name}")


if __name__ == "__main__":
    import anyio

    async def main() -> None:
        async with stdio_server() as (read_stream, write_stream):
            await server.run(read_stream, write_stream, server.create_initialization_options())

    anyio.run(main)