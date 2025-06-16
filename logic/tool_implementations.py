import time
import os
from pathlib import Path
from typing import Any, Dict, List

from logic.file_collection import collect_and_parse_files_from_rust, search_in_files_from_rust, concept_search_from_rust
from logic.context_processing import format_project_context, format_search_results, format_concept_search_results

PLAN_MD_FILENAME = "plan.md"
DEFAULT_PLAN_MD_CONTENT = """# Project Plan

This plan.md file was automatically created.
Please populate this file with the project goals, architecture decisions, and task breakdown.
This will help the AI assistant understand the project context.

[ ] Initial project setup
"""


def _format_stats_for_text_output(stats_dict: Dict[str, Any], title: str = "Stats") -> str:
    """Helper function to format a dictionary of stats into a readable string."""
    if not stats_dict:
        return ""
    lines = [f"\n--- {title} ---"]
    for key, value in stats_dict.items():
        # Try to format numbers nicely
        if isinstance(value, float):
            value_str = f"{value:.2f}"
        else:
            value_str = str(value)
        lines.append(f"{key.replace('_', ' ').capitalize()}: {value_str}")
    return "\n".join(lines)

# Return type will be string effectively, but server.py handles JSON wrapping


async def initialize_project_context_impl(args: Dict[str, Any]) -> Dict[str, Any]:
    """
    Initializes project context by reading/creating plan.md and provides a complexity assessment.
    Output is formatted as a plain text string.
    """
    input_path_str = args["path"]
    project_path = Path(input_path_str)
    debug_mode = args.get("debug", False)
    # Timeout for the lightweight scan
    timeout_seconds = args.get("timeout", 10)

    response_stats = {}
    # Renamed to avoid conflict if debug_mode is true
    debug_log_internal: List[str] = []

    # Path validation
    if not project_path.is_absolute():
        error_output_str = f"--- Error ---\nPath '{input_path_str}' must be an absolute path."
        return {"status": "error_text_output", "text_output": error_output_str}

    try:
        if not project_path.exists() or not project_path.is_dir():
            error_output_str = f"--- Error ---\nProject path '{input_path_str}' not found or not a directory"
            return {"status": "error_text_output", "text_output": error_output_str}
    except Exception as e:
        error_output_str = f"--- Error ---\nInvalid project path: {e}"
        return {"status": "error_text_output", "text_output": error_output_str}

    # 1. Handle plan.md
    plan_md_content = ""
    plan_md_path = project_path / PLAN_MD_FILENAME
    try:
        if plan_md_path.exists():
            with open(plan_md_path, "r", encoding="utf-8") as f:
                plan_md_content = f.read()
            if debug_mode:
                debug_log_internal.append(f"Read existing {PLAN_MD_FILENAME}")
        else:
            with open(plan_md_path, "w", encoding="utf-8") as f:
                f.write(DEFAULT_PLAN_MD_CONTENT)
            plan_md_content = DEFAULT_PLAN_MD_CONTENT
            if debug_mode:
                debug_log_internal.append(f"Created new {PLAN_MD_FILENAME}")
    except Exception as e:
        error_message = f"Error handling {PLAN_MD_FILENAME}: {e}"
        if debug_mode:
            debug_log_internal.append(error_message)
        plan_md_content = f"[Error reading/writing {PLAN_MD_FILENAME}: {e}]"

    # 2. Project Complexity Assessment (Lightweight Scan)
    file_count = 0
    complexity_level = "Unknown"
    guidance = "Could not determine project complexity due to an issue."
    scan_start_time = time.time()
    scan_successful = False
    rust_call_error_message = ""

    try:
        rust_scan_args = {
            "project_path": project_path,
            "extensions": [".cs", ".py", ".rs", ".js", ".ts", ".json", ".md", ".txt", ".html", ".css"],
            "compactness_level": 0,
            "timeout": timeout_seconds,
            "debug": debug_mode
        }
        if debug_mode:
            debug_log_internal.append(
                f"Calling collect_and_parse_files_from_rust for complexity assessment with args: {rust_scan_args}")

        rust_result = collect_and_parse_files_from_rust(
            project_path,
            rust_scan_args["extensions"],
            rust_scan_args["compactness_level"],
            rust_scan_args["timeout"],
            rust_scan_args["debug"]
        )

        if debug_mode:
            debug_log_internal.append(
                f"Rust scan result for complexity: {str(rust_result)[:500]}...")
            if rust_result.get("debug_log"):
                debug_log_internal.extend(rust_result.get("debug_log", []))

        if "error" in rust_result.get("status", "") or rust_result.get("status") == "error":
            rust_call_error_message = rust_result.get(
                'error', 'Unknown scan error')
            guidance = f"Error during project scan for complexity: {rust_call_error_message}"
            if debug_mode:
                debug_log_internal.append(guidance)
        else:
            scan_successful = True
            if "stats" in rust_result and "files_processed" in rust_result["stats"]:
                file_count = rust_result["stats"]["files_processed"]
            elif "file_contexts" in rust_result:
                file_count = len(rust_result.get("file_contexts", []))

            if file_count < 10:
                complexity_level = "Trivial"
                guidance = "Project is trivial (less than 10 files). Direct file examination and `get_full_code_context` (low compactness) are likely sufficient for understanding."
            elif file_count < 30:
                complexity_level = "Small"
                guidance = "Project is small (10-29 files). Use `get_full_code_context` for an overview. `find_string` can be useful for targeted searches."
            elif file_count < 150:
                complexity_level = "Medium"
                guidance = "Project is medium-sized (30-149 files). Rely on `get_full_code_context` for initial understanding. Prioritize `find_string` and `find_code_by_concept` to locate relevant areas before reading files extensively."
            else:
                complexity_level = "Large"
                guidance = "Project is large (150+ files). Heavily prioritize `find_code_by_concept` and `find_string` for navigation. Use `get_full_code_context` selectively, possibly on subdirectories, or with higher compactness levels to manage output size. Avoid reading files without a clear target."
            if debug_mode:
                debug_log_internal.append(
                    f"Determined complexity: {complexity_level} with {file_count} files.")

    except Exception as e:
        rust_call_error_message = f"Exception during project scan for complexity: {e}"
        guidance = rust_call_error_message
        if debug_mode:
            debug_log_internal.append(str(e))

    scan_duration = time.time() - scan_start_time
    response_stats["complexity_scan_duration_seconds"] = scan_duration
    response_stats["files_counted_for_complexity"] = file_count if scan_successful else "N/A"

    output_lines = [
        "--- Plan.md Content ---",
        plan_md_content if plan_md_content else "plan.md not found or empty.",
        "\n--- Project Assessment ---",
        f"File Count: {file_count if scan_successful else 'Error during scan'}",
        f"Complexity Level: {complexity_level}",
        f"Guidance: {guidance}",
    ]
    output_lines.append(_format_stats_for_text_output(
        response_stats, "Initialization Stats"))

    plain_text_output = "\n".join(output_lines)

    current_status = "success_text_output"
    if not scan_successful and rust_call_error_message:
        current_status = "error_text_output"  # If scan failed, overall status is error
    elif not scan_successful:  # Generic scan issue without specific error message from rust_result
        # e.g. plan.md worked but scan had Python side exception
        current_status = "partial_text_output"

    final_tool_result = {
        "status": current_status,
        "text_output": plain_text_output
    }

    if debug_mode:
        final_tool_result["debug_log_for_text_output"] = "\n".join(
            debug_log_internal)
    return final_tool_result


