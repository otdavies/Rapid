"""
Enhanced file parser that extracts function signatures and descriptions from comments.
"""

import re
import os
from typing import List, Dict, Any, Optional, Tuple


class FileParser:
    def __init__(self):
        self.parsers = {
            ".py": self._parse_python,
            ".rs": self._parse_rust,
            ".js": self._parse_javascript,
            ".jsx": self._parse_javascript,
            ".ts": self._parse_typescript,
            ".tsx": self._parse_typescript,
            ".cs": self._parse_csharp
        }

    def parse_file(self, file_path: str) -> Tuple[Optional[str], List[Dict[str, Any]]]:
        """Parse file and extract file description and function signatures with descriptions."""
        ext = os.path.splitext(file_path)[1]

        if ext not in self.parsers:
            return None, []

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()

            # Extract file-level description
            file_description = self._extract_file_description(content, ext)

            # Parse functions
            functions = self.parsers[ext](content)

            # Deduplicate functions by name (handle function overloads)
            functions = self._deduplicate_functions(functions)

            return file_description, functions
        except Exception as e:
            print(f"Error parsing {file_path}: {e}")
            return None, []

    def _extract_file_description(self, content: str, ext: str) -> Optional[str]:
        """Extract file-level description from top of file comments."""
        lines = content.split('\n')

        # Python: Look for module docstring
        if ext == ".py":
            # Triple quote docstring at start
            match = re.match(r'^("""|\'\'\')(.*?)(\1)', content, re.DOTALL)
            if match:
                return match.group(2).strip()

        # JavaScript/TypeScript: Look for /** */ comment at start
        if ext in [".js", ".jsx", ".ts", ".tsx"]:
            match = re.match(r'^\s*/\*\*(.*?)\*/', content, re.DOTALL)
            if match:
                desc = match.group(1).strip()
                # Clean up * at start of lines
                desc = re.sub(r'^\s*\*\s?', '', desc, flags=re.MULTILINE)
                return desc.strip()

        # Rust: Look for //! comments at start
        if ext == ".rs":
            doc_lines = []
            for line in lines:
                if line.strip().startswith("//!"):
                    doc_lines.append(line.strip()[3:].strip())
                elif line.strip() and not line.strip().startswith("//"):
                    break
            if doc_lines:
                return " ".join(doc_lines)

        # C#: Look for /// <summary> or /** */ comments
        if ext == ".cs":
            # Look for XML doc comments at the start of the file
            summary_match = re.match(
                r'\s*///\s*<summary>(.*?)</summary>', content, re.DOTALL)
            if summary_match:
                # Clean up the extracted summary
                summary = summary_match.group(1)
                summary = re.sub(r'\s*///\s?', '', summary)
                return summary.strip().replace('\r\n', ' ').replace('\n', ' ')

            # Look for Javadoc-style comments at the start
            js_match = re.match(r'^\s*/\*\*(.*?)\*/', content, re.DOTALL)
            if js_match:
                desc = js_match.group(1).strip()
                desc = re.sub(r'^\s*\*\s?', '', desc, flags=re.MULTILINE)
                return desc.strip()

        return None

    def _extract_function_description(self, content: str, line_num: int, language: str) -> Optional[str]:
        """Extract function description from comments above the function."""
        lines = content.split('\n')
        if line_num <= 0 or line_num > len(lines):
            return None

        if language == "python":
            if line_num < len(lines):
                remaining_content = '\n'.join(lines[line_num:])
                match = re.match(r'^\s*("""|\'\'\')(.*?)(\1)',
                                 remaining_content, re.DOTALL)
                if match:
                    return match.group(2).strip().replace('\n', ' ')
            return None

        elif language in ["javascript", "typescript"]:
            content_before_function = '\n'.join(lines[:line_num-1])
            match = re.search(r'/\*\*(.*?)\*/\s*$',
                              content_before_function, re.DOTALL)
            if match:
                desc = match.group(1).strip()
                desc = re.sub(r'^\s*\* ?', '', desc, flags=re.MULTILINE)
                return desc.strip().replace('\n', ' ')
            return None

        elif language == "rust":
            comment_lines = []
            for i in range(line_num - 2, -1, -1):
                line = lines[i].strip()
                if line.startswith("///"):
                    comment_lines.insert(0, line[3:].strip())
                else:
                    break
            if comment_lines:
                return " ".join(comment_lines)

        elif language == "csharp":
            comment_lines = []
            for i in range(line_num - 2, -1, -1):
                line = lines[i].strip()
                if line.startswith("///"):
                    comment_lines.insert(0, line[3:].strip())
                else:
                    break
            if comment_lines:
                full_comment = " ".join(comment_lines)
                summary_match = re.search(
                    r'<summary>(.*?)</summary>', full_comment, re.DOTALL)
                if summary_match:
                    return summary_match.group(1).strip().replace('\n', ' ')
                return " ".join([l for l in comment_lines if not l.startswith("<")])

        return None

    def _deduplicate_functions(self, functions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        if not functions:
            return []
        function_groups = {}
        for func in functions:
            name = func["name"]
            if name not in function_groups:
                function_groups[name] = []
            function_groups[name].append(func)
        deduplicated = []
        for name, group in function_groups.items():
            if len(group) == 1:
                deduplicated.append(group[0])
            else:
                base_func = group[0].copy()
                signatures = list(dict.fromkeys(
                    [f["signature"] for f in group]))
                if len(signatures) > 1:
                    base_func["signature"] = " | ".join(signatures[:3])
                    if len(signatures) > 3:
                        base_func["signature"] += f" (and {len(signatures) - 3} more overloads)"
                descriptions = list(dict.fromkeys(
                    [f.get("description") for f in group if f.get("description")]))
                if descriptions:
                    base_func["description"] = " | ".join(descriptions[:2])
                deduplicated.append(base_func)
        return deduplicated

    def _parse_python(self, content: str) -> List[Dict[str, Any]]:
        functions = []
        func_pattern = re.compile(
            r'^(\s*)def\s+(\w+)\s*\([^)]*\)\s*(?:->\s*[^:]+)?:', re.MULTILINE)
        for match in func_pattern.finditer(content):
            line_num = content.count('\n', 0, match.start()) + 1
            description = self._extract_function_description(
                content, line_num + 1, "python")
            functions.append({
                "name": match.group(2),
                "signature": match.group(0).strip(),
                "line_number": line_num,
                "description": description,
                "indent": len(match.group(1))
            })
        return functions

    def _parse_rust(self, content: str) -> List[Dict[str, Any]]:
        functions = []
        pattern = re.compile(
            r'(?:pub\s+)?(?:async\s+)?fn\s+(\w+)\s*(<[^>]+>)?\s*\([^)]*\)\s*(?:->\s*[^{]+)?', re.MULTILINE | re.DOTALL)
        for match in pattern.finditer(content):
            line_num = content.count('\n', 0, match.start()) + 1
            description = self._extract_function_description(
                content, line_num, "rust")
            functions.append({
                "name": match.group(1),
                "signature": match.group(0).strip(),
                "line_number": line_num,
                "description": description
            })
        return functions

    def _parse_javascript(self, content: str) -> List[Dict[str, Any]]:
        functions = []
        patterns = [
            re.compile(r'(?:async\s+)?function\s\*?\s*(\w+)\s*\([^)]*\)'),
            re.compile(
                r'(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s+)?\([^)]*\)\s*=>')
        ]
        for pattern in patterns:
            for match in pattern.finditer(content):
                line_num = content.count('\n', 0, match.start()) + 1
                description = self._extract_function_description(
                    content, line_num, "javascript")
                functions.append({
                    "name": match.group(1),
                    "signature": match.group(0).strip(),
                    "line_number": line_num,
                    "description": description
                })
        return functions

    def _parse_typescript(self, content: str) -> List[Dict[str, Any]]:
        return self._parse_javascript(content)

    def _parse_csharp(self, content: str) -> List[Dict[str, Any]]:
        items = []
        type_pattern = re.compile(
            r'^\s*(?:public|private|protected|internal)?\s*(?:static|sealed|abstract)?\s*(class|struct|interface)\s+(\w+)', re.MULTILINE)
        for match in type_pattern.finditer(content):
            line_num = content.count('\n', 0, match.start()) + 1
            description = self._extract_function_description(
                content, line_num, "csharp")
            items.append({
                "name": match.group(2),
                "signature": match.group(0).strip(),
                "line_number": line_num,
                "description": description
            })

        method_pattern = re.compile(
            r'^\s*(public|private|protected|internal)?\s*(static|virtual|override|async|new|sealed|abstract)?\s*(?:[\w<>\[\],]+\s+)*?(\w+)\s*\([^)]*\)\s*(?:where\s+[^;{]+)?\s*{', re.MULTILINE)
        for match in method_pattern.finditer(content):
            func_name = match.group(3)
            if func_name in ['if', 'for', 'while', 'switch', 'return']:
                continue
            line_num = content.count('\n', 0, match.start()) + 1
            description = self._extract_function_description(
                content, line_num, "csharp")
            items.append({
                "name": func_name,
                "signature": match.group(0).strip('{').strip(),
                "line_number": line_num,
                "description": description
            })

        prop_pattern = re.compile(
            r'^\s*(public|private|protected|internal)?\s*(?:static|new)?\s*([\w<>\[\],]+)\s+(\w+)\s*{\s*get;\s*(?:private\s*)?set;\s*}', re.MULTILINE)
        for match in prop_pattern.finditer(content):
            line_num = content.count('\n', 0, match.start()) + 1
            description = self._extract_function_description(
                content, line_num, "csharp")
            items.append({
                "name": match.group(3),
                "signature": match.group(0).strip(),
                "line_number": line_num,
                "description": description
            })

        return items
