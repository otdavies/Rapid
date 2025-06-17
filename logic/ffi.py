import ctypes
import json
import platform
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple, Callable

# Global variable to hold the loaded library instance
# This avoids reloading the DLL on every call, which can be inefficient
# and problematic on some OSes if the library is already in use.
s_rust_lib: Optional[ctypes.CDLL] = None
s_lib_path: Optional[Path] = None


class FFIError(Exception):
    """Custom exception for FFI related errors."""

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.details = details if details is not None else {}


def _find_rust_library_path() -> Optional[Path]:
    """
    Finds the Rust library path, checking for release and debug builds.
    The path is constructed relative to this script's location and is OS-aware.
    """
    base_path = Path(__file__).resolve(
    ).parent.parent  # Moves up to the project root (d:/AIProjects/MCPServers/project-context-server)

    system = platform.system()
    if system == "Windows":
        lib_name = "file_scanner.dll"
    elif system == "Darwin":  # macOS
        lib_name = "libfile_scanner.dylib"
    else:  # Linux and other UNIX-like
        lib_name = "libfile_scanner.so"

    scanner_path = base_path / "file_scanner"

    release_path = scanner_path / "target" / "release" / lib_name
    if release_path.exists():
        return release_path

    debug_path = scanner_path / "target" / "debug" / lib_name
    if debug_path.exists():
        return debug_path

    return None


def _get_rust_library() -> ctypes.CDLL:
    """
    Loads the Rust library using ctypes.
    Raises FFIError if the library cannot be found or loaded.
    Uses a global variable to cache the loaded library.
    """
    global s_rust_lib, s_lib_path

    if s_rust_lib is not None and s_lib_path is not None and s_lib_path.exists():
        # Potentially add a check here if the library file has been modified,
        # though for simplicity, we assume it doesn't change during a single server run.
        return s_rust_lib

    s_lib_path = _find_rust_library_path()
    if not s_lib_path:
        raise FFIError("Rust library not found.", {
                       "tried_paths": "release and debug target directories"})

    try:
        s_rust_lib = ctypes.CDLL(str(s_lib_path))
        # Setup free_string function once
        s_rust_lib.free_string.argtypes = [ctypes.c_void_p]
        s_rust_lib.free_string.restype = None
        return s_rust_lib
    except OSError as e:
        s_rust_lib = None  # Reset on failure
        s_lib_path = None
        raise FFIError(f"Failed to load Rust library: {e}", {
                       "path": str(s_lib_path)})