async def get_full_context_impl(args: Dict[str, Any]) -> Dict[str, Any]:
    input_path_str = args["path"]
    project_path = Path(input_path_str)
    debug_mode = args.get("debug", False)
    timeout_seconds = args.get("timeout", 10)
    compactness_level = args.get("compactness_level", 1)
    extensions = args.get("extensions", [".cs", ".py", ".rs", ".js", ".ts"])

    debug_log_internal: List[str] = []

    if not project_path.is_absolute():
        return {"status": "error_text_output", "text_output": f"--- Error ---\nPath '{input_path_str}' must be an absolute path."}

    try:
        if not project_path.exists() or not project_path.is_dir():
            return {"status": "error_text_output", "text_output": f"--- Error ---\nProject path '{input_path_str}' not found or not a directory"}
    except Exception as e:
        return {"status": "error_text_output", "text_output": f"--- Error ---\nInvalid project path: {e}"}

    overall_start_time = time.time()
    text_output_parts = []
    final_status_str = "error_text_output"  # Default to error
    final_stats = {}

    try:
        rust_result = collect_and_parse_files_from_rust(
            project_path, extensions, compactness_level, timeout_seconds, debug_mode
        )

        if debug_mode:
            debug_log_internal.append(
                f"Rust result from collect_and_parse_files_from_rust: {str(rust_result)[:500]}...")
            if rust_result.get("debug_log"):
                debug_log_internal.extend(rust_result.get("debug_log", []))

        file_contexts = rust_result.get("file_contexts", [])
        # final_stats needs to be accessed early for the safety rail
        final_stats = rust_result.get("stats", {})

        # Safety rail for large projects (over 150 files)
        files_processed = final_stats.get("files_processed")
        # Ensure files_processed is an integer before comparison
        if isinstance(files_processed, int) and files_processed > 150:
            final_status_str = "success_text_output"
            guidance_message = (
                f"Project contains {files_processed} files. This exceeds the 150 file limit for a full context display.\n"
                "To efficiently navigate and understand this large codebase, please use the 'find_string' or 'find_code_by_concept' tools.\n"
                "Listing all file contents would be too verbose and consume excessive resources."
            )
            text_output_parts.append(guidance_message)

            # Calculate overall_scan_duration_seconds for this early return path
            current_time = time.time()
            final_stats['overall_scan_duration_seconds'] = current_time - \
                overall_start_time

            text_output_parts.append(
                _format_stats_for_text_output(final_stats, "Scan Stats"))

            result_dict = {
                "status": final_status_str,
                "text_output": "\n".join(text_output_parts)
            }
            if debug_mode:
                result_dict["debug_log_for_text_output"] = "\n".join(
                    debug_log_internal)
            return result_dict
        # End of safety rail

        # Map Rust status to text output status
        rust_status = rust_result.get("status", "success")
        if rust_status == "success":
            final_status_str = "success_text_output"
        elif rust_status == "success_partial_internal_timeout":
            final_status_str = "partial_text_output"
            text_output_parts.append(
                "[Warning: Scan timed out internally, results may be incomplete.]\n")
        elif "error" in rust_status:
            final_status_str = "error_text_output"
            text_output_parts.append(
                f"--- Error during scan ---\n{rust_result.get('error', 'Unknown error from Rust layer.')}\n")

        formatted_context = format_project_context(
            project_path, file_contexts, compactness_level)  # Added project_path
        text_output_parts.append(
            formatted_context if formatted_context else "No processable files found or an error occurred.")

        # Stats from Rust result if available, otherwise calculate
        # final_stats is already initialized above
        # Fallback if Rust stats are missing (e.g. if rust_result.get("stats") was empty)
        if not final_stats:
            final_stats['files_processed'] = len(file_contexts)
            final_stats['total_functions'] = sum(
                len(c.get('functions', [])) for c in file_contexts)

        # Ensure files_processed is in final_stats if it wasn't from rust_result.get("stats")
        if 'files_processed' not in final_stats:
            final_stats['files_processed'] = len(file_contexts)

        final_stats['timed_out_internally'] = rust_result.get(
            'timed_out_internally', False)
        # overall_scan_duration_seconds is now calculated earlier if the safety rail is hit,
        # otherwise calculate it here for the normal path.
        if 'overall_scan_duration_seconds' not in final_stats:
            final_stats['overall_scan_duration_seconds'] = time.time() - \
                overall_start_time

        text_output_parts.append(
            _format_stats_for_text_output(final_stats, "Scan Stats"))

    except Exception as e:
        final_status_str = "error_text_output"
        text_output_parts.append(
            f"--- Critical Error in Python Layer ---\n{e}")
        if debug_mode:
            debug_log_internal.append(
                f"Critical error in get_full_context_impl: {e}")
        final_stats['overall_scan_duration_seconds'] = time.time() - \
            overall_start_time
        text_output_parts.append(_format_stats_for_text_output(
            final_stats, "Scan Stats (incomplete)"))

    result_dict = {
        "status": final_status_str,
        "text_output": "\n".join(text_output_parts)
    }
    if debug_mode:
        result_dict["debug_log_for_text_output"] = "\n".join(
            debug_log_internal)
    return result_dict


