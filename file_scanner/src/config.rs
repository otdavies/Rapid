use tree_sitter::Parser;

/// Retrieves a tree-sitter parser for a given file extension.
pub fn get_parser(extension: &str) -> Option<Parser> {
    let mut parser = Parser::new();
    let language = match extension {
        "cs" => tree_sitter_c_sharp::language(),
        "py" => tree_sitter_python::language(),
        "rs" => tree_sitter_rust::language(),
        "ts" => tree_sitter_typescript::language_typescript(),
        // TODO: Add support for more languages
        _ => return None,
    };
    if parser.set_language(language).is_err() {
        // Log an error or handle it appropriately.
        // For now, returning None is consistent with other failure paths.
        return None;
    }
    Some(parser)
}

/// Retrieves a tree-sitter query string for a given file extension and compactness level.
///
/// Compactness levels determine the detail captured:
/// - `0`: Function/method names only.
/// - `1`: Signatures (name + parameters, up to body start).
/// - `2`: Signatures + preceding comments.
/// - `3`: Full definition (body + comments).
/// - Other values default to names only.
pub fn get_query(extension: &str, compactness: u8) -> Option<String> {
    let query_str = match extension {
        "cs" => match compactness {
            0 => r#"((method_declaration (identifier) @method_name))"#.to_string(),
            1 | 2 | 3 => r#"((method_declaration (identifier) @method_name body: (block) @body) @function_definition)"#.to_string(),
            _ => r#"((method_declaration (identifier) @method_name) @function_definition)"#.to_string(),
        },
        "py" => match compactness {
            0 => r#"((function_definition name: (identifier) @method_name))"#.to_string(),
            1 | 2 | 3 => r#"((function_definition name: (identifier) @method_name body: (block) @body) @function_definition)"#.to_string(),
            _ => r#"((function_definition name: (identifier) @method_name) @function_definition)"#.to_string(),
        },
        "rs" => match compactness {
            0 => r#"((function_item name: (identifier) @method_name))"#.to_string(),
            1 | 2 | 3 => r#"((function_item name: (identifier) @method_name body: (block) @body) @function_definition)"#.to_string(),
            _ => r#"((function_item name: (identifier) @method_name) @function_definition)"#.to_string(),
        },
        "ts" => {
            let base_queries = [
                ("function_declaration", "identifier", "statement_block"),
                ("method_definition", "property_identifier", "statement_block"),
            ];
            match compactness {
                0 => base_queries.iter().map(|(node_type, name_field, _body_field)| {
                    format!(r#"(({} name: ({}) @method_name))"#, node_type, name_field)
                }).collect::<Vec<_>>().join("\n"),
                1 | 2 | 3 => base_queries.iter().map(|(node_type, name_field, body_field)| {
                    format!(r#"(({} name: ({}) @method_name body: ({}) @body) @function_definition)"#, node_type, name_field, body_field)
                }).collect::<Vec<_>>().join("\n"),
                _ => base_queries.iter().map(|(node_type, name_field, _body_field)| {
                    format!(r#"(({} name: ({}) @method_name) @function_definition)"#, node_type, name_field)
                }).collect::<Vec<_>>().join("\n"),
            }
        }
        _ => return None,
    };
    Some(query_str)
}
