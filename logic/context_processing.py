import textwrap
from typing import List, Dict, Any
from pathlib import Path


def _get_relative_path_str(abs_path_str: str, project_root_path: Path) -> str:
    """Helper to convert absolute path string to relative path string."""
    if abs_path_str == "UNKNOWN_FILE" or not project_root_path:
        return abs_path_str
    try:
        abs_path = Path(abs_path_str)
        # Ensure project_root_path is an ancestor or the same as abs_path
        if project_root_path in abs_path.parents or project_root_path == abs_path:
            return str(abs_path.relative_to(project_root_path))
        else:  # If not an ancestor, return the original absolute path or just the name
            return abs_path.name  # Or abs_path_str if full path is preferred in this edge case
    except ValueError:  # Handles cases like paths on different drives for Windows
        return Path(abs_path_str).name  # Fallback to filename
    except Exception:  # Catch any other path-related errors
        return abs_path_str  # Fallback to original string


def format_project_context(
    project_root_path: Path,
    file_contexts: List[Dict[str, Any]],
    compactness_level: int
) -> str:
    """
    Formats the collected project context into a human-readable string,
    grouped by file, with items as bullet points. Paths are relative to project_root_path.
    """
    output_blocks = []
    # Sort by the original absolute path for consistent ordering
    for file_data in sorted(file_contexts, key=lambda x: x.get('path', '')):
        abs_file_path_str = file_data.get("path", "UNKNOWN_FILE")
        relative_file_path_str = _get_relative_path_str(
            abs_file_path_str, project_root_path)

        functions = file_data.get("functions", [])

        if not functions:
            continue

        file_content_parts = []
        for func in functions:
            name = func.get('name', 'UNKNOWN_FUNCTION')
            body = func.get('body')
            comment = func.get('comment')

            func_representation = ""
            if compactness_level == 0:  # Function names only
                func_representation = name
            elif compactness_level == 1:  # Function signature
                func_representation = body.strip() if body else name
            elif compactness_level == 2:  # Signature and comments
                comment_str = ""
                if comment:
                    cleaned_comment = ' '.join(comment.strip().split())
                    if cleaned_comment:
                        comment_str = f"{cleaned_comment}\n"
                func_representation = f"{comment_str}{body.strip() if body else name}"
            elif compactness_level >= 3:  # Full function
                comment_str = f"{comment.strip()}\n" if comment else ""
                func_representation = f"{comment_str}{body.strip() if body else name}"

            file_content_parts.append(func_representation)

        bullet_point_parts = [f"- {part}" for part in file_content_parts]
        file_content_str = "\n".join(bullet_point_parts)

        output_blocks.append(
            f'FILE: {relative_file_path_str}\n{file_content_str}')

    return "\n\n".join(output_blocks)


def format_search_results(
    project_root_path: Path,
    search_results: Dict[str, Any]
) -> str:
    """
    Formats the search results into an XML-style string. Paths are relative to project_root_path.
    """
    output_blocks = []
    results = search_results.get("results", [])

    for file_result in sorted(results, key=lambda x: x.get('path', '')):
        abs_file_path_str = file_result.get("path", "UNKNOWN_FILE")
        relative_file_path_str = _get_relative_path_str(
            abs_file_path_str, project_root_path)
        matches = file_result.get("matches", [])

        if not matches:
            continue

        match_parts = []
        for match in matches:
            line_number = match.get('line_number', 'N/A')
            context = match.get('context', '')
            match_parts.append(
                f'<MATCH line="{line_number}">\n{context}\n</MATCH>')

        file_content_str = "\n".join(match_parts)
        output_blocks.append(
            f'<FILE path="{relative_file_path_str}">\n{file_content_str}\n</FILE>')

    return "\n\n".join(output_blocks)


def format_concept_search_results(
    project_root_path: Path,
    search_results: Dict[str, Any]
) -> str:
    """
    Formats the concept search results into a readable string, grouped by file.
    Paths are relative to project_root_path.
    """
    output_blocks = []
    raw_results = search_results.get("results", [])

    # Group results by original absolute file path first to ensure correct grouping
    file_groups_abs: Dict[str, List[Dict[str, Any]]] = {}
    for result in raw_results:
        abs_file_path_str = result.get("file", "UNKNOWN_FILE")
        if abs_file_path_str not in file_groups_abs:
            file_groups_abs[abs_file_path_str] = []
        file_groups_abs[abs_file_path_str].append(result)

    # Sort files by absolute path for consistent ordering before converting to relative
    sorted_abs_files = sorted(file_groups_abs.keys())

    for abs_file_path_str in sorted_abs_files:
        relative_file_path_str = _get_relative_path_str(
            abs_file_path_str, project_root_path)

        match_parts = []
        # Sort functions within a file by similarity
        sorted_functions = sorted(file_groups_abs[abs_file_path_str], key=lambda x: x.get(
            'similarity', 0.0), reverse=True)

        for match in sorted_functions:
            function_name = match.get('function', 'N/A')
            similarity = match.get('similarity', 0.0)
            match_parts.append(
                f"- {function_name} (Similarity: {similarity:.4f})")

        file_content_str = "\n".join(match_parts)
        output_blocks.append(
            f"FILE: {relative_file_path_str}\n{file_content_str}")

    return "\n\n".join(output_blocks)