async def project_wide_search_impl(args: Dict[str, Any]) -> Dict[str, Any]:
    input_path_str = args["path"]
    search_string = args["search_string"]
    project_path = Path(input_path_str)
    debug_mode = args.get("debug", False)
    timeout_seconds = args.get("timeout", 10)
    extensions = args.get("extensions", [".cs", ".py", ".rs", ".js", ".ts"])
    context_lines = args.get("context_lines", 2)

    debug_log_internal: List[str] = []
    text_output_parts = []
    final_status_str = "error_text_output"
    final_stats = {}

    if not project_path.is_absolute():
        return {"status": "error_text_output", "text_output": f"--- Error ---\nPath '{input_path_str}' must be an absolute path."}
    try:
        if not project_path.exists() or not project_path.is_dir():
            return {"status": "error_text_output", "text_output": f"--- Error ---\nProject path '{input_path_str}' not found or not a directory"}
    except Exception as e:
        return {"status": "error_text_output", "text_output": f"--- Error ---\nInvalid project path: {e}"}

    start_time = time.time()
    try:
        rust_result = search_in_files_from_rust(
            project_path, search_string, extensions, context_lines, timeout_seconds, debug_mode
        )
        if debug_mode:
            debug_log_internal.append(
                f"Rust result from search_in_files_from_rust: {str(rust_result)[:500]}...")
            if rust_result.get("debug_log"):
                debug_log_internal.extend(rust_result.get("debug_log", []))

        rust_status = rust_result.get("status", "success")
        if rust_status == "success":
            final_status_str = "success_text_output"
        elif rust_status == "success_partial_internal_timeout":  # Assuming search might also have this
            final_status_str = "partial_text_output"
            text_output_parts.append(
                "[Warning: Search timed out internally, results may be incomplete.]\n")
        elif "error" in rust_status:
            final_status_str = "error_text_output"
            text_output_parts.append(
                f"--- Error during search ---\n{rust_result.get('error', 'Unknown error from Rust search.')}\n")

        formatted_results = format_search_results(
            project_path, rust_result)  # Added project_path
        text_output_parts.append(
            formatted_results if formatted_results else "No results found or an error occurred.")

        final_stats = rust_result.get("stats", {})
        final_stats["overall_search_duration_seconds"] = time.time() - \
            start_time
        text_output_parts.append(
            _format_stats_for_text_output(final_stats, "Search Stats"))

    except Exception as e:
        final_status_str = "error_text_output"
        text_output_parts.append(
            f"--- Critical Error in Python Layer ---\n{e}")
        if debug_mode:
            debug_log_internal.append(
                f"Critical error in project_wide_search_impl: {e}")
        final_stats["overall_search_duration_seconds"] = time.time() - \
            start_time
        text_output_parts.append(_format_stats_for_text_output(
            final_stats, "Search Stats (incomplete)"))

    result_dict = {
        "status": final_status_str,
        "text_output": "\n".join(text_output_parts)
    }
    if debug_mode:
        result_dict["debug_log_for_text_output"] = "\n".join(
            debug_log_internal)
    return result_dict


