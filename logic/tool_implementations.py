import time
from pathlib import Path
from typing import Any, Dict, List

from logic.file_collection import collect_and_parse_files_from_rust, search_in_files_from_rust, concept_search_from_rust
from logic.context_processing import format_project_context, format_search_results, format_concept_search_results


async def get_full_context_impl(args: Dict[str, Any]) -> Dict[str, Any]:
    """Implementation of the get_full_context tool, now powered by Rust."""
    input_path_str = args["path"]

    project_path = Path(input_path_str)
    if not project_path.is_absolute():
        return {"status": "error", "error": f"Path '{input_path_str}' must be an absolute path."}

    # Default timeout for the overall operation, passed to file_collection
    timeout_seconds = args.get("timeout", 10)
    compactness_level = args.get("compactness_level", 1)
    include_descriptions = args.get("include_descriptions", True)
    extensions = args.get("extensions", [".cs", ".py", ".rs", ".js", ".ts"])
    debug_mode = args.get("debug", False)  # Get the new debug flag

    try:
        if not project_path.exists() or not project_path.is_dir():
            return {"status": "error", "error": f"Project path '{input_path_str}' not found or not a directory"}
    except Exception as e:
        return {"status": "error", "error": f"Invalid project path: {e}"}

    stats: Dict[str, Any] = {'scanned_files': 0,
                             'total_functions': 0, 'timed_out': False}
    debug_log: List[str] = []
    file_contexts: List[Dict[str, Any]] = []

    overall_start_time = time.time()

    try:
        rust_result = collect_and_parse_files_from_rust(
            project_path, extensions, compactness_level, timeout_seconds, debug_mode
        )

        file_contexts = rust_result.get("file_contexts", [])
        debug_log = rust_result.get("debug_log", [])

        is_timed_out_externally = rust_result.get("timed_out", False)
        is_timed_out_internally = rust_result.get(
            "timed_out_internally", False)

        stats['timed_out'] = is_timed_out_externally or is_timed_out_internally
        # For more detailed stats
        stats['timed_out_internally'] = is_timed_out_internally

        # Determine status based on rust_result
        # rust_result["status"] can be "error_ffi_call", "success_partial_internal_timeout", etc.
        # or a simple "error" if something else went wrong in file_collection.
        # Default to success if no status
        final_status = rust_result.get("status", "success")

        # Covers "error", "error_ffi_call", "error_file_collection_critical"
        if "error" in final_status or final_status.startswith("error_"):
            # Unreliable if FFI error or other error in collection layer
            stats['scanned_files'] = 0  # Default if error
            if is_timed_out_internally:  # If Rust also timed out, its count is more relevant
                stats['scanned_files'] = rust_result.get(
                    "files_processed_before_timeout", 0)

            # Ensure the final return reflects this error
            duration = time.time() - overall_start_time
            stats["scan_duration_seconds"] = round(duration, 2)
            return {
                "status": final_status,  # Propagate status from file_collection
                "error": rust_result.get("error", "Processing error or timeout in FFI/collection layer."),
                "context": "",
                "stats": stats,
                "debug_log": debug_log
            }

        # If status was "success_partial_internal_timeout" or just "success"
        if is_timed_out_internally:
            stats['scanned_files'] = rust_result.get(
                "files_processed_before_timeout", 0)
            final_status = "success_partial_internal_timeout"  # Ensure status reflects this
        else:  # Not timed out internally, and not an error from file_collection
            stats['scanned_files'] = len(file_contexts)
            # final_status remains "success"

        stats['total_functions'] = sum(
            len(c.get('functions', [])) for c in file_contexts)

    except Exception as e:
        duration = time.time() - overall_start_time
        stats["scan_duration_seconds"] = round(duration, 2)
        stats["timed_out"] = True  # Assume timeout or critical failure
        # Ensure debug_log is a list
        current_debug_log = debug_log if 'debug_log' in locals(
        ) and isinstance(debug_log, list) else []
        current_debug_log.append(
            f"Critical error in get_full_context_impl: {e}")
        return {
            "status": "error",
            "error": f"Critical scan failed in tool_implementations: {e}",
            "context": "",
            "stats": stats,
            "debug_log": current_debug_log
        }

    formatted_context = format_project_context(
        file_contexts, compactness_level, include_descriptions
    )
    duration = time.time() - overall_start_time

    # Final stats structure
    final_stats = {
        "files_processed": stats['scanned_files'],
        "total_functions": stats.get('total_functions', 0),  # Ensure it exists
        "scan_duration_seconds": round(duration, 2),
        "timed_out": stats.get('timed_out', False),
        "timed_out_internally": stats.get('timed_out_internally', False),
    }
    if is_timed_out_internally:  # Add this if Rust timed out, for more info
        final_stats["files_attempted_by_rust"] = rust_result.get(
            "files_processed_before_timeout", 0)

    response = {
        "status": final_status,
        "context": formatted_context,
        "stats": final_stats,
    }
    if debug_mode:
        response["debug_log"] = debug_log

    return response


