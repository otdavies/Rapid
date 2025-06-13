#!/usr/bin/env python3
"""
MCP server for maintaining project context.
This server acts as an orchestration layer, delegating tasks to specialized modules.
"""

import asyncio
import json
import traceback
from typing import Any, Dict, List, Optional

from mcp.server import Server, NotificationOptions
from mcp.server.models import InitializationOptions
import mcp.server.stdio
import mcp.types as types

from logic.tool_implementations import get_full_context_impl, project_wide_search_impl


class ProjectContextServer:
    """
    MCP server for maintaining project context.
    This server acts as an orchestration layer, delegating tasks to specialized modules.
    """
    SERVER_NAME = "project-context"
    SERVER_VERSION = "0.4.0"

    def __init__(self):
        self.server = Server(self.SERVER_NAME)
        self._setup_routes()

    def _setup_routes(self):
        """Configures the routes for the MCP server."""
        self.server.list_tools()(self.list_tools)
        self.server.call_tool()(self.call_tool)

    async def list_tools(self) -> List[types.Tool]:
        """Lists the available tools."""
        return [
            self._get_full_context_tool_definition(),
            self._get_project_wide_search_tool_definition(),
        ]

    def _get_project_wide_search_tool_definition(self) -> types.Tool:
        """Returns the definition for the 'project_wide_search' tool."""
        return types.Tool(
            name="project_wide_search",
            description="Perform a project-wide search for a string.",
            inputSchema={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Absolute path to the project directory."
                    },
                    "search_string": {
                        "type": "string",
                        "description": "The string to search for."
                    },
                    "extensions": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "File extensions to scan (e.g., .rs, .py, .cs). If not provided, a default set will be used."
                    },
                    "max_depth": {
                        "type": "integer",
                        "description": "Maximum depth to scan directories. Default is 6."
                    },
                    "max_files": {
                        "type": "integer",
                        "description": "Maximum number of files to process. Default is 1000."
                    },
                    "timeout": {
                        "type": "integer",
                        "description": "Timeout in seconds for the operation. Default is 60."
                    },
                    "context_lines": {
                        "type": "integer",
                        "description": "Number of context lines to show around each match. Default is 2."
                    },
                    "debug": {
                        "type": "boolean",
                        "description": "Whether to include the debug log in the output. Defaults to false.",
                        "default": False
                    }
                },
                "required": ["path", "search_string"]
            }
        )

    def _get_full_context_tool_definition(self) -> types.Tool:
        """Returns the definition for the 'get_full_context' tool."""
        return types.Tool(
            name="get_full_context",
            description="Scrape the project directory for code files and return the full context.",
            inputSchema={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Absolute path to the project directory."
                    },
                    "extensions": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "File extensions to scan (e.g., .rs, .py, .cs). If not provided, a default set will be used."
                    },
                    "max_depth": {
                        "type": "integer",
                        "description": "Maximum depth to scan directories. Default is 6."
                    },
                    "max_files": {
                        "type": "integer",
                        "description": "Maximum number of files to process. Default is 1000."
                    },
                    "timeout": {
                        "type": "integer",
                        "description": "Timeout in seconds for the operation. Default is 60."
                    },
                    "compactness_level": {
                        "type": "integer",
                        "description": "Controls output verbosity: 0 (ultra-compact), 1 (compact), 2 (medium), 3 (detailed). Default is 1."
                    },
                    "include_descriptions": {
                        "type": "boolean",
                        "description": "Whether to include function and file descriptions. Default is true."
                    },
                    "debug": {
                        "type": "boolean",
                        "description": "Whether to include the debug log in the output. Defaults to false.",
                        "default": False
                    }
                },
                "required": ["path"]
            }
        )

    async def call_tool(
        self, name: str, arguments: Optional[Dict[str, Any]]
    ) -> List[types.TextContent]:
        """Handles tool calls from the client."""
        try:
            if name == "get_full_context":
                result = await get_full_context_impl(arguments or {})
            elif name == "project_wide_search":
                result = await project_wide_search_impl(arguments or {})
            else:
                result = {"status": "error", "error": f"Unknown tool: {name}"}

            return [types.TextContent(type="text", text=json.dumps(result, indent=2))]

        except Exception as e:
            error_info = {
                "status": "error",
                "error": f"An unexpected error occurred in tool '{name}': {e}",
                "traceback": traceback.format_exc()
            }
            return [types.TextContent(type="text", text=json.dumps(error_info))]

    def _get_initialization_options(self) -> InitializationOptions:
        """Returns the initialization options for the server."""
        return InitializationOptions(
            server_name=self.SERVER_NAME,
            server_version=self.SERVER_VERSION,
            capabilities=self.server.get_capabilities(
                notification_options=NotificationOptions(),
                experimental_capabilities={},
            ),
        )

    async def run(self):
        """Starts the server and listens for requests."""
        async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
            await self.server.run(
                read_stream,
                write_stream,
                self._get_initialization_options(),
            )


def main():
    server = ProjectContextServer()
    asyncio.run(server.run())


if __name__ == "__main__":
    main()