def _invoke_ffi_function(
    rust_fn_name: str,
    arg_types: List[Any],
    args: Tuple[Any, ...],
    debug: bool = False,
    calling_function_name: str = "unknown"
) -> Dict[str, Any]:
    """
    Generic helper to invoke a Rust FFI function that returns a JSON string.
    Handles loading the library, setting up argtypes/restype, calling, and processing the response.
    """
    ffi_debug_log: List[str] = []
    if debug:
        ffi_debug_log.append(
            f"[_invoke_ffi_function for {calling_function_name}] Called. Rust func: {rust_fn_name}, Debug: {debug}")

    try:
        rust_lib = _get_rust_library()

        rust_function = getattr(rust_lib, rust_fn_name)
        rust_function.argtypes = arg_types
        # All our Rust functions return char* (via void*)
        rust_function.restype = ctypes.c_void_p

        if debug:
            # Be careful about logging sensitive data if args can contain it.
            # For now, logging types and existence.
            arg_summary = [(type(arg), arg.value if hasattr(arg, 'value') and isinstance(
                arg.value, bytes) else '...') for arg in args]
            ffi_debug_log.append(
                f"[_invoke_ffi_function] Calling Rust '{rust_fn_name}' with arg types: {arg_summary}")

        result_ptr = rust_function(*args)

        if not result_ptr:
            # Rust function returned a null pointer.
            rust_lib.free_string(result_ptr)  # type: ignore
            error_msg = f"Rust function '{rust_fn_name}' returned a null pointer."
            if debug:
                ffi_debug_log.append(error_msg)
            return {"error": error_msg, "debug_log": ffi_debug_log}

        # Cast the void* to char*, get the value, and decode
        value = ctypes.cast(result_ptr, ctypes.c_char_p).value
        json_string = value.decode('utf-8') if value else ""

        rust_lib.free_string(result_ptr)  # type: ignore

        if not json_string:
            error_msg = f"Rust function '{rust_fn_name}' returned an empty string after decode."
            if debug:
                ffi_debug_log.append(error_msg)
            return {"error": error_msg, "debug_log": ffi_debug_log}

        if debug:
            ffi_debug_log.append(
                f"[_invoke_ffi_function] Raw JSON from '{rust_fn_name}': {json_string[:500]}...")

        try:
            result_data = json.loads(json_string)
            if debug:
                # Prepend FFI logs to any logs from Rust
                rust_debug_logs = result_data.get("debug_log", [])
                if not isinstance(rust_debug_logs, list):
                    rust_debug_logs = [
                        str(rust_debug_logs)] if rust_debug_logs is not None else []
                result_data["debug_log"] = ffi_debug_log + rust_debug_logs
            return result_data
        except json.JSONDecodeError as e:
            error_msg = f"Failed to parse JSON response from Rust function '{rust_fn_name}': {e}"
            if debug:
                ffi_debug_log.append(
                    f"{error_msg}. Raw string: {json_string[:500]}...")
            return {"error": error_msg, "raw_response": json_string, "debug_log": ffi_debug_log}

    except FFIError as e:  # Errors from _get_rust_library
        if debug:
            ffi_debug_log.append(f"FFIError: {str(e)}. Details: {e.details}")
        return {"error": str(e), "details": e.details, "debug_log": ffi_debug_log}
    except AttributeError as e:  # getattr failed for rust_fn_name
        error_msg = f"Rust function '{rust_fn_name}' not found in library."
        if debug:
            ffi_debug_log.append(f"{error_msg} Details: {str(e)}")
        return {"error": error_msg, "debug_log": ffi_debug_log}
    except Exception as e:
        # Catch any other unexpected errors
        error_msg = f"An unexpected error occurred in _invoke_ffi_function for '{rust_fn_name}': {e}"
        if debug:
            ffi_debug_log.append(error_msg)
        return {"error": error_msg, "debug_log": ffi_debug_log}

# --- Public FFI Invocation Functions ---


def invoke_scan_and_parse(
    project_path: str, extensions: List[str], compactness_level: int, timeout_sec: int, debug: bool = False
) -> Dict[str, Any]:
    """
    Invokes the 'scan_and_parse' FFI function.
    """
    extensions_str = ",".join(extensions)
    timeout_ms = timeout_sec * 1000

    # Prepare ctype arguments
    root_path_c = ctypes.c_char_p(project_path.encode('utf-8'))
    extensions_c = ctypes.c_char_p(extensions_str.encode('utf-8'))
    compactness_level_c = ctypes.c_uint8(compactness_level)
    timeout_ms_c = ctypes.c_uint32(timeout_ms)
    debug_c = ctypes.c_bool(debug)

    arg_types = [ctypes.c_char_p, ctypes.c_char_p,
                 ctypes.c_uint8, ctypes.c_uint32, ctypes.c_bool]
    args_tuple = (root_path_c, extensions_c,
                  compactness_level_c, timeout_ms_c, debug_c)

    return _invoke_ffi_function("scan_and_parse", arg_types, args_tuple, debug, "invoke_scan_and_parse")


def invoke_project_wide_search(
    project_path: str, search_string: str, extensions: List[str], context_lines: int, timeout_sec: int, debug: bool = False
) -> Dict[str, Any]:
    """
    Invokes the 'project_wide_search' FFI function.
    """
    extensions_str = ",".join(extensions)
    timeout_ms = timeout_sec * 1000

    root_path_c = ctypes.c_char_p(project_path.encode('utf-8'))
    search_string_c = ctypes.c_char_p(search_string.encode('utf-8'))
    extensions_c = ctypes.c_char_p(extensions_str.encode('utf-8'))
    context_lines_c = ctypes.c_uint8(context_lines)
    timeout_ms_c = ctypes.c_uint32(timeout_ms)
    debug_c = ctypes.c_bool(debug)

    arg_types = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_char_p,
                 ctypes.c_uint8, ctypes.c_uint32, ctypes.c_bool]
    args_tuple = (root_path_c, search_string_c, extensions_c,
                  context_lines_c, timeout_ms_c, debug_c)

    return _invoke_ffi_function("project_wide_search", arg_types, args_tuple, debug, "invoke_project_wide_search")


