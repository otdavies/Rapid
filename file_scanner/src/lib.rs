use ignore::WalkBuilder;
use serde::{Deserialize, Serialize};
use std::ffi::{CStr, CString};
use std::fs;
use std::io::{BufRead, BufReader};
use std::os::raw::c_char;
use std::path::Path;
use std::sync::atomic::{AtomicBool, AtomicUsize, Ordering};
use std::sync::{Arc, Mutex};
use std::time::Instant;
use tree_sitter::{Parser, Query, QueryCursor};

// --- Data Structures for Parsed Content ---

#[derive(Serialize, Deserialize, Debug)]
struct FunctionInfo {
    name: String,
    body: Option<String>,
    comment: Option<String>,
}

#[derive(Serialize, Deserialize, Debug)]
struct FileContext {
    path: String,
    description: String,
    functions: Vec<FunctionInfo>,
}

#[derive(Serialize, Deserialize, Debug)]
struct ScanResult {
    file_contexts: Vec<FileContext>,
    debug_log: Vec<String>,
    timed_out_internally: bool,
    files_processed_before_timeout: usize,
}

// --- Data Structures for Search ---

#[derive(Serialize, Deserialize, Debug, Clone)]
struct SearchMatch {
    line_number: usize,
    context: String,
}

#[derive(Serialize, Deserialize, Debug, Clone)]
struct FileSearchResult {
    path: String,
    matches: Vec<SearchMatch>,
}

#[derive(Serialize, Deserialize, Debug)]
struct SearchServiceResult {
    results: Vec<FileSearchResult>,
    stats: SearchStats,
    debug_log: Vec<String>,
}

#[derive(Serialize, Deserialize, Debug, Default, Clone)]
struct SearchStats {
    files_scanned: usize,
    total_matches: usize,
    timed_out: bool,
}

// --- Tree-sitter Parser Setup ---

fn get_parser(extension: &str) -> Option<Parser> {
    let mut parser = Parser::new();
    let language = match extension {
        "cs" => tree_sitter_c_sharp::language(),
        "py" => tree_sitter_python::language(),
        "rs" => tree_sitter_rust::language(),
        "ts" => tree_sitter_typescript::language_typescript(),
        _ => return None,
    };
    parser.set_language(language).ok()?;
    Some(parser)
}

fn get_query(extension: &str, compactness: u8) -> Option<String> {
    let query_str = match extension {
        "cs" => match compactness {
            0 => r#"((method_declaration (identifier) @method_name))"#,
            1 => r#"
                (
                    (comment)* @comment
                    .
                    (method_declaration (identifier) @method_name) @function_definition
                )
                "#,
            _ => r#"
                (method_declaration
                    (identifier) @method_name
                    (block) @body)
                "#,
        },
        "py" => match compactness {
            0 => r#"((function_definition name: (identifier) @method_name))"#,
            1 => r#"
                (
                    (comment)* @comment
                    .
                    (function_definition name: (identifier) @method_name)
                )
                "#,
            _ => r#"
                (function_definition
                    name: (identifier) @method_name
                    body: (block) @body)
                "#,
        },
        "rs" => match compactness {
            0 => r#"((function_item name: (identifier) @method_name))"#,
            1 => r#"
                (
                    (line_comment)* @comment
                    .
                    (function_item name: (identifier) @method_name)
                )
                "#,
            _ => r#"
                (function_item
                    name: (identifier) @method_name
                    body: (block) @body)
                "#,
        },
        "ts" => match compactness {
            0 => r#"
                (function_declaration name: (identifier) @method_name)
                (method_definition name: (property_identifier) @method_name)
                "#,
            1 => r#"
                (
                    (comment)* @comment
                    .
                    (function_declaration name: (identifier) @method_name)
                )
                (
                    (comment)* @comment
                    .
                    (method_definition name: (property_identifier) @method_name)
                )
                "#,
            _ => r#"
                (function_declaration
                    name: (identifier) @method_name
                    body: (statement_block) @body)
                (method_definition
                    name: (property_identifier) @method_name
                    body: (statement_block) @body)
                "#,
        },
        _ => return None,
    };
    Some(query_str.to_string())
}

