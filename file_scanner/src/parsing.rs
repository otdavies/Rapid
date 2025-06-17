use crate::config;
use crate::structs::{FileContext, FunctionInfo};
use crate::utils;
use std::fs;
use std::path::Path;
use tree_sitter::{Query, QueryCursor};

/// Parses a single file to extract function information using tree-sitter.
///
/// # Arguments
/// * `path` - Path to the file.
/// * `compactness` - Controls the detail of extracted function information.
///
/// # Returns
/// `Some(FileContext)` if parsing succeeds and functions are found, otherwise `None`.
/// Returns `None` for binary files, unreadable files, or if no functions are extracted.
pub fn parse_file(path: &Path, compactness: u8) -> Option<FileContext> {
    if utils::is_binary(path) {
        return None;
    }

    let extension = path.extension().and_then(|ext| ext.to_str())?;
    let mut parser = config::get_parser(extension)?;
    let query_str = config::get_query(extension, compactness)?;

    let code = fs::read_to_string(path).ok()?;
    let tree = parser.parse(&code, None)?;

    let mut functions = Vec::new();
    let query = match Query::new(
        parser
            .language()
            .expect("Language should be set if parser was obtained"),
        &query_str,
    ) {
        Ok(q) => q,
        Err(_e) => {
            // Error creating query, e.g., due to syntax issues in the query string.
            // eprintln!("[Parsing] Error creating query for {:?}: {}", path, _e);
            return None;
        }
    };

    let mut cursor = QueryCursor::new();
    let matches = cursor.matches(&query, tree.root_node(), code.as_bytes());

    for mat in matches {
        let mut name = String::new();
        let mut comment: Option<String> = None;
        let mut function_definition_node: Option<tree_sitter::Node> = None;
        let mut body_node: Option<tree_sitter::Node> = None;

        for cap in mat.captures {
            let capture_name_result = query.capture_names().get(cap.index as usize);
            // This check ensures that the capture index is valid for the query's capture names.
            // It should not fail with correctly constructed queries and tree-sitter behavior.
            if capture_name_result.is_none() {
                // eprintln!("[Parsing] Warning: Invalid capture index {} for query in file {:?}", cap.index, path);
                continue;
            }

            let capture_name = capture_name_result.unwrap().as_str(); // Safe due to the check above.
            let node = cap.node;
            let node_text = node.utf8_text(code.as_bytes()).unwrap_or("").to_string();

            match capture_name {
                "method_name" | "name" => name = node_text, // "name" is used in Python queries.
                "comment" => comment = Some(node_text),
                "function_definition" => function_definition_node = Some(node),
                "body" => body_node = Some(node),
                _ => {} // Ignore other captures not relevant for FunctionInfo.
            }
        }

        if !name.is_empty() {
            let body_content = match compactness {
                1 | 2 => {
                    // Signature only (compactness 1) or signature + comment (compactness 2).
                    if let (Some(def_node), Some(b_node)) = (function_definition_node, body_node) {
                        let body_start_byte = b_node.start_byte();
                        let def_start_byte = def_node.start_byte();
                        // Extract text from start of definition up to start of body.
                        if body_start_byte > def_start_byte {
                            Some(code[def_start_byte..body_start_byte].trim().to_string())
                        } else {
                            // Fallback for compact definitions or if body_start isn't strictly after def_start.
                            function_definition_node.map(|n| {
                                n.utf8_text(code.as_bytes())
                                    .unwrap_or("")
                                    .trim()
                                    .to_string()
                            })
                        }
                    } else {
                        // Fallback if body node isn't captured, use full definition node text.
                        function_definition_node.map(|n| {
                            n.utf8_text(code.as_bytes())
                                .unwrap_or("")
                                .trim()
                                .to_string()
                        })
                    }
                }
                3 => {
                    // Full function body (compactness 3).
                    // For concept search, we want the entire function definition.
                    function_definition_node.map(|n| {
                        n.utf8_text(code.as_bytes())
                            .unwrap_or("")
                            .trim()
                            .to_string()
                    })
                }
                _ => None, // Compactness 0 (name only) or other invalid levels: no body content.
            };

            functions.push(FunctionInfo {
                name,
                body: body_content,
                comment: if compactness >= 2 { comment } else { None }, // Include comment only if compactness is 2 or 3.
            });
        }
    }

    if functions.is_empty() {
        return None;
    }

    Some(FileContext {
        path: path.to_str()?.to_string(),
        description: String::new(), // TODO: Determine how to populate FileContext::description meaningfully.
        functions,
    })
}
