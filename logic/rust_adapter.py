import ctypes
import json
from pathlib import Path
from typing import Optional, Dict, Any

# This print statement can be removed if it's no longer needed for startup checks.
# For now, I'll keep it commented out, assuming it was for the old subprocess model.
# print("ADAPTER_SCRIPT_LOADING_OK", file=sys.stderr, flush=True)


def find_rust_library() -> Optional[Path]:
    """
    Finds the Rust library, checking for release and debug builds.
    The path is constructed relative to this script's location.
    """
    base_path = Path(
        __file__).parent.parent  # Moves up two levels to project root

    # Look for the 'file_scanner' directory, which is at the root.
    scanner_path = base_path / "file_scanner"

    # Check for release build first
    release_path = scanner_path / "target" / "release" / "file_scanner.dll"
    if release_path.exists():
        return release_path

    # Fallback to debug build
    debug_path = scanner_path / "target" / "debug" / "file_scanner.dll"
    if debug_path.exists():
        return debug_path

    return None


def invoke_rust_scanner(
    project_path_str: str,
    extensions_str: str,
    compactness_level: int,
    timeout_ms: int
) -> Dict[str, Any]:
    """
    Loads the Rust library, calls the scan_and_parse function, and returns the result.
    The library is loaded and unloaded (implicitly by ctypes) on each call.
    """
    lib_path = find_rust_library()

    if not lib_path:
        return {"error": "Rust library not found.", "file_contexts": [], "debug_log": ["Rust library not found."]}

    try:
        rust_lib = ctypes.CDLL(str(lib_path))
    except OSError as e:
        return {"error": f"Failed to load Rust library: {e}", "file_contexts": [], "debug_log": [f"Failed to load Rust library: {e}"]}

    try:
        rust_lib.scan_and_parse.argtypes = [
            ctypes.c_char_p,  # root_path_c
            ctypes.c_char_p,  # extensions_c
            ctypes.c_uint8,   # compactness_level_c
            ctypes.c_uint32   # timeout_ms_c
        ]
        rust_lib.scan_and_parse.restype = ctypes.c_void_p
        rust_lib.free_string.argtypes = [ctypes.c_void_p]
        rust_lib.free_string.restype = None  # Explicitly set restype for free_string

        root_path_c = ctypes.c_char_p(project_path_str.encode('utf-8'))
        extensions_c = ctypes.c_char_p(extensions_str.encode('utf-8'))
        compactness_level_c = ctypes.c_uint8(compactness_level)
        timeout_ms_c = ctypes.c_uint32(timeout_ms)

        result_ptr = rust_lib.scan_and_parse(
            root_path_c, extensions_c, compactness_level_c, timeout_ms_c)

        if not result_ptr:
            # Ensure free_string is not called with a NULL pointer if scan_and_parse fails early.
            # However, the Rust side should ideally always return a valid pointer (e.g., to an empty error JSON)
            # or the contract for free_string must allow NULL. Assuming free_string handles NULL.
            # Call free_string even if result_ptr is null, if Rust side expects it
            rust_lib.free_string(result_ptr)
            return {"file_contexts": [], "debug_log": ["Rust scan_and_parse returned null pointer."]}

        value = ctypes.cast(result_ptr, ctypes.c_char_p).value
        json_string = value.decode('utf-8') if value else ""

        rust_lib.free_string(result_ptr)

        if not json_string:
            return {"file_contexts": [], "debug_log": ["Rust scan_and_parse returned empty string after decode."]}

        # Attempt to parse the JSON string
        try:
            result_data = json.loads(json_string)
            return result_data
        except json.JSONDecodeError as e:
            return {"error": f"Failed to parse JSON response from Rust: {e}",
                    "raw_response": json_string,
                    "file_contexts": [],
                    "debug_log": [f"JSONDecodeError: {e}", f"Raw string: {json_string[:500]}..."]}

    except Exception as e:
        # Catch any other ctypes or unexpected errors during the call
        return {"error": f"An unexpected error occurred while interacting with the Rust library: {e}",
                "file_contexts": [],
                "debug_log": [f"Unexpected error: {e}"]}
    finally:
        # On Windows, ctypes.CDLL uses LoadLibrary. The DLL is unloaded when the CDLL object
        # is garbage collected. There isn't an explicit unload function in ctypes for Windows
        # equivalent to FreeLibrary that we can call here directly and reliably without
        # causing issues if the library is still in use or if Python's GC plans to collect it.
        # By creating rust_lib within this function scope, it becomes eligible for GC upon exit.
        # If the DLL needs to be *guaranteed* to be unloaded for recompilation,
        # this approach is generally sufficient.
        # This might encourage GC but doesn't guarantee immediate unload.
        del rust_lib
        pass


def invoke_rust_searcher(
    project_path_str: str,
    search_string: str,
    extensions_str: str,
    context_lines: int,
    timeout_ms: int
) -> Dict[str, Any]:
    """
    Loads the Rust library, calls the project_wide_search function, and returns the result.
    """
    lib_path = find_rust_library()

    if not lib_path:
        return {"error": "Rust library not found.", "results": [], "stats": {}}

    try:
        rust_lib = ctypes.CDLL(str(lib_path))
    except OSError as e:
        return {"error": f"Failed to load Rust library: {e}", "results": [], "stats": {}}

    try:
        rust_lib.project_wide_search.argtypes = [
            ctypes.c_char_p,  # root_path_c
            ctypes.c_char_p,  # search_string_c
            ctypes.c_char_p,  # extensions_c
            ctypes.c_uint8,   # context_lines_c
            ctypes.c_uint32   # timeout_ms_c
        ]
        rust_lib.project_wide_search.restype = ctypes.c_void_p
        rust_lib.free_string.argtypes = [ctypes.c_void_p]
        rust_lib.free_string.restype = None

        root_path_c = ctypes.c_char_p(project_path_str.encode('utf-8'))
        search_string_c = ctypes.c_char_p(search_string.encode('utf-8'))
        extensions_c = ctypes.c_char_p(extensions_str.encode('utf-8'))
        context_lines_c = ctypes.c_uint8(context_lines)
        timeout_ms_c = ctypes.c_uint32(timeout_ms)

        result_ptr = rust_lib.project_wide_search(
            root_path_c, search_string_c, extensions_c, context_lines_c, timeout_ms_c)

        if not result_ptr:
            rust_lib.free_string(result_ptr)
            return {"results": [], "stats": {}, "debug_log": ["Rust project_wide_search returned null pointer."]}

        value = ctypes.cast(result_ptr, ctypes.c_char_p).value
        json_string = value.decode('utf-8') if value else ""

        rust_lib.free_string(result_ptr)

        if not json_string:
            return {"results": [], "stats": {}, "debug_log": ["Rust project_wide_search returned empty string after decode."]}

        try:
            result_data = json.loads(json_string)
            return result_data
        except json.JSONDecodeError as e:
            return {"error": f"Failed to parse JSON response from Rust: {e}",
                    "raw_response": json_string,
                    "results": [],
                    "stats": {}}

    except Exception as e:
        return {"error": f"An unexpected error occurred while interacting with the Rust library: {e}",
                "results": [],
                "stats": {}}
    finally:
        del rust_lib
        pass

# Removed the if __name__ == "__main__": block as this module will be imported.
