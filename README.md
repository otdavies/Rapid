![454813373-e1bbac2c-6ba0-480f-965c-d44e3f5b6f17](https://github.com/user-attachments/assets/8cfae815-341b-4b1d-a935-e12091de9307)

# R.A.P.I.D. Rapid Alignment of Project Intelligence and Documentation

RAPID is a local MCP server designed to provide powerful code analysis and search capabilities for any software project. It leverages a high-performance Rust-based file scanner to quickly parse and analyze code, exposing a set of tools that can be used by any MCP-compliant client.

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

### `initialize_project_context`

Initializes project context by reading/creating `plan.md` and provides a complexity assessment with guidance for interacting with the codebase. This should be the first tool called when starting work on a project.

**Arguments:**

-   `path` (string, required): The absolute path to the project directory.
-   `timeout` (integer, optional): Timeout in seconds for the initial scan. Default is 10.
-   `debug` (boolean, optional): Whether to include the debug log in the output. Defaults to false.

**Output Structure (Example):**
```json
{
  "status": "success",
  "plan_md_content": "# Project Plan...",
  "project_assessment": {
    "file_count": 42,
    "complexity_level": "Small",
    "guidance": "Project is small (20-75 files)..."
  },
  "stats": {
    "complexity_scan_duration_seconds": 0.05,
    "files_counted_for_complexity": 42
  }
}
```

### `get_full_code_context`

Comprehensively scans a project directory to extract and structure code from specified file types. Generates a detailed overview of the project's content, including file structures and optionally, function/class descriptions. Essential for gaining a holistic understanding of a codebase.

**Arguments:**

-   `path` (string, required): The absolute path to the project directory.
-   `extensions` (array of strings, optional): A list of file extensions to include in the scan (e.g., `[".py", ".rs"]`).
-   `max_depth` (integer, optional): The maximum depth to scan directories. Default is 6.
-   `max_files` (integer, optional): Maximum number of files to process. Default is 1000.
-   `compactness_level` (integer, optional): Controls output verbosity: 0 (ultra-compact summary), 1 (compact, default), 2 (medium detail), 3 (highly detailed with full code snippets).
-   `timeout` (integer, optional): Timeout in seconds for the operation. Default is 60.
-   `debug` (boolean, optional): Whether to include the debug log in the output. Defaults to false.


### `find_string`

Efficiently searches all files within a specified project directory for an exact string or pattern. Ideal for locating specific code snippets, configurations, or mentions across the entire codebase. Returns matches with surrounding context lines.

**Arguments:**

-   `path` (string, required): The absolute path to the project directory.
-   `search_string` (string, required): The string to search for.
-   `extensions` (array of strings, optional): A list of file extensions to search in.
-   `max_depth` (integer, optional): Maximum depth to scan directories. Default is 6.
-   `max_files` (integer, optional): Maximum number of files to process. Default is 1000.
-   `context_lines` (integer, optional): The number of context lines to include around each match. Default is 2.
-   `timeout` (integer, optional): Timeout in seconds for the operation. Default is 60.
-   `debug` (boolean, optional): Whether to include the debug log in the output. Defaults to false.

### `find_code_by_concept`

Performs a powerful semantic search across the codebase to find functions or code blocks related to a natural language query. Instead of exact string matching, it understands the *intent* behind the query to locate relevant functionality. Useful for discovering how specific concepts are implemented or finding code when you don't know the exact names or terms.

**Arguments:**

-   `path` (string, required): The absolute path to the project directory.
-   `query` (string, required): A natural language description of the functionality or concept you are searching for (e.g., "how user authentication is handled").
-   `extensions` (array of strings, optional): File extensions to scan. Defaults to common code extensions.
-   `top_n` (integer, optional): Number of top results to return. Default is 10.
-   `timeout` (integer, optional): Timeout in seconds for the operation. Default is 20.
-   `debug` (boolean, optional): Whether to include the debug log in the output. Defaults to false.

## Getting Started

This guide provides step-by-step instructions to get the R.A.P.I.D. server up and running on your local machine.

### Prerequisites

Before you proceed, make sure you have the following software installed:

-   **Git:** For cloning the source code. You can download it from [git-scm.com](https://git-scm.com/).
-   **Python (3.8+):** The core server is written in Python. You can get it from [python.org](https://www.python.org/).
-   **Rust:** The high-performance file scanner is built with Rust. The recommended installation method is `rustup` from [rust-lang.org](https://www.rust-lang.org/tools/install).

### Installation Steps

1.  **Clone the Repository**

    Open your terminal, navigate to your desired directory, and clone the repository:
    ```bash
    git clone https://github.com/otdavies/Rapid.git
    cd Rapid
    ```

2.  **Set Up Python Environment**

    It's best practice to use a virtual environment to avoid conflicts with other projects.

    ```bash
    # Create a virtual environment
    python -m venv venv

    # Activate it
    # On Windows:
    # venv\Scripts\activate
    # On macOS/Linux:
    # source venv/bin/activate

    # Install dependencies
    pip install -r requirements.txt
    ```

3.  **Build the Rust Scanner**

    Compile the Rust library, which handles the file scanning and parsing.

    ```bash
    cd file_scanner
    cargo build --release
    cd ..
    ```

    Once these steps are complete, the server is ready to be configured with your client.

## Client Configuration

To use this server, you need to register it with your MCP-compliant client (e.g., an AI assistant in your IDE). This typically involves adding a configuration block to the client's settings file.

Locate your MCP client's configuration file (often a `settings.json` or similar) and add the following entry to the `mcpServers` object. Make sure to replace `"your-path-here\\server.py"` with the absolute path to the `server.py` file in this project.

```json
"mcpServers": {
    "project-context": {
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
