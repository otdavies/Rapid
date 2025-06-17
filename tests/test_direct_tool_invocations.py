import json
from pathlib import Path
import os
import sys
import traceback
from typing import Callable, Dict, Any

# --- Global Setup ---
# Adjusted for tests directory
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Attempt to import all necessary functions
try:
    from logic.rust_adapter import (
        invoke_rust_scanner,
        invoke_rust_searcher,
        invoke_rust_concept_searcher,
        find_rust_library
    )
except ImportError as e:
    print(f"CRITICAL ERROR: Error importing project modules: {e}")
    print("Ensure your PYTHONPATH is set correctly or run this script from the project root.")
    print(f"Current sys.path: {sys.path}")
    print(f"Attempted to add {PROJECT_ROOT} to sys.path.")
    sys.exit(1)

# Common test data directory
TEST_DATA_DIR = PROJECT_ROOT / "test_data"

# --- Helper Function ---


def run_test_with_debug_variants(test_func: Callable, base_params: Dict[str, Any], test_name: str):
    """Runs a given test function with debug=True and debug=False."""
    for debug_mode in [True, False]:
        print("\\n" + "="*80)
        print(f"Running Test: {test_name} (Debug: {debug_mode})")
        print("="*80)

        params = {**base_params, "debug": debug_mode}

        # Print all parameters being used for this specific run
        print("Parameters:")
        for key, value in params.items():
            # For extensions_str in concept search, it can be very long. Truncate if necessary.
            if key == "extensions_str" and isinstance(value, str) and len(value) > 100:
                print(
                    f"  {key.replace('_str', '').capitalize()}: {value[:100]}... (truncated)")
            else:
                print(f"  {key.replace('_str', '').capitalize()}: {value}")

        try:
            test_func(**params)
        except Exception as e:
            print(
                f"\\nEXCEPTION during {test_name} (Debug: {debug_mode}): {e}")
            traceback.print_exc()
        print("="*80 + "\\n")

# --- Test Functions (modified to accept debug_mode) ---


def test_invoke_rust_scanner_runner(project_path_str: str, extensions_str: str, compactness_level: int, timeout_ms: int, debug: bool):
    """Runner for invoke_rust_scanner tests."""
    try:
        result = invoke_rust_scanner(
            project_path_str=project_path_str,
            extensions_str=extensions_str,
            compactness_level=compactness_level,
            timeout_ms=timeout_ms,
            debug=debug
        )
        print("\\n--- Result from invoke_rust_scanner ---")
        print(json.dumps(result, indent=2))
        if result.get("error"):
            print(f"ERROR DETECTED: {result['error']}")
        elif not result.get("file_contexts"):
            print("WARNING: invoke_rust_scanner returned no file_contexts.")
        else:
            print("invoke_rust_scanner execution successful.")

        if debug and "debug_log" not in result:
            print("WARNING: Debug mode was True, but no debug_log found in result.")
        elif not debug and "debug_log" in result:
            print("WARNING: Debug mode was False, but debug_log was found in result.")

        print("--- End of invoke_rust_scanner Result ---")
    except Exception as e:
        print(f"\\nEXCEPTION: {e}")
        traceback.print_exc()


def test_invoke_rust_searcher_runner(project_path_str: str, search_string: str, extensions_str: str, context_lines: int, timeout_ms: int, debug: bool):
    """Runner for invoke_rust_searcher tests."""
    try:
        result = invoke_rust_searcher(
            project_path_str=project_path_str,
            search_string=search_string,
            extensions_str=extensions_str,
            context_lines=context_lines,
            timeout_ms=timeout_ms,
            debug=debug
        )
        print("\\n--- Result from invoke_rust_searcher ---")
        print(json.dumps(result, indent=2))
        if result.get("error"):
            print(f"ERROR DETECTED: {result['error']}")
        elif not result.get("results") and result.get("stats", {}).get("total_matches", 0) == 0:
            print(
                f"Search for '{search_string}' found no matches (this may be expected).")
        elif result.get("stats", {}).get("total_matches", 0) > 0:
            print("invoke_rust_searcher execution successful (found matches).")
        else:
            print("invoke_rust_searcher execution completed, but outcome unclear.")

        if debug and "debug_log" not in result:
            print("WARNING: Debug mode was True, but no debug_log found in result.")
        elif not debug and "debug_log" in result:
            print("WARNING: Debug mode was False, but debug_log was found in result.")

        print("--- End of invoke_rust_searcher Result ---")
    except Exception as e:
        print(f"\\nEXCEPTION: {e}")
        traceback.print_exc()