async def concept_search_impl(args: Dict[str, Any]) -> Dict[str, Any]:
    input_path_str = args["path"]
    query = args["query"]
    project_path = Path(input_path_str)
    debug_mode = args.get("debug", False)
    timeout_seconds = args.get("timeout", 20)
    extensions = args.get("extensions", [".cs", ".py", ".rs", ".js", ".ts"])
    top_n = args.get("top_n", 10)

    debug_log_internal: List[str] = []
    text_output_parts = []
    final_status_str = "error_text_output"
    final_stats = {}

    if not project_path.is_absolute():
        return {"status": "error_text_output", "text_output": f"--- Error ---\nPath '{input_path_str}' must be an absolute path."}
    try:
        if not project_path.exists() or not project_path.is_dir():
            return {"status": "error_text_output", "text_output": f"--- Error ---\nProject path '{input_path_str}' not found or not a directory"}
    except Exception as e:
        return {"status": "error_text_output", "text_output": f"--- Error ---\nInvalid project path: {e}"}

    start_time = time.time()
    try:
        if debug_mode:
            debug_log_internal.append(
                f"Calling concept_search_from_rust with: project_path='{project_path}', query='{query[:50]}...', extensions={extensions}, top_n={top_n}, timeout_seconds={timeout_seconds}, debug_mode={debug_mode}")

        rust_result = concept_search_from_rust(
            project_path, query, extensions, top_n, timeout_seconds, debug_mode
        )
        if debug_mode:
            debug_log_internal.append(
                f"Rust result from concept_search_from_rust: {str(rust_result)[:500]}...")
            if rust_result.get("debug_log"):
                debug_log_internal.extend(rust_result.get("debug_log", []))

        rust_status = rust_result.get("status", "success")
        # Map Rust status (e.g. "success_embeddings_generated_no_results", "error_embedding_generation_failed")
        if rust_status == "success" or "success_" in rust_status:  # Covers success and specific successes
            final_status_str = "success_text_output"
            if rust_status == "success_embeddings_generated_no_results":
                text_output_parts.append(
                    "[Info: Embeddings generated, but no matching concepts found for the query.]\n")
        elif "partial" in rust_status:  # e.g. success_partial_internal_timeout
            final_status_str = "partial_text_output"
            text_output_parts.append(
                "[Warning: Concept search timed out or was partial, results may be incomplete.]\n")
        elif "error" in rust_status:
            final_status_str = "error_text_output"
            text_output_parts.append(
                f"--- Error during concept search ---\n{rust_result.get('error', 'Unknown error from Rust concept search.')}\n")

        formatted_results = format_concept_search_results(
            project_path, rust_result)  # Added project_path
        text_output_parts.append(
            formatted_results if formatted_results else "No results found or an error occurred.")

        final_stats = rust_result.get("stats", {})
        final_stats["overall_concept_search_duration_seconds"] = time.time() - \
            start_time
        text_output_parts.append(_format_stats_for_text_output(
            final_stats, "Concept Search Stats"))

    except Exception as e:
        final_status_str = "error_text_output"
        text_output_parts.append(
            f"--- Critical Error in Python Layer ---\n{e}")
        if debug_mode:
            debug_log_internal.append(
                f"Critical error in concept_search_impl: {e}")
        final_stats["overall_concept_search_duration_seconds"] = time.time() - \
            start_time
        text_output_parts.append(_format_stats_for_text_output(
            final_stats, "Concept Search Stats (incomplete)"))

    result_dict = {
        "status": final_status_str,
        "text_output": "\n".join(text_output_parts)
    }
    if debug_mode:
        result_dict["debug_log_for_text_output"] = "\n".join(
            debug_log_internal)
    return result_dict
