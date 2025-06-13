import json
import sys  # Keep for sys.stderr if any debug prints are desired, otherwise remove
from pathlib import Path
from typing import List, Dict, Any

# Import the new direct invocation function
from logic.rust_adapter import invoke_rust_scanner, invoke_rust_searcher, invoke_rust_concept_searcher


def collect_and_parse_files_from_rust(
    project_path: Path, extensions: List[str], compactness_level: int, timeout: int
) -> Dict[str, Any]:
    """
    Calls the Rust library directly to perform a high-speed scan.
    """
    timeout_rust_ms = timeout * 1000

    # Prepare arguments for the direct call
    project_path_str = str(project_path)
    extensions_str = ",".join(extensions)

    # sys.stderr.write(
    #     f"[FileCollection] Direct Call: Calling invoke_rust_scanner with path='{project_path_str}', "
    #     f"ext='{extensions_str}', compact={compactness_level}, timeout_ms={timeout_rust_ms}\n"
    # )
    # sys.stderr.flush()

    try:
        # Direct call to the refactored rust_adapter function
        raw_result = invoke_rust_scanner(
            project_path_str=project_path_str,
            extensions_str=extensions_str,
            compactness_level=compactness_level,
            timeout_ms=timeout_rust_ms
        )

        # Process the result from invoke_rust_scanner
        # invoke_rust_scanner returns a dict, which might be an error dict or the parsed JSON from Rust.

        if "error" in raw_result:
            # This means invoke_rust_scanner itself had an error (e.g., DLL not found, load error, JSON parse error from Rust output)
            return {
                # Should be empty on error
                "file_contexts": raw_result.get("file_contexts", []),
                "debug_log": raw_result.get("debug_log", [f"Error from invoke_rust_scanner: {raw_result['error']}"]),
                "status": "error_adapter_call",  # General error status for adapter issues
                "error": raw_result['error'],
                "timed_out": False,  # This specific error is not a timeout of the scan itself
                "timed_out_internally": False
            }

        # If no "error" key, raw_result is the parsed JSON data from the Rust library
        # The Rust library's output structure is expected here.
        # It should include 'file_contexts', 'debug_log', and potentially 'timed_out_internally'.

        file_contexts = raw_result.get("file_contexts", [])
        debug_log = raw_result.get("debug_log", [])

        # Check if the Rust library reported an internal timeout
        timed_out_internally = raw_result.get("timed_out_internally", False)

        status = "success"
        if timed_out_internally:
            status = "success_partial_internal_timeout"
            # If Rust timed out, it should also provide files_processed_before_timeout
            # This key needs to be consistent with what tool_implementations.py expects
            # Add it to raw_result if not already there, or ensure it's named correctly.
            if "files_processed_before_timeout" not in raw_result:
                # If Rust doesn't provide this, we might infer it from len(file_contexts)
                # but it's better if Rust provides it. For now, assume it might be missing.
                raw_result["files_processed_before_timeout"] = len(
                    file_contexts)

        # The overall 'timed_out' flag for collect_and_parse_files_from_rust
        # will be true if the Rust library itself reported an internal timeout.
        # There's no longer a separate Python-level "external" timeout for the subprocess.
        final_timed_out_flag = timed_out_internally

        # Construct the final dictionary to be returned, ensuring all expected keys by tool_implementations.py are present.
        # Merge raw_result (which is the data from Rust) with our status and timeout flags.
        final_result = {
            **raw_result,  # This includes file_contexts, debug_log, and any Rust-specific fields
            "status": status,
            "timed_out": final_timed_out_flag,  # True if Rust internally timed out
            "timed_out_internally": timed_out_internally  # Explicitly from Rust
        }
        # Ensure 'error' key is not present if successful
        if "error" in final_result and status.startswith("success"):
            del final_result["error"]

        return final_result

    except Exception as ex:
        # Catch-all for unexpected errors during the direct call to invoke_rust_scanner
        # or during the processing of its result.
        return {
            "file_contexts": [],
            "debug_log": [f"Critical error in collect_and_parse_files_from_rust (direct call): {ex}"],
            "status": "error_file_collection_critical",
            "error": str(ex),
            # Assume a critical failure might be related to timeout or causes one effectively
            "timed_out": True,
            "timed_out_internally": False  # Cannot determine this if Python code fails
        }


def search_in_files_from_rust(
    project_path: Path, search_string: str, extensions: List[str], context_lines: int, timeout: int
) -> Dict[str, Any]:
    """
    Calls the Rust library to perform a project-wide search.
    """
    timeout_rust_ms = timeout * 1000
    project_path_str = str(project_path)
    extensions_str = ",".join(extensions)

    try:
        raw_result = invoke_rust_searcher(
            project_path_str=project_path_str,
            search_string=search_string,
            extensions_str=extensions_str,
            context_lines=context_lines,
            timeout_ms=timeout_rust_ms
        )

        if "error" in raw_result:
            return {
                "status": "error_adapter_call",
                "error": raw_result['error'],
                "results": [],
                "stats": {}
            }

        return raw_result

    except Exception as ex:
        return {
            "status": "error_file_collection_critical",
            "error": str(ex),
            "results": [],
            "stats": {}
        }


def concept_search_from_rust(
    project_path: Path, query: str, extensions: List[str], top_n: int, timeout: int
) -> Dict[str, Any]:
    """
    Calls the Rust library to perform a concept search.
    """
    timeout_rust_ms = timeout * 1000
    project_path_str = str(project_path)
    extensions_str = ",".join(extensions)

    try:
        raw_result = invoke_rust_concept_searcher(
            project_path_str=project_path_str,
            query_str=query,
            extensions_str=extensions_str,
            top_n=top_n,
            timeout_ms=timeout_rust_ms
        )

        if "error" in raw_result:
            return {
                "status": "error_adapter_call",
                "error": raw_result['error'],
                "results": [],
                "stats": {}
            }

        return raw_result

    except Exception as ex:
        return {
            "status": "error_file_collection_critical",
            "error": str(ex),
            "results": [],
            "stats": {}
        }
