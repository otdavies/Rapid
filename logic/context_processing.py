import textwrap
from typing import List, Dict, Any


def format_project_context(
    file_contexts: List[Dict[str, Any]],
    compactness_level: int,
    include_descriptions: bool
) -> str:
    """
    Formats the collected project context into an XML-style string.
    """
    output_blocks = []
    for file_data in sorted(file_contexts, key=lambda x: x.get('path', '')):
        file_path = file_data.get("path", "UNKNOWN_FILE")
        # Extract only the filename from the path
        file_name = file_path.split('/')[-1]
        functions = file_data.get("functions", [])
        
        if not functions:
            continue

        file_content_parts = []
        for func in functions:
            name = func.get('name', 'UNKNOWN_FUNCTION')
            body = func.get('body')
            comment = func.get('comment')

            func_representation = ""
            if compactness_level == 0: # Function names only
                func_representation = name
            elif compactness_level == 1: # Function signature
                func_representation = body.strip() if body else name
            elif compactness_level == 2: # Signature and comments
                comment_str = ""
                if comment:
                    cleaned_comment = ' '.join(comment.strip().split())
                    if cleaned_comment:
                        comment_str = f"{cleaned_comment}\n"
                func_representation = f"{comment_str}{body.strip() if body else name}"
            elif compactness_level >= 3: # Full function
                comment_str = f"{comment.strip()}\n" if comment else ""
                func_representation = f"{comment_str}{body.strip() if body else name}"
            
            file_content_parts.append(func_representation)

        # Join functions with a separator that makes sense for readability
        separator = ", " if compactness_level < 2 else "\n"
        file_content_str = separator.join(file_content_parts)
        
        output_blocks.append(f'<FILE="{file_name}">\n{file_content_str}\n</FILE>')

    return "\n".join(output_blocks)


def format_search_results(search_results: Dict[str, Any]) -> str:
    """
    Formats the search results into an XML-style string.
    """
    output_blocks = []
    results = search_results.get("results", [])
    
    for file_result in sorted(results, key=lambda x: x.get('path', '')):
        file_path = file_result.get("path", "UNKNOWN_FILE")
        file_name = file_path.split('/')[-1]
        matches = file_result.get("matches", [])
        
        if not matches:
            continue

        match_parts = []
        for match in matches:
            line_number = match.get('line_number', 'N/A')
            context = match.get('context', '')
            match_parts.append(f'<MATCH line="{line_number}">\n{context}\n</MATCH>')

        file_content_str = "\n".join(match_parts)
        output_blocks.append(f'<FILE="{file_name}">\n{file_content_str}\n</FILE>')

    return "\n\n".join(output_blocks)


def format_concept_search_results(search_results: Dict[str, Any]) -> str:
    """
    Formats the concept search results into a readable string, grouped by file.
    """
    output_blocks = []
    results = search_results.get("results", [])
    
    # Group results by file
    file_groups = {}
    for result in results:
        file_path = result.get("file", "UNKNOWN_FILE")
        if file_path not in file_groups:
            file_groups[file_path] = []
        file_groups[file_path].append(result)

    # Sort files by path
    sorted_files = sorted(file_groups.keys())

    for file_path in sorted_files:
        file_name = file_path.split('/')[-1]
        
        match_parts = []
        # Sort functions within a file by similarity
        sorted_functions = sorted(file_groups[file_path], key=lambda x: x.get('similarity', 0.0), reverse=True)

        for match in sorted_functions:
            function_name = match.get('function', 'N/A')
            similarity = match.get('similarity', 0.0)
            match_parts.append(f"- {function_name} (Similarity: {similarity:.4f})")

        file_content_str = "\n".join(match_parts)
        output_blocks.append(f"FILE: {file_name}\n{file_content_str}")

    return "\n\n".join(output_blocks)
