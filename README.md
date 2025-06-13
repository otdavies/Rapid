# RAPID: Relational Abstract Programmatic Insight Discovery

RAPID (Relational Abstract Programmatic Insight Discovery) is a local MCP server designed to provide powerful code analysis and search capabilities for any software project. It leverages a high-performance Rust-based file scanner to quickly parse and analyze code, exposing a set of tools that can be used by any MCP-compliant client.

This server is ideal for AI assistants and development tools that need to understand the context of a codebase to perform tasks like code generation, refactoring, and automated documentation.

## Features

- **Full Project Context Analysis:** Recursively scans a project directory to extract information about files, functions, and classes.
- **Project-Wide Search:** Performs fast, project-wide searches for specific strings or patterns.
- **Multi-Language Support:** Includes parsers for Python, Rust, C#, and TypeScript/JavaScript.
- **High-Performance Rust Core:** The file scanning and parsing logic is implemented in Rust for maximum performance and efficiency.
- **Configurable:** Allows for customization of scanning depth, file extensions, and output verbosity.
- **MCP Compliant:** Exposes its functionality through a set of well-defined MCP tools.

## Architecture

The server is composed of two main components:

1.  **Python MCP Server (`server.py`):** The main entry point of the server. It handles MCP requests, defines the available tools, and orchestrates the code analysis process.
2.  **Rust File Scanner (`file_scanner/`):** A Rust library that performs the heavy lifting of file system scanning, parsing, and search. It is called by the Python server through a C FFI layer.

This hybrid approach combines the flexibility of Python for the server logic with the performance of Rust for the CPU-intensive file processing tasks.

## Tools

The server exposes the following tools:

### `get_full_context`

Scans a project directory and returns a structured overview of the codebase.

**Arguments:**

-   `path` (string, required): The absolute path to the project directory.
-   `extensions` (array of strings, optional): A list of file extensions to include in the scan.
-   `max_depth` (integer, optional): The maximum depth to scan directories.
-   `compactness_level` (integer, optional): Controls the verbosity of the output.

### `project_wide_search`

Performs a project-wide search for a given string.

**Arguments:**

-   `path` (string, required): The absolute path to the project directory.
-   `search_string` (string, required): The string to search for.
-   `extensions` (array of strings, optional): A list of file extensions to search in.
-   `context_lines` (integer, optional): The number of context lines to include in the search results.

## Getting Started

1.  **Install Dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

2.  **Build the Rust Scanner:**
    ```bash
    cd file_scanner
    cargo build --release
    cd ..
    ```

3.  **Run the Server:**
    ```bash
    python server.py
    ```

The server will start and be available for any MCP-compliant client to connect to.

## Installation

To use this server with an MCP-compliant client, you need to add the following configuration to your client's settings:

```json
"mcpServers": {
    "project-context": {
      "autoApprove": [
        "clear_project_context_database",
        "get_project_overview",
        "search_functions",
        "get_file_context",
        "scan_project",
        "get_context",
        "get_full_context"
      ],
      "disabled": false,
      "timeout": 30,
      "type": "stdio",
      "command": "python",
      "args": [
        "your-path-here\\server.py"
      ],
      "env": {}
    }
}
```