async def project_wide_search_impl(args: Dict[str, Any]) -> Dict[str, Any]:
    """Implementation of the project_wide_search tool."""
    input_path_str = args["path"]
    search_string = args["search_string"]

    project_path = Path(input_path_str)
    if not project_path.is_absolute():
        return {"status": "error", "error": f"Path '{input_path_str}' must be an absolute path."}

    timeout_seconds = args.get("timeout", 10)
    extensions = args.get("extensions", [".cs", ".py", ".rs", ".js", ".ts"])
    context_lines = args.get("context_lines", 2)
    debug_mode = args.get("debug", False)

    try:
        if not project_path.exists() or not project_path.is_dir():
            return {"status": "error", "error": f"Project path '{input_path_str}' not found or not a directory"}
    except Exception as e:
        return {"status": "error", "error": f"Invalid project path: {e}"}

    start_time = time.time()

    try:
        rust_result = search_in_files_from_rust(
            project_path, search_string, extensions, context_lines, timeout_seconds, debug_mode
        )

        duration = time.time() - start_time

        formatted_results = format_search_results(rust_result)

        final_stats = rust_result.get("stats", {})
        final_stats["search_duration_seconds"] = round(duration, 2)

        response = {
            "status": "success",
            "results": formatted_results,
            "stats": final_stats,
        }

        if debug_mode:
            response["debug_log"] = rust_result.get("debug_log", [])

        return response

    except Exception as e:
        duration = time.time() - start_time
        return {
            "status": "error",
            "error": f"Critical search failed in tool_implementations: {e}",
            "stats": {"search_duration_seconds": round(duration, 2)}
        }