// --- Core Scanning and Parsing Logic ---

fn is_binary(path: &Path) -> bool {
    fs::read(path)
        .map(|bytes| bytes.iter().any(|&b| b == 0))
        .unwrap_or(true)
}

fn parse_file(path: &Path, compactness: u8) -> Option<FileContext> {
    if is_binary(path) {
        return None;
    }

    let extension = path.extension()?.to_str()?;
    let mut parser = get_parser(extension)?;
    let query_str = get_query(extension, compactness)?;

    let code = fs::read_to_string(path).ok()?;
    let tree = parser.parse(&code, None)?;

    let mut functions = Vec::new();
    let query = Query::new(parser.language().unwrap(), &query_str).ok()?;
    let mut cursor = QueryCursor::new();
    let matches = cursor.matches(&query, tree.root_node(), code.as_bytes());

    for mat in matches {
        let mut name = "".to_string();
        let mut body = None;
        let mut comment = None;

        for cap in mat.captures {
            let capture_name = query.capture_names()[cap.index as usize].as_str();
            let text = std::str::from_utf8(&code.as_bytes()[cap.node.byte_range()])
                .unwrap_or("")
                .to_string();
            match capture_name {
                "method_name" => name = text,
                "body" => body = Some(text),
                "comment" => comment = Some(text),
                "function_definition" => body = Some(text),
                _ => {}
            }
        }

        if !name.is_empty() {
            functions.push(FunctionInfo {
                name,
                body,
                comment,
            });
        }
    }

    Some(FileContext {
        path: path.to_str()?.to_string(),
        description: "".to_string(),
        functions,
    })
}

// --- FFI Interface ---

