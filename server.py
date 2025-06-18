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

from logic.tool_implementations import (
    get_full_context_impl,
    project_wide_search_impl,
    concept_search_impl,
    initialize_project_context_impl
)


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
            self._get_initialize_project_context_tool_definition(),  # Added new tool
            self._get_project_full_code_context_tool_definition(),
            self._get_project_find_string_tool_definition(),
            self._get_project_find_code_by_concept_tool_definition(),
        ]

    def _get_initialize_project_context_tool_definition(self) -> types.Tool:
        """Returns the definition for the 'initialize_project_context' tool."""
        return types.Tool(
            name="initialize_project_context",
            description="""
Initializes project context by reading/creating plan.md.

This tool is the critical first step for interacting with a project. It establishes a shared understanding
of the project's goals and status by reading the `plan.md` file.

**You must adhere to the following protocol:**
1.  **Always call this tool first** before taking any other action in a project.
2.  **Carefully read the entire output**, especially the contents of `plan.md`.
3.  **Preserve and update `plan.md`:** As you complete tasks, update this file to reflect the current
    project status. It is the single source of truth for project planning.

The tool also provides a lightweight complexity assessment to guide your next steps.
""",
            inputSchema={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Absolute path to the project directory."
                    },
                    "timeout": {
                        "type": "integer",
                        "description": "Timeout in seconds for the initial scan. Default is 10.",
                        "default": 10
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
        """Handles tool calls from the client. All tools now return a dictionary
        with 'text_output' and optionally 'debug_log_for_text_output'."""
        try:
            tool_function = None
            if name == "get_full_code_context":
                tool_function = get_full_context_impl
            elif name == "find_string":
                tool_function = project_wide_search_impl
            elif name == "find_code_by_concept":
                tool_function = concept_search_impl
            elif name == "initialize_project_context":
                tool_function = initialize_project_context_impl
            else:
                # Handle unknown tool by creating a compatible error dict
                tool_result_dict = {
                    "status": "error_text_output",  # Consistent status for text output
                    "text_output": f"--- Error ---\nUnknown tool: {name}"
                }
                # No debug log to append for an unknown tool error
                return [types.TextContent(type="text", text=tool_result_dict["text_output"])]

            if tool_function:
                tool_result_dict = await tool_function(arguments or {})
            else:  # Should not be reached if logic above is correct, but as a safeguard
                tool_result_dict = {
                    "status": "error_text_output",
                    "text_output": f"--- Error ---\nTool function for '{name}' not found internally."
                }

            text_to_return = tool_result_dict.get(
                "text_output", f"Error: No text_output from tool '{name}'.")

            # Append debug log if present and if the original tool call requested debug mode
            tool_args_debug = (arguments or {}).get("debug", False)
            if tool_args_debug and "debug_log_for_text_output" in tool_result_dict:
                # debug_log_for_text_output is now expected to be a pre-formatted string
                debug_log_str = tool_result_dict["debug_log_for_text_output"]
                if debug_log_str:  # Only append if not empty
                    text_to_return += "\n\n--- Debug Log ---\n" + debug_log_str

            return [types.TextContent(type="text", text=text_to_return)]

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