def test_invoke_rust_concept_searcher_runner(project_path_str: str, query_str: str, extensions_str: str, top_n: int, timeout_ms: int, debug: bool):
    """Runner for invoke_rust_concept_searcher tests."""
    try:
        result = invoke_rust_concept_searcher(
            project_path_str=project_path_str,
            query_str=query_str,
            extensions_str=extensions_str,
            top_n=top_n,
            timeout_ms=timeout_ms,
            debug=debug
        )
        print("\\n--- Result from invoke_rust_concept_searcher ---")
        if result.get("error"):
            print(f"ERROR DETECTED: {result['error']}")
        elif not result.get("results") and result.get("stats", {}).get("functions_analyzed", 0) == 0:
            print("WARNING: invoke_rust_concept_searcher analyzed 0 functions.")
        elif result.get("results"):
            print(
                "invoke_rust_concept_searcher execution successful (analyzed functions).")
            print("Formatted Results:")
            for item in result.get("results", []):
                print(f"  File: {item.get('file')}")
                # The 'body' field now contains the function body.
                # The 'function' field (function name) is being omitted as requested.
                print(f"  Function Body:\\n{item.get('body', 'N/A')}")
                print("-" * 20)

            # Check for 'body' in the first result for general validation
            first_res = result["results"][0]
            if "body" not in first_res:
                print("WARNING: 'body' field missing from concept search results.")
            elif not first_res.get("body"):
                print(
                    "WARNING: 'body' field is present but empty/null in concept search results.")
        else:
            print(
                "invoke_rust_concept_searcher execution completed, but outcome unclear (no results found).")

        # Debug log is a top-level field for concept_search results
        debug_log_present = "debug_log" in result and result["debug_log"] is not None

        if debug:
            if not debug_log_present:
                print(
                    "ERROR: Debug mode was True, but no debug_log found or it is null in result for concept_search.")
            else:
                print("Debug log content:")
                for log_entry in result["debug_log"]:
                    print(f"  - {log_entry}")

                expected_ffi_log_true = "[FFI concept_search] Received debug_c: true"
                if any(expected_ffi_log_true in entry for entry in result["debug_log"]):
                    print(
                        f"SUCCESS: Found expected FFI entry log: '{expected_ffi_log_true}'")
                else:
                    print(
                        f"ERROR: Did NOT find expected FFI entry log for debug=true: '{expected_ffi_log_true}'")

                expected_inner_log_true = "[ConceptSearchInner] START. Debug: true"
                if any(expected_inner_log_true in entry for entry in result["debug_log"]):
                    print(
                        f"SUCCESS: Found expected ConceptSearchInner entry log: '{expected_inner_log_true}'")
                else:
                    print(
                        f"ERROR: Did NOT find expected ConceptSearchInner entry log for debug=true: '{expected_inner_log_true}'")

        elif not debug:
            # Check if list is not empty
            if debug_log_present and result["debug_log"]:
                print(
                    "ERROR: Debug mode was False, but debug_log was found and is not empty in result for concept_search.")
                print("Unexpected debug log content:")
                for log_entry in result["debug_log"]:
                    print(f"  - {log_entry}")
            else:
                # Check for the specific FFI log for debug=false to ensure it's correctly NOT there,
                # or that the FFI log indicates debug_c was false.
                # This part is tricky because if debug_c is false, ffi_entry_debug_log is None.
                # The test for debug=true already covers positive confirmation.
                # For debug=false, we primarily care that no extensive debug logs appear.
                # The `[FFI concept_search] Received debug_c: false` would only appear if we forced it into another field.
                # For now, just ensuring the log is empty or absent is the main check.
                print(
                    "Debug mode was False, and debug_log is appropriately absent or empty.")

        print("--- End of invoke_rust_concept_searcher Result ---")
    except Exception as e:
        print(f"\\nEXCEPTION: {e}")
        traceback.print_exc()

# --- Main Execution ---


def main():
    print("Starting All Direct Tool Tests...")
    print(f"Project Root: {PROJECT_ROOT}")
    print(f"Test Data Directory: {TEST_DATA_DIR}")

    rust_lib_path = find_rust_library()
    if not rust_lib_path:
        print("CRITICAL ERROR: Rust library (file_scanner) not found. Ensure it's built (cargo build --release).")
        return
    print(f"Found Rust library at: {rust_lib_path}")

    if not TEST_DATA_DIR.is_dir():
        print(
            f"CRITICAL ERROR: Test data directory not found at {TEST_DATA_DIR}")
        return

    # Define base parameters for each test
    scanner_base_params = {
        "project_path_str": str(TEST_DATA_DIR.resolve()),
        "extensions_str": ",".join([".py", ".rs", ".cs", ".ts"]),
        "compactness_level": 1,  # Test with signature level for scanner
        "timeout_ms": 30000
    }
    searcher_base_params = {
        "project_path_str": str(TEST_DATA_DIR.resolve()),
        "search_string": "Method",
        "extensions_str": ",".join([".py", ".rs", ".cs", ".ts"]),
        "context_lines": 2,
        "timeout_ms": 30000
    }
    concept_searcher_base_params = {
        "project_path_str": str(TEST_DATA_DIR.resolve()),
        "query_str": "a function that performs calculations",
        # Keep as JSON string for concept search
        "extensions_str": json.dumps([".py", ".rs", ".cs", ".ts"]),
        "top_n": 5,
        "timeout_ms": 60000  # Longer for embedding
        # "debug" will be added by run_test_with_debug_variants
    }

    # Run tests with debug variants
    run_test_with_debug_variants(test_invoke_rust_scanner_runner,
                                 scanner_base_params, "Get Full Context (invoke_rust_scanner)")
    run_test_with_debug_variants(test_invoke_rust_searcher_runner,
                                 searcher_base_params, "Project Wide Search (invoke_rust_searcher)")
    run_test_with_debug_variants(test_invoke_rust_concept_searcher_runner,
                                 concept_searcher_base_params, "Concept Search (invoke_rust_concept_searcher)")

    print("All Direct Tool Tests Completed.")


if __name__ == "__main__":
    main()