def invoke_concept_search(
    project_path: str, query: str, extensions: List[str], top_n: int, timeout_sec: int, debug: bool = False
) -> Dict[str, Any]:
    """
    Invokes the 'concept_search' FFI function.
    Note: extensions are passed as a JSON string to Rust for concept_search.
    """
    extensions_json_str = json.dumps(extensions)
    timeout_ms = timeout_sec * 1000

    root_path_c = ctypes.c_char_p(project_path.encode('utf-8'))
    query_c = ctypes.c_char_p(query.encode('utf-8'))
    extensions_json_c = ctypes.c_char_p(extensions_json_str.encode('utf-8'))
    top_n_c = ctypes.c_size_t(top_n)
    timeout_ms_c = ctypes.c_uint32(timeout_ms)
    debug_c = ctypes.c_bool(debug)

    arg_types = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_char_p,
                 ctypes.c_size_t, ctypes.c_uint32, ctypes.c_bool]
    args_tuple = (root_path_c, query_c, extensions_json_c,
                  top_n_c, timeout_ms_c, debug_c)

    # Special handling for concept_search results
    raw_result = _invoke_ffi_function(
        "concept_search", arg_types, args_tuple, debug, "invoke_concept_search")

    # Ensure debug_log list exists if debug is true, done early.
    if debug and "debug_log" not in raw_result:
        # Should be created by _invoke_ffi_function if debug, but as a safeguard.
        raw_result["debug_log"] = []

    # Handle cases where Rust might return `{"error": null, "results": [...]}` on success.
    # If "error" key exists and is None, and results are present, treat as success.
    if raw_result.get("error") is None and "error" in raw_result and raw_result.get("results"):
        if debug:
            log_msg = "[invoke_concept_search] Corrected 'error: null' from Rust because results were present."
            # Ensure debug_log is a list before trying to insert
            if not isinstance(raw_result.get("debug_log"), list):
                raw_result["debug_log"] = []
            raw_result["debug_log"].insert(0, log_msg)

        del raw_result["error"]  # Remove the "error": null
        if "status" not in raw_result:  # If Rust didn't also provide a status
            raw_result["status"] = "success"  # Assume success

    # Legacy handling for "error_adapter_call" status from Rust with string results.
    # This might be less relevant if concept_search results are now consistently lists.
    if "error" not in raw_result:  # Check again, as the block above might have removed "error"
        current_status_from_rust = raw_result.get("status")
        results_data = raw_result.get("results")  # Can be list or string

        # This condition specifically checks for string results, as per original logic.
        if current_status_from_rust == "error_adapter_call" and \
           isinstance(results_data, str) and results_data.strip():

            new_status = "success_with_rust_reported_issue"
            raw_result["status"] = new_status
            # 'error' key might be absent or was 'error:null' and removed.
            # If Rust set status=error_adapter_call but no actual error field, add one.
            if "error" not in raw_result:
                raw_result["error"] = (
                    f"Rust layer reported status '{current_status_from_rust}' "
                    f"but provided results (type: {type(results_data).__name__})."
                )

            if debug:
                log_message = (
                    f"[invoke_concept_search] Overrode Rust's status '{current_status_from_rust}' "
                    f"to '{new_status}' because results (string) were present. "
                    f"Ensured 'error' field: '{raw_result.get('error')}'."
                )
                if not isinstance(raw_result.get("debug_log"), list):  # Should be a list
                    raw_result["debug_log"] = []
                raw_result["debug_log"].insert(0, log_message)

    return raw_result

# Example of how to potentially unload the library if needed, e.g., for testing or specific scenarios.
# This is OS-dependent and can be tricky.
# For Windows:
# if platform.system() == "Windows":
#     kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
#     def unload_library():
#         global s_rust_lib
#         if s_rust_lib:
#             handle = s_rust_lib._handle
#             kernel32.FreeLibrary(handle)
#             s_rust_lib = None
# else: # For Linux/macOS (conceptual, dlclose is harder to call safely via ctypes)
#     # On Unix, library unloading is typically handled by GC or less explicitly needed.
#     # Forcing dlclose can be complex.
#     def unload_library():
#         global s_rust_lib
#         # This is non-trivial and often not recommended with ctypes
#         # Forcing GC might be an option: import gc; gc.collect()
#         s_rust_lib = None # Allow GC to collect
#         pass

# For now, we rely on Python's GC to unload the DLL when s_rust_lib is no longer referenced
# or when the program exits. Explicit unloading is commented out.
