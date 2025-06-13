import textwrap
from typing import List, Dict, Any


def format_project_context(
    file_contexts: List[Dict[str, Any]],
    compactness_level: int,
    include_descriptions: bool
) -> str:
    """
    Formats the collected project context into a structured, machine-readable string
    optimized for LLM consumption.
    """

    def dedent_body(body: str) -> str:
        """Strips, dedents, and prepares a code body for structured output."""
        if not body:
            return ""
        body = body.strip()
        if body.startswith('{') and body.endswith('}'):
            body = body[1:-1].strip()

        lines = body.split('\n')
        if any(lines[0].strip().startswith(q) for q in ['"""', "'''"]):
            quote_char = '"""' if lines[0].strip().startswith('"""') else "'''"
            if lines[0].strip().count(quote_char) >= 2:
                body = '\n'.join(lines[1:])
            else:
                for i, line in enumerate(lines[1:]):
                    if quote_char in line:
                        body = '\n'.join(lines[i+2:])
                        break

        return textwrap.dedent(body).strip()

    output_blocks = []
    for file_data in sorted(file_contexts, key=lambda x: x.get('path', '')):
        file_path = file_data.get("path", "UNKNOWN_FILE")
        functions = file_data.get("functions", [])
        block = f"[FILE_PATH] {file_path}\n"

        if not functions:
            block += "[NO_FUNCTIONS]\n"
            output_blocks.append(block)
            continue

        for func in functions:
            name = func.get('name', 'UNKNOWN_FUNCTION')
            block += f"[FUNC_NAME] {name}\n"

            if compactness_level == 1:
                comment_text = func.get('comment')
                if comment_text:
                    cleaned_comment = ' '.join(comment_text.strip().split())
                    if cleaned_comment:
                        block += f"[COMMENT] {cleaned_comment}\n"

            elif compactness_level >= 2:
                body = dedent_body(func.get('body'))
                block += f"[BODY]\n---\n{body}\n---\n"

        output_blocks.append(block)

    return "\n".join(output_blocks)
    return "\n".join(output_blocks)
