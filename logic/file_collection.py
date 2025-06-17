import sys
from pathlib import Path
from typing import List, Dict, Any

# Import from the new consolidated FFI module
from logic.ffi import invoke_scan_and_parse, invoke_project_wide_search, invoke_concept_search


def collect_and_parse_files_from_rust(
    project_path: Path, extensions: List[str], compactness_level: int, timeout: int, debug: bool = False
) -> Dict[str, Any]:
    """
    Calls the FFI layer to perform a high-speed scan.
    'timeout' is in seconds.
    """
    if debug:
        # Example of a debug log specific to this layer, if needed.
        # sys.stderr.write(f"[FileCollection] Calling invoke_scan_and_parse: path='{str(project_path)}', ext={extensions}, compact={compactness_level}, timeout_sec={timeout}\n")
        # sys.stderr.flush()
        pass

    try:
        raw_result = invoke_scan_and_parse(
            project_path=str(project_path),
            extensions=extensions,  # Pass list directly
            compactness_level=compactness_level,
            timeout_sec=timeout,    # Pass timeout in seconds
            debug=debug
        )

        # The ffi.py layer now handles initial error checking (lib load, null ptr, json decode)
        # and includes its own debug logs. We primarily process the structured result.
        if "error" in raw_result:
            # Error from FFI layer (e.g., lib not found, FFI call issue, JSON parse error)
            return {
                # Default to empty
                "file_contexts": raw_result.get("file_contexts", []),
                "debug_log": raw_result.get("debug_log", [f"Error from FFI invoke_scan_and_parse: {raw_result.get('error', 'Unknown FFI error')}"]),
                # Use status from FFI if available
                "status": raw_result.get("status", "error_ffi_call"),
                "error": raw_result.get('error', 'Unknown FFI error'),
                # FFI layer itself doesn't set this; Rust layer might.
                "timed_out": False,
                # Pass through from Rust
                "timed_out_internally": raw_result.get("timed_out_internally", False)
            }

        # If no "error" key from FFI, raw_result is the parsed JSON data from Rust.
        # It should include 'file_contexts', 'debug_log', and 'timed_out_internally'.
        timed_out_internally = raw_result.get("timed_out_internally", False)
        status = "success"
        if timed_out_internally:
            status = "success_partial_internal_timeout"
            if "files_processed_before_timeout" not in raw_result:
                # This field should ideally come from Rust if it times out internally.
                raw_result["files_processed_before_timeout"] = len(
                    raw_result.get("file_contexts", []))

        final_result = {
            # Includes file_contexts, debug_log from Rust (already merged with FFI logs)
            **raw_result,
            "status": status,
            # Overall timeout is true if Rust internally timed out
            "timed_out": timed_out_internally,
        }
        # Ensure 'error' key is not present if successful, unless Rust itself reported an error field.
        # if ffi.py didn't set it
        if status.startswith("success") and "error" in final_result and not raw_result.get("error"):
            del final_result["error"]

        return final_result

    except Exception as ex:
        # Catch-all for unexpected errors within this file_collection.py layer
        return {
            "file_contexts": [],
            "debug_log": [f"Critical error in collect_and_parse_files_from_rust: {ex}"],
            "status": "error_file_collection_critical",
            "error": str(ex),
            "timed_out": True,  # Assume timeout or related failure
            "timed_out_internally": False
        }


def search_in_files_from_rust(
    project_path: Path, search_string: str, extensions: List[str], context_lines: int, timeout: int, debug: bool = False
) -> Dict[str, Any]:
    """
    Calls the FFI layer to perform a project-wide search.
    'timeout' is in seconds.
    """
    try:
        raw_result = invoke_project_wide_search(
            project_path=str(project_path),
            search_string=search_string,
            extensions=extensions,  # Pass list directly
            context_lines=context_lines,
            timeout_sec=timeout,   # Pass timeout in seconds
            debug=debug
        )

        if "error" in raw_result:
            # Error from FFI layer
            return {
                "results": raw_result.get("results", []),  # Default to empty
                "stats": raw_result.get("stats", {}),     # Default to empty
                "debug_log": raw_result.get("debug_log", [f"Error from FFI invoke_project_wide_search: {raw_result.get('error', 'Unknown FFI error')}"]),
                "status": raw_result.get("status", "error_ffi_call"),
                "error": raw_result.get('error', 'Unknown FFI error'),
            }

        # If no "error" from FFI, raw_result is the parsed JSON from Rust.
        # It should include 'results', 'stats', 'debug_log'.
        return raw_result

    except Exception as ex:
        return {
            "results": [],
            "stats": {},
            "debug_log": [f"Critical error in search_in_files_from_rust: {ex}"],
            "status": "error_file_collection_critical",
            "error": str(ex),
        }


def concept_search_from_rust(
    project_path: Path, query: str, extensions: List[str], top_n: int, timeout: int, debug: bool = False
) -> Dict[str, Any]:
    """
    Calls the FFI layer to perform a concept search.
    'timeout' is in seconds.
    """
    fc_debug_logs: List[str] = []
    if debug:
        fc_debug_logs.append(
            f"[FileCollection | concept_search] Called. Debug: {debug}, Path: {project_path}, Query: {query[:50]}...")

    try:
        # Extensions are passed as a list; ffi.py handles JSON conversion for concept_search
        raw_result = invoke_concept_search(
            project_path=str(project_path),
            query=query,
            extensions=extensions,  # Pass list directly
            top_n=top_n,
            timeout_sec=timeout,   # Pass timeout in seconds
            debug=debug
        )

        # ffi.py's invoke_concept_search already handles merging its debug logs
        # with Rust's logs, and also the special status override logic.

        # Prepend file_collection specific logs if any
        if debug:
            existing_debug_logs = raw_result.get("debug_log", [])
            if not isinstance(existing_debug_logs, list):  # Should be a list from ffi.py
                existing_debug_logs = [
                    str(existing_debug_logs)] if existing_debug_logs is not None else []
            raw_result["debug_log"] = fc_debug_logs + existing_debug_logs

        # Check if FFI or Rust reported an error that isn't overridden to success
        if "error" in raw_result and not raw_result.get("status", "").startswith("success"):
            return {
                # Default to empty string as per original
                "results": raw_result.get("results", ""),
                "stats": raw_result.get("stats", {}),
                "debug_log": raw_result.get("debug_log", [f"Error from FFI invoke_concept_search: {raw_result.get('error', 'Unknown FFI error')}"]),
                "status": raw_result.get("status", "error_ffi_call"),
                "error": raw_result.get('error', 'Unknown FFI error'),
            }

        # If no "error" from FFI (or if it was a "success_with_rust_reported_issue"),
        # raw_result is the (potentially modified by ffi.py) data from Rust.
        return raw_result

    except Exception as ex:
        critical_error_msg = f"Critical error in concept_search_from_rust: {ex}"
        if debug:
            fc_debug_logs.append(critical_error_msg)

        return {
            "results": "",  # Default to empty string
            "stats": {},
            "debug_log": fc_debug_logs,
            "status": "error_file_collection_critical",
            "error": critical_error_msg,
        }
