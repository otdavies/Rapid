#!/usr/bin/env python3
"""
RAPID MCP server for maintaining project context.
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

from logic.tool_implementations import get_full_context_impl, project_wide_search_impl, concept_search_impl


class RAPIDServer:
    """
    Project Intelligence MCP Server: Provides advanced tools for deep codebase analysis,
    understanding, and navigation. Enables an AI assistant to effectively explore, search,
    and comprehend complex software projects by offering structured context retrieval,
    precise string searching, and powerful semantic concept location.
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
            self._get_project_full_code_context_tool_definition(),
            self._get_project_find_string_tool_definition(),
            self._get_project_find_code_by_concept_tool_definition(),
        ]

    def _get_project_find_string_tool_definition(self) -> types.Tool:
        """Returns the definition for the 'project_find_string' tool."""
        return types.Tool(
            name="find_string",
            description="Efficiently searches all files within a specified project directory for an exact string or pattern. Ideal for locating specific code snippets, configurations, or mentions across the entire codebase. Returns matches with surrounding context lines.",
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
                        "description": "File extensions to scan (Available: .ts .rs, .py, .cs). If not provided, a default set will be used."
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

    def _get_project_full_code_context_tool_definition(self) -> types.Tool:
        """Returns the definition for the 'project_get_full_code_context' tool."""
        return types.Tool(
            name="get_full_code_context",
            description="Comprehensively scans a project directory to extract and structure code from specified file types. Generates a detailed overview of the project's content, including file structures and optionally, function/class descriptions. Essential for gaining a holistic understanding of a codebase.",
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
                        "description": "File extensions to scan (Available: .ts .rs, .py, .cs). If not provided, a default set will be used."
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
                        "description": "Controls output verbosity: 0 (ultra-compact summary), 1 (compact, default), 2 (medium detail), 3 (highly detailed with full code snippets). Choose based on the level of detail required."
                    },
                    "include_descriptions": {
                        "type": "boolean",
                        "description": "Set to true to include AI-generated summaries for files and major code structures (functions, classes). False provides raw code structure only."
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

    def _get_project_find_code_by_concept_tool_definition(self) -> types.Tool:
        """Returns the definition for the 'project_find_code_by_concept' tool."""
        return types.Tool(
            name="find_code_by_concept",
            description="Performs a powerful semantic search across the codebase to find functions or code blocks related to a natural language query. Instead of exact string matching, it understands the *intent* behind the query to locate relevant functionality. Useful for discovering how specific concepts are implemented or finding code when you don't know the exact names or terms.",
            inputSchema={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Absolute path to the project directory."
                    },
                    "query": {
                        "type": "string",
                        "description": "A natural language description of the functionality or concept you are searching for (e.g., 'how user authentication is handled', 'function to parse JSON data')."
                    },
                    "extensions": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "File extensions to scan. Defaults to common code extensions. (Available: .ts .rs, .py, .cs)"
                    },
                    "top_n": {
                        "type": "integer",
                        "description": "Number of top results to return. Default is 10."
                    },
                    "timeout": {
                        "type": "integer",
                        "description": "Timeout in seconds for the operation. Default is 20."
                    },
                    "debug": {
                        "type": "boolean",
                        "description": "Whether to include the debug log in the output. Defaults to false.",
                        "default": False
                    }
                },
                "required": ["path", "query"]
            }
        )

    async def call_tool(
        self, name: str, arguments: Optional[Dict[str, Any]]
    ) -> List[types.TextContent]:
        """Handles tool calls from the client."""
        try:
            if name == "get_full_code_context":
                result = await get_full_context_impl(arguments or {})
            elif name == "find_string":
                result = await project_wide_search_impl(arguments or {})
            elif name == "find_code_by_concept":
                result = await concept_search_impl(arguments or {})
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
    server = RAPIDServer()
    asyncio.run(server.run())


if __name__ == "__main__":
    main()  # Entry point
