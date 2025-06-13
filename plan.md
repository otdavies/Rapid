# Project Debugging Plan

## Original User Request

> Ok, so this project isn't working properly at all. When running these commands you can see it fails. The path is correct:
> 
> {
>   "path": "d:\\UnityProjects\\Soulless\\Assets\\Scripts",
>   "extensions": [
>     ".cs"
>   ],
>   "compactness_level": 1,
>   "include_descriptions": true
> }
>
> Can you write some tests and do some debugging?

## Debugging Steps

- [X] **Analyze the root cause.** The `get_full_context` tool fails on a C# project. The existing code only has parsers for Python, Rust, and JavaScript/TypeScript. The lack of a C# parser is the likely cause of the failure.
- [X] **Implement a C# parser.** Add functionality to `file_parser.py` to correctly parse `.cs` files and extract relevant information like classes, methods, and descriptions.
- [X] **Integrate the new parser.** Modify the main `parse_file` function in `file_parser.py` to use the new C# parser when a `.cs` file is encountered.
- [X] **Create a test file.** Add a new test file (`csharp_test.py`) to validate the functionality of the C# parser with a sample C# file.
- [X] **Verify the fix.** Run the test suite and confirm that the new tests pass and that no existing functionality is broken.
- [X] **Notify user.** Inform the user that C# support has been added and the issue should be resolved.

## Performance Optimizations

- [X] **Optimize file collection.** Improve performance by skipping large files (over 500KB) and non-text files to avoid unnecessary processing.

## Code Cleanup and Refactoring

- [X] **Clean up `server.py`.** Refactor the main server file for clarity and maintainability.
- [X] **Improve tool definitions.** Ensure that the MCP tool definitions are clear, accurate, and make sense.

## Rust File Scanner Enhancements

- [X] **Implement `.gitignore` handling.** Modify the Rust file scanner to find and respect the `.gitignore` file in the target project. The search for `.gitignore` should start from the root path provided and go downwards.
- [X] **Add early-out optimizations.** Introduce checks to quickly exclude irrelevant files and directories (e.g., binary files, build artifacts) to prevent the parser from wasting time on them.
- [X] **Generalize file type support.** Modify the Rust file scanner to accept a list of file extensions and process them dynamically.
- [X] **Re-implement verbosity control.** Add support for `compactness_level` to control the level of detail in the output, including function bodies and comments.

## Rust DLL Loading Refactor

- [X] **Refactor Rust DLL loading.** Modified `logic/rust_adapter.py` and `logic/file_collection.py` to remove subprocess-based DLL loading. The Rust `file_scanner.dll` is now loaded and called directly within the main Python process, ensuring it's opened and closed as needed for each scan operation. This addresses issues with the previous threaded/subprocess approach.

## Tool Enhancements

- [X] **Add debug mode to `get_full_context`.** Added an optional `debug` boolean parameter (defaults to `false`) to the `get_full_context` tool. If `true`, the `debug_log` from the Rust scanner is included in the output.

- [X] **Add project-wide search.** Implement a new `project_wide_search` tool that allows searching for a string across all files in a project, with options for context lines and file extensions.
- [X] **Refine search output.** Updated the `project_wide_search` tool to return a single, contiguous block of context with the matched line marked with `>>`. The number of context lines is now configurable.

## Project Setup
- [X] **Create `.gitignore`.** Added a `.gitignore` file to the project root to exclude common build artifacts, virtual environments, and IDE-specific files.