async def concept_search_impl(args: Dict[str, Any]) -> Dict[str, Any]:
    """Implementation of the concept_search tool."""
    input_path_str = args["path"]
    query = args["query"]
    project_path = Path(input_path_str)
    all_debug_logs: List[str] = []

    # Get debug_mode early to use for all logging and decisions
    debug_mode = args.get("debug", False)

    if debug_mode:
        all_debug_logs.append(
            f"[PY_TOOL_IMPL | concept_search_impl] Received args: {args}")
        all_debug_logs.append(
            f"[PY_TOOL_IMPL | concept_search_impl] Parsed debug_mode: {debug_mode}")
        all_debug_logs.append(
            f"[PY_TOOL_IMPL | concept_search_impl] Type of 'debug' in args: {type(args.get('debug'))}, Value: {args.get('debug')}")

    if not project_path.is_absolute():
        error_msg = f"Path '{input_path_str}' must be an absolute path."
        if debug_mode:
            all_debug_logs.append(
                f"[PY_TOOL_IMPL | concept_search_impl] Error: {error_msg}")
            return {"status": "error", "error": error_msg, "debug_log": all_debug_logs}
        return {"status": "error", "error": error_msg}

    timeout_seconds = args.get("timeout", 20)
    extensions = args.get("extensions", [".cs", ".py", ".rs", ".js", ".ts"])
    top_n = args.get("top_n", 10)

    try:
        if not project_path.exists() or not project_path.is_dir():
            error_msg = f"Project path '{input_path_str}' not found or not a directory"
            if debug_mode:
                all_debug_logs.append(
                    f"[PY_TOOL_IMPL | concept_search_impl] Error: {error_msg}")
                return {"status": "error", "error": error_msg, "debug_log": all_debug_logs}
            return {"status": "error", "error": error_msg}
    except Exception as e:
        error_msg = f"Invalid project path: {e}"
        if debug_mode:
            all_debug_logs.append(
                f"[PY_TOOL_IMPL | concept_search_impl] Error: {error_msg}")
            return {"status": "error", "error": error_msg, "debug_log": all_debug_logs}
        return {"status": "error", "error": error_msg}

    start_time = time.time()

    try:
        if debug_mode:
            all_debug_logs.append(
                f"[PY_TOOL_IMPL | concept_search_impl] Calling concept_search_from_rust with: "
                f"project_path='{project_path}', query='{query[:50]}...', extensions={extensions}, "
                f"top_n={top_n}, timeout_seconds={timeout_seconds}, debug_mode={debug_mode}"
            )

        rust_result = concept_search_from_rust(
            project_path, query, extensions, top_n, timeout_seconds, debug_mode
        )

        if debug_mode:
            # Log a summary of what was received from the lower layer
            rust_debug_log_summary = rust_result.get("debug_log", [])
            all_debug_logs.append(
                f"[PY_TOOL_IMPL | concept_search_impl] Received from concept_search_from_rust: "
                f"status='{rust_result.get('status', 'N/A')}', "
                f"error='{rust_result.get('error', 'N/A')}', "
                f"results_type='{type(rust_result.get('results')).__name__}', "
                f"num_results={len(rust_result.get('results', [])) if isinstance(rust_result.get('results'), list) else 'N/A'}, "
                f"num_debug_logs_from_rust={len(rust_debug_log_summary)}"
            )

        # Aggregate logs from lower layer
        all_debug_logs.extend(rust_result.get("debug_log", []))

        duration = time.time() - start_time

        # Check for errors reported by file_collection.py (which includes errors from ffi.py and Rust)
        # The ffi.py layer and file_collection.py already try to set a meaningful status.
        status_from_collection = rust_result.get("status", "success")
        if "error" in status_from_collection or status_from_collection.startswith("error_"):
            error_msg = rust_result.get(
                "error", "Unknown error from concept search process.")
            error_response = {"status": status_from_collection,  # Use the status from file_collection
                              "error": error_msg,
                              # Preserve partial results if any
                              "results": rust_result.get("results", ""),
                              "stats": rust_result.get("stats", {})}
            if debug_mode:
                all_debug_logs.append(
                    f"[PY_TOOL_IMPL | concept_search_impl] Error from file_collection: {error_msg} (status: {status_from_collection})")
                error_response["debug_log"] = all_debug_logs
            return error_response

        formatted_results = format_concept_search_results(rust_result)
        if debug_mode:
            # Log a snippet of formatted results to check for emptiness
            formatted_results_str = str(formatted_results)
            all_debug_logs.append(
                f"[PY_TOOL_IMPL | concept_search_impl] Formatted results (first 200 chars): {formatted_results_str[:200]}"
            )
            # If formatted is empty but original had results
            if not formatted_results_str and rust_result.get('results'):
                all_debug_logs.append(
                    f"[PY_TOOL_IMPL | concept_search_impl] WARNING: Formatted results are empty, but rust_result had results. Rust result keys: {list(rust_result.keys())}"
                )

        final_stats = rust_result.get("stats", {})
        final_stats["search_duration_seconds"] = round(duration, 2)

        response = {
            # Propagate status from rust_result
            "status": rust_result.get("status", "success"),
            "results": formatted_results,
            "stats": final_stats,
        }

        if debug_mode:
            response["debug_log"] = all_debug_logs

        return response

    except Exception as e:
        duration = time.time() - start_time
        critical_error_msg = f"Critical concept search failed in tool_implementations: {e}"

        if debug_mode:
            all_debug_logs.append(
                f"[PY_TOOL_IMPL | concept_search_impl] Critical error: {critical_error_msg}"
            )

        error_response = {
            "status": "error",
            "error": critical_error_msg,
            "stats": {"search_duration_seconds": round(duration, 2)},
        }
        if debug_mode:
            error_response["debug_log"] = all_debug_logs

        return error_response
