# Project Context MCP Server

An MCP (Model Context Protocol) server that maintains a local database of project context for LLMs. It tracks files, function signatures, and descriptions to provide rapid context without needing to read entire projects.

## Features

- Automatic project root detection (looks for .git, package.json, Cargo.toml, etc.)
- Function signature extraction for Python, Rust, JavaScript, and TypeScript
- **Automatic description extraction from code comments**
- SQLite database for persistent context storage
- Change detection using file hashing
- Full-text search across functions and descriptions
- **Complete project overview with the new `get_full_context` tool**

## Quick Installation (Windows)

### Option 1: Automatic Setup (Recommended)
Simply double-click `INSTALL.bat` or run:
```bash
INSTALL.bat
```

### Option 2: PowerShell
Right-click `INSTALL.ps1` and select "Run with PowerShell", or:
```powershell
.\INSTALL.ps1
```

### Option 3: Manual Setup
```bash
pip install -r requirements.txt
python add_to_claude.py
```

## Usage

### Running the Server

```bash
python server.py
```

### Available Tools

1. **scan_project** - Scan project directory for code files
   - `path` (optional): Project directory path (auto-detects if not provided)
   - `extensions` (optional): File extensions to scan (default: .rs, .js, .ts, .jsx, .tsx, .py)

2. **get_file_context** - Get context about a specific file
   - `path` (required): File path relative to project root

3. **search_functions** - Search for functions by name or description
   - `query` (required): Search query

4. **get_project_overview** - Get an overview of the project structure
   - `include_stats` (optional): Include statistics about files and functions

5. **update_file_description** - Update or add a description for a file
   - `path` (required): File path relative to project root
   - `description` (required): Description of what the file does

6. **update_function_description** - Update or add a description for a function
   - `file_path` (required): File path containing the function
   - `function_name` (required): Name of the function
   - `description` (required): Description of what the function does

7. **get_full_context** - Get complete project context with all files and functions
   - `include_descriptions` (optional): Include descriptions (default: true)
   - Returns a concise overview perfect for giving LLMs rapid project understanding

## Database Schema

The server maintains a SQLite database (`project_context.db`) with:
- **files** table: Tracks file paths, hashes, descriptions, and update times
- **functions** table: Stores function names, signatures, descriptions, and line numbers

## How It Works

1. The server scans your project directory for supported file types
2. It parses each file to extract function signatures and descriptions from comments
3. File hashes are used to detect changes and avoid re-parsing unchanged files
4. All data is stored in a local SQLite database for fast retrieval
5. LLMs can query this context without reading entire files

## Enhanced Features

### Automatic Description Extraction

The server now automatically extracts descriptions from comments:

- **Python**: Module docstrings and function docstrings
- **JavaScript/TypeScript**: JSDoc comments (`/** */`) and line comments (`//`)
- **Rust**: Doc comments (`///` and `//!`)

### Complete Project Context

The new `get_full_context` tool provides a concise overview of your entire project:

```json
{
  "project_summary": {
    "total_files": 10,
    "total_functions": 45,
    "files_with_descriptions": 8,
    "functions_with_descriptions": 32
  },
  "files": [
    {
      "path": "server.py",
      "description": "MCP server for maintaining project context.",
      "functions": [
        "async def _scan_project(...): // Scan project directory for code files",
        "async def _get_full_context(...): // Get complete project context"
      ]
    }
  ]
}
```

This gives LLMs instant understanding of your project structure without reading thousands of lines of code.