#[unsafe(no_mangle)]
pub unsafe extern "C" fn scan_and_parse(
    root_path_c: *const c_char,
    extensions_c: *const c_char,
    compactness_level: u8,
    timeout_milliseconds: u32, // New timeout parameter
) -> *mut c_char {
    let start_time = Instant::now();
    let mut debug_log: Vec<String> = Vec::new();

    // Initial check for timeout_milliseconds to prevent issues if it's 0
    if timeout_milliseconds == 0 {
        debug_log.push("Error: timeout_milliseconds cannot be 0. Setting to a default of 60000ms.".to_string());
        // Or handle as an error, for now, let's use a default or just log.
        // For this example, let's assume it's an error to pass 0 and return early.
        let result = ScanResult {
            file_contexts: Vec::new(),
            debug_log,
            timed_out_internally: true, // Technically not a timeout, but an invalid arg
            files_processed_before_timeout: 0,
        };
        return CString::new(serde_json::to_string(&result).unwrap_or_else(|_| "{}".to_string()))
            .map_or(std::ptr::null_mut(), |s| s.into_raw());
    }
    
    let root_path_str = unsafe {
        match CStr::from_ptr(root_path_c).to_str() {
            Ok(s) if !s.is_empty() => s,
            _ => {
                debug_log.push("Error: root_path_c is null or empty.".to_string());
                let result = ScanResult {
                    file_contexts: Vec::new(),
                    debug_log,
                    timed_out_internally: false, // Not a timeout, but an arg error
                    files_processed_before_timeout: 0,
                };
                return CString::new(serde_json::to_string(&result).unwrap_or_else(|_| "{}".to_string()))
                    .map_or(std::ptr::null_mut(), |s| s.into_raw());
            }
        }
    };
    debug_log.push(format!("Scanning root path: {}", root_path_str));

    let extensions_str = unsafe { CStr::from_ptr(extensions_c).to_str().unwrap_or("") };
    let extensions: Vec<String> = extensions_str
        .split(',')
        .map(|s| s.trim().to_string())
        .collect();
    debug_log.push(format!("Extensions to scan: {:?}", extensions));

    let root_path = Path::new(root_path_str);
    let mut walker_builder = WalkBuilder::new(root_path);
    walker_builder.git_ignore(true).git_global(true);

    // Add a fallback gitignore
    let fallback_ignore = r#"
# Binaries
*.dll
*.exe
*.so
*.a
*.lib
*.o
*.obj

# Archives
*.zip
*.tar.gz
*.rar

# Build artifacts
target/
build/
dist/
bin/
obj/

# IDE files
.vscode/
.idea/
*.suo
*.user
*.sln

# OS files
.DS_Store
Thumbs.db
"#;
    walker_builder.add_custom_ignore_filename(fallback_ignore);

    let walker = walker_builder.build_parallel();

    let (tx, rx) = std::sync::mpsc::channel();
    let debug_log_arc = Arc::new(Mutex::new(debug_log)); 
    let timed_out_internally_flag = Arc::new(AtomicBool::new(false));
    let files_processed_count = Arc::new(AtomicUsize::new(0));

    // Clone Arcs and tx for the walker's closure
    let start_time_clone = start_time; // Instant is Copy
    let timeout_milliseconds_clone = timeout_milliseconds; // u32 is Copy
    let timed_out_internally_flag_clone = Arc::clone(&timed_out_internally_flag);
    let files_processed_count_clone = Arc::clone(&files_processed_count);
    let debug_log_arc_walker_clone = Arc::clone(&debug_log_arc);
    let tx_for_closure = tx.clone(); // Clone tx before moving into closure

    walker.run(move || {
        let tx_clone = tx_for_closure.clone();
        let extensions_clone = extensions.clone(); // extensions is Vec<String>, needs clone
        let debug_log_thread_arc = Arc::clone(&debug_log_arc_walker_clone);
        let timed_out_flag_thread = Arc::clone(&timed_out_internally_flag_clone);
        let files_processed_thread_count = Arc::clone(&files_processed_count_clone);

        Box::new(move |result| {
            // Check for timeout at the beginning of each entry processing
            if timed_out_flag_thread.load(Ordering::Relaxed) {
                return ignore::WalkState::Quit;
            }
            if start_time_clone.elapsed().as_millis() as u32 > timeout_milliseconds_clone {
                if !timed_out_flag_thread.swap(true, Ordering::Relaxed) { // Ensure message logged once
                    let mut guard = debug_log_thread_arc.lock().unwrap();
                    guard.push(format!(
                        "Internal timeout of {}ms reached after processing approx. {} files.",
                        timeout_milliseconds_clone,
                        files_processed_thread_count.load(Ordering::Relaxed)
                    ));
                }
                return ignore::WalkState::Quit;
            }

            let mut thread_debug_log_guard = debug_log_thread_arc.lock().unwrap();
            
            match result {
                Ok(entry) => {
                    let path = entry.path();
                    if entry.file_type().map_or(false, |ft| ft.is_file()) {
                        files_processed_thread_count.fetch_add(1, Ordering::Relaxed); // Count file being considered
                        thread_debug_log_guard.push(format!("Processing file: {:?} (Count: {})", path, files_processed_thread_count.load(Ordering::Relaxed)));

                        if !path.extension().and_then(|s| s.to_str()).map_or(false, |actual_file_ext| extensions_clone.iter().any(|pattern_ext| pattern_ext.trim_start_matches('.') == actual_file_ext)) {
                            thread_debug_log_guard.push(format!("Skipping file with wrong extension: {:?}", path));
                            return ignore::WalkState::Continue;
                        }
                        if entry.metadata().map_or(true, |m| m.len() > 1_000_000) { // 1MB limit
                            thread_debug_log_guard.push(format!("Skipping large file: {:?}", path));
                            return ignore::WalkState::Continue;
                        }
                        if is_binary(path) { // Check if binary after size check
                             thread_debug_log_guard.push(format!("Skipping binary file: {:?}", path));
                             return ignore::WalkState::Continue;
                        }

                        if let Some(context) = parse_file(path, compactness_level) {
                            if tx_clone.send(context).is_err() {
                                // Receiver dropped, implies main thread might be quitting or channel closed
                                thread_debug_log_guard.push("Error sending context, receiver dropped.".to_string());
                                timed_out_flag_thread.store(true, Ordering::Relaxed); // Signal other threads to quit
                                return ignore::WalkState::Quit;
                            }
                        } else {
                            thread_debug_log_guard.push(format!("Failed to parse file (or skipped by parse_file): {:?}", path));
                        }
                    } else {
                        thread_debug_log_guard.push(format!("Skipping non-file: {:?}", path));
                    }
                }
                Err(err) => {
                    thread_debug_log_guard.push(format!("Error walking directory: {}", err));
                }
            }
            // Check for timeout again before continuing, in case processing took long
            if start_time_clone.elapsed().as_millis() as u32 > timeout_milliseconds_clone {
                 if !timed_out_flag_thread.swap(true, Ordering::Relaxed) {
                    let mut guard = debug_log_thread_arc.lock().unwrap();
                    guard.push(format!(
                        "Internal timeout of {}ms reached during entry processing (approx. {} files).",
                        timeout_milliseconds_clone,
                        files_processed_thread_count.load(Ordering::Relaxed)
                    ));
                }
                return ignore::WalkState::Quit;
            }
            ignore::WalkState::Continue
        })
    });

    drop(tx); // Close the sender, allows rx.iter() to complete

    let file_contexts: Vec<FileContext> = rx.iter().collect();
    let final_files_processed_count = files_processed_count.load(Ordering::Relaxed);
    let was_timed_out = timed_out_internally_flag.load(Ordering::Relaxed) || 
                        (start_time.elapsed().as_millis() as u32 > timeout_milliseconds && timeout_milliseconds > 0);


    // If timeout occurred, ensure the debug log reflects it if not already added by a thread
    if was_timed_out {
        let mut guard = debug_log_arc.lock().unwrap();
        if !guard.iter().any(|s| s.contains("Internal timeout")) {
             guard.push(format!(
                "Scan terminated due to internal timeout of {}ms (processed approx. {} files).",
                timeout_milliseconds,
                final_files_processed_count
            ));
        }
    }
    
    let final_debug_log_vec = debug_log_arc.lock().unwrap().drain(..).collect();

    let final_result = ScanResult {
        file_contexts,
        debug_log: final_debug_log_vec,
        timed_out_internally: was_timed_out,
        files_processed_before_timeout: final_files_processed_count,
    };

    let json_output = serde_json::to_string(&final_result).unwrap_or_else(|e| {
        // Fallback JSON if serialization fails
        let error_scan_result = ScanResult {
            file_contexts: Vec::new(),
            debug_log: vec![format!("Error serializing result to JSON: {}", e)],
            timed_out_internally: was_timed_out,
            files_processed_before_timeout: final_files_processed_count,
        };
        serde_json::to_string(&error_scan_result).unwrap_or_else(|_| "{\"error\":\"Failed to serialize result and fallback JSON\"}".to_string())
    });

    CString::new(json_output).map_or(std::ptr::null_mut(), |s| s.into_raw())
}

#[unsafe(no_mangle)]
pub unsafe extern "C" fn project_wide_search(
    root_path_c: *const c_char,
    search_string_c: *const c_char,
    extensions_c: *const c_char,
    context_lines_c: u8,
    timeout_ms_c: u32,
) -> *mut c_char {
    let start_time = Instant::now();
    let debug_log = Vec::new();

    let root_path_str = unsafe { CStr::from_ptr(root_path_c).to_str().unwrap_or("") };
    let search_string = unsafe { CStr::from_ptr(search_string_c).to_str().unwrap_or("") };
    let extensions_str = unsafe { CStr::from_ptr(extensions_c).to_str().unwrap_or("") };
    let extensions: Vec<&str> = extensions_str.split(',').collect();

    if root_path_str.is_empty() || search_string.is_empty() {
        let result = SearchServiceResult {
            results: vec![],
            stats: Default::default(),
            debug_log: vec!["Error: Root path or search string is empty.".to_string()],
        };
        return CString::new(serde_json::to_string(&result).unwrap()).unwrap().into_raw();
    }

    let root_path = Path::new(root_path_str);
    let walker = WalkBuilder::new(root_path).git_ignore(true).build_parallel();

    let results = Arc::new(Mutex::new(Vec::<FileSearchResult>::new()));
    let stats = Arc::new(Mutex::new(SearchStats::default()));
    let timed_out = Arc::new(AtomicBool::new(false));

    walker.run(|| {
        let results = Arc::clone(&results);
        let stats = Arc::clone(&stats);
        let timed_out = Arc::clone(&timed_out);
        let extensions = extensions.clone();
        let search_string = search_string.to_string();

        Box::new(move |entry| {
            if timed_out.load(Ordering::Relaxed) || start_time.elapsed().as_millis() as u32 > timeout_ms_c {
                timed_out.store(true, Ordering::Relaxed);
                return ignore::WalkState::Quit;
            }

            if let Ok(entry) = entry {
                if entry.file_type().map_or(false, |ft| ft.is_file()) {
                    let path = entry.path();
                    if !extensions.iter().any(|ext| path.to_str().unwrap_or("").ends_with(ext)) {
                        return ignore::WalkState::Continue;
                    }

                    if let Ok(file) = fs::File::open(path) {
                        let reader = BufReader::new(file);
                        let lines: Vec<String> = reader.lines().filter_map(Result::ok).collect();
                        let mut matches = Vec::new();

                        for (i, line) in lines.iter().enumerate() {
                            if line.contains(&search_string) {
                                let start = i.saturating_sub(context_lines_c as usize);
                                let end = (i + context_lines_c as usize + 1).min(lines.len());
                                
                                let mut context_buffer = Vec::new();
                                for (j, context_line) in lines[start..end].iter().enumerate() {
                                    if start + j == i {
                                        context_buffer.push(format!(">> {}", context_line));
                                    } else {
                                        context_buffer.push(format!("   {}", context_line));
                                    }
                                }

                                matches.push(SearchMatch {
                                    line_number: i + 1,
                                    context: context_buffer.join("\n"),
                                });
                            }
                        }

                        if !matches.is_empty() {
                            let mut stats = stats.lock().unwrap();
                            stats.total_matches += matches.len();
                            results.lock().unwrap().push(FileSearchResult {
                                path: path.to_str().unwrap().to_string(),
                                matches,
                            });
                        }
                    }
                    let mut stats = stats.lock().unwrap();
                    stats.files_scanned += 1;
                }
            }
            ignore::WalkState::Continue
        })
    });

    let mut final_stats = stats.lock().unwrap();
    final_stats.timed_out = timed_out.load(Ordering::Relaxed);

    let final_results = results.lock().unwrap().clone();
    let result = SearchServiceResult {
        results: final_results,
        stats: final_stats.clone(),
        debug_log,
    };

    let json_output = serde_json::to_string(&result).unwrap_or_else(|e| {
        format!("{{\"error\":\"Failed to serialize result: {}\"}}", e)
    });

    CString::new(json_output).unwrap().into_raw()
}

#[unsafe(no_mangle)]
pub unsafe extern "C" fn free_string(s: *mut c_char) {
    if !s.is_null() {
        // Explicitly wrap in unsafe block for clarity
        unsafe {
            let _ = CString::from_raw(s);
        }
    }
}
