use crate::embedding;
use crate::scanner;
use crate::structs::{
    ConceptSearchResultItem, ConceptSearchServiceResult, ConceptSearchStats, FileSearchResult,
    ScanResult, SearchMatch, SearchServiceResult, SearchStats,
};
use crate::utils;

use ignore::WalkBuilder;
use rayon::prelude::*;
use std::ffi::{CStr, CString};
use std::fs;
use std::io::{BufRead, BufReader};
use std::os::raw::c_char;
use std::path::Path;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, Mutex};
use std::time::Instant;

// Helper function for concept_search, kept close to its FFI counterpart
fn concept_search_inner(
    root_path_str: &str,
    query_str: &str,
    extensions: Vec<String>,
    top_n: usize,
    timeout_ms: u32,
    debug: bool,
) -> Result<ConceptSearchServiceResult, anyhow::Error> {
    let start_time = Instant::now();
    let cache_dir = Path::new(root_path_str).join("file_scanner").join(".cache");
    let mut debug_log_accumulator: Option<Vec<String>> =
        if debug { Some(Vec::new()) } else { None };

    if let Some(log_acc) = &mut debug_log_accumulator {
        log_acc.push(format!(
            "[ConceptSearchInner] START. Debug: {}, Extensions: {:?}, Query: '{}', Path: '{}'",
            debug, extensions, query_str, root_path_str
        ));
    }

    // 1. Get all functions using the scanner module
    let scan_result = scanner::perform_scan(root_path_str, extensions, 3, timeout_ms, debug);
    if debug {
        if let Some(scan_log) = scan_result.debug_log {
            debug_log_accumulator
                .get_or_insert_with(Vec::new)
                .extend(scan_log);
        }
    }

    let documents: Vec<String> = scan_result
        .file_contexts
        .par_iter()
        .flat_map_iter(|fc| {
            fc.functions.iter().map(|f| {
                format!(
                    "Function: {}\nFile: {}\nBody:\n{}",
                    f.name,
                    fc.path,
                    f.body.as_deref().unwrap_or("")
                )
            })
        })
        .collect();

    let doc_identifiers: Vec<_> = scan_result
        .file_contexts
        .par_iter()
        .flat_map_iter(|fc| {
            fc.functions.iter().map(move |f| {
                (
                    fc.path.clone(),
                    f.name.clone(),
                    f.body.clone(),
                )
            })
        })
        .collect();

    if documents.is_empty() {
        if let Some(log_ref) = &mut debug_log_accumulator {
            log_ref.push("[ConceptSearch] No documents found to embed.".to_string());
        }
        return Ok(ConceptSearchServiceResult {
            results: vec![],
            stats: ConceptSearchStats {
                functions_analyzed: 0,
                search_duration_seconds: start_time.elapsed().as_secs_f32(),
            },
            error: Some(
                "No documents were found to embed. The initial scan may have found no functions."
                    .to_string(),
            ),
            debug_log: debug_log_accumulator,
        });
    }
    if let Some(log_ref) = &mut debug_log_accumulator {
        log_ref.push(format!(
            "[ConceptSearch] Found {} documents to embed.",
            documents.len()
        ));
    }

    // 2. Embed query and documents
    let model = embedding::MODEL.get_or_try_init(|| embedding::initialize_model(&cache_dir))?;
    if let Some(log_ref) = &mut debug_log_accumulator {
        log_ref.push("[ConceptSearch] Embedding model initialized/retrieved.".to_string());
    }

    let mut query_embeddings = model.embed(vec![query_str.to_string()], None)?;
    if query_embeddings.is_empty() {
        if let Some(log_ref) = &mut debug_log_accumulator {
            log_ref.push("[ConceptSearch] Error: Failed to embed query string.".to_string());
        }
        return Err(anyhow::anyhow!("Failed to embed query string."));
    }
    let query_embedding = query_embeddings.remove(0);
    if let Some(log_ref) = &mut debug_log_accumulator {
        log_ref.push("[ConceptSearch] Query embedded successfully.".to_string());
    }

    let doc_embeddings = model.embed(documents, None)?;
    if let Some(log_ref) = &mut debug_log_accumulator {
        log_ref.push(format!(
            "[ConceptSearch] {} documents embedded successfully.",
            doc_embeddings.len()
        ));
    }

    // 3. Cosine similarity
    let mut similarities: Vec<(usize, f32)> = doc_embeddings
        .par_iter()
        .enumerate()
        .map(|(i, doc_emb)| {
            let sim = utils::cosine_similarity(&query_embedding, doc_emb);
            (i, sim)
        })
        .collect();

    similarities.par_sort_by(|a, b| b.1.partial_cmp(&a.1).unwrap_or(std::cmp::Ordering::Equal));
    if let Some(log_ref) = &mut debug_log_accumulator {
        log_ref.push("[ConceptSearch] Similarities calculated and sorted.".to_string());
    }

    // 4. Get top N results
    let results: Vec<ConceptSearchResultItem> = similarities
        .iter()
        .take(top_n)
        .map(|(idx, sim)| ConceptSearchResultItem {
            file: doc_identifiers[*idx].0.clone(),
            function: doc_identifiers[*idx].1.clone(),
            similarity: *sim,
            body: doc_identifiers[*idx].2.clone(),
        })
        .collect();
    if let Some(log_ref) = &mut debug_log_accumulator {
        log_ref.push(format!(
            "[ConceptSearch] Top {} results collected.",
            results.len()
        ));
    }

    Ok(ConceptSearchServiceResult {
        results,
        stats: ConceptSearchStats {
            functions_analyzed: doc_identifiers.len(),
            search_duration_seconds: start_time.elapsed().as_secs_f32(),
        },
        error: None,
        debug_log: debug_log_accumulator,
    })
}

/// # Safety
///
/// This function is unsafe because it dereferences raw pointers passed from C.
/// The caller must ensure that `root_path_c` and `extensions_c` are valid, non-null,
/// null-terminated UTF-8 encoded strings. The memory pointed to by these pointers
/// must remain valid for the duration of this call.
/// The returned `*mut c_char` must be deallocated by the C caller using `free_string`.
#[no_mangle]
pub unsafe extern "C" fn scan_and_parse(
    root_path_c: *const c_char,
    extensions_c: *const c_char,
    compactness_level: u8,
    timeout_milliseconds: u32,
    debug_c: bool,
) -> *mut c_char {
    if timeout_milliseconds == 0 {
        let err_result = ScanResult {
            file_contexts: Vec::new(),
            debug_log: if debug_c {
                Some(vec!["Error: timeout_milliseconds cannot be 0.".to_string()])
            } else {
                None
            },
            timed_out_internally: true,
            files_processed_before_timeout: 0,
        };
        return CString::new(serde_json::to_string(&err_result).unwrap_or_default())
            .map_or(std::ptr::null_mut(), |s| s.into_raw());
    }

    let root_path_str = match CStr::from_ptr(root_path_c).to_str() {
        Ok(s) if !s.is_empty() => s,
        _ => {
            let err_result = ScanResult {
                file_contexts: Vec::new(),
                debug_log: if debug_c {
                    Some(vec![
                        "Error: root_path_c is null, empty, or invalid UTF-8.".to_string()
                    ])
                } else {
                    None
                },
                timed_out_internally: false,
                files_processed_before_timeout: 0,
            };
            return CString::new(serde_json::to_string(&err_result).unwrap_or_default())
                .map_or(std::ptr::null_mut(), |s| s.into_raw());
        }
    };

    let extensions_str = CStr::from_ptr(extensions_c).to_str().unwrap_or("");
    let extensions: Vec<String> = extensions_str
        .split(',')
        .map(|s| s.trim().to_string())
        .filter(|s| !s.is_empty())
        .collect();

    if extensions.is_empty() {
        let err_result = ScanResult {
            file_contexts: Vec::new(),
            debug_log: if debug_c {
                Some(vec![
                    "Error: extensions_c is null, empty, or resulted in no valid extensions."
                        .to_string(),
                ])
            } else {
                None
            },
            timed_out_internally: false,
            files_processed_before_timeout: 0,
        };
        return CString::new(serde_json::to_string(&err_result).unwrap_or_default())
            .map_or(std::ptr::null_mut(), |s| s.into_raw());
    }

    let scan_result = scanner::perform_scan(
        root_path_str,
        extensions,
        compactness_level,
        timeout_milliseconds,
        debug_c, // Pass debug flag
    );

    let json_output = serde_json::to_string(&scan_result).unwrap_or_else(|e| {
        let mut current_debug_log = scan_result.debug_log; // This is already an Option
        if debug_c {
            current_debug_log.get_or_insert_with(Vec::new).push(format!("Error serializing result to JSON: {}", e));
        }

        let error_fallback = ScanResult {
            file_contexts: Vec::new(),
            debug_log: current_debug_log,
            timed_out_internally: scan_result.timed_out_internally,
            files_processed_before_timeout: scan_result.files_processed_before_timeout,
        };
        serde_json::to_string(&error_fallback).unwrap_or_else(|_| {
            if debug_c {
                "{\"error\":\"Failed to serialize result and fallback JSON\", \"debug_log\":[\"Serialization double fault\"]}".to_string()
            } else {
                "{\"error\":\"Failed to serialize result and fallback JSON\"}".to_string()
            }
        })
    });

    CString::new(json_output).map_or(std::ptr::null_mut(), |s| s.into_raw())
}

/// # Safety
///
/// This function is unsafe because it dereferences raw pointers passed from C.
/// The caller must ensure that `root_path_c`, `query_c`, and `extensions_c`
/// are valid, non-null, null-terminated UTF-8 encoded strings.
/// The memory pointed to by these pointers must remain valid for the duration of this call.
/// The returned `*mut c_char` must be deallocated by the C caller using `free_string`.
#[no_mangle]
pub unsafe extern "C" fn concept_search(
    root_path_c: *const c_char,
    query_c: *const c_char,
    extensions_c: *const c_char,
    top_n_c: usize,
    timeout_ms_c: u32,
    debug_c: bool,
) -> *mut c_char {
    // Create a temporary debug log for FFI entry diagnostics
    let mut ffi_entry_debug_log: Option<Vec<String>> = if debug_c { Some(Vec::new()) } else { None };
    if let Some(log) = &mut ffi_entry_debug_log {
        log.push(format!("[FFI concept_search] Received debug_c: {}", debug_c));
    }

    let root_path_str = CStr::from_ptr(root_path_c).to_str().unwrap_or_default();
    let query_str = CStr::from_ptr(query_c).to_str().unwrap_or_default();
    let extensions_json_str = CStr::from_ptr(extensions_c).to_str().unwrap_or_default();

    if root_path_str.is_empty() || query_str.is_empty() || extensions_json_str.is_empty() {
        let mut error_msg = "Error: One or more C string arguments (root_path, query, extensions) are null, empty or invalid UTF-8.".to_string();
        // Use ffi_entry_debug_log here
        let mut current_debug_log = ffi_entry_debug_log;
        if debug_c { // This check is somewhat redundant if ffi_entry_debug_log is already Some if debug_c is true
            error_msg = format!("[DEBUG_C_TRUE_EARLY_EXIT_1] {}", error_msg);
            current_debug_log.get_or_insert_with(Vec::new).push("Forced debug log for early exit 1".to_string());
        } else {
            error_msg = format!("[DEBUG_C_FALSE_EARLY_EXIT_1] {}", error_msg);
            // If debug_c is false, current_debug_log is None. No need to add to it.
        }

        let error_result = ConceptSearchServiceResult {
            results: vec![],
            stats: ConceptSearchStats::default(),
            error: Some(error_msg),
            debug_log: current_debug_log, // Use the potentially populated ffi_entry_debug_log
        };
        let json_output = serde_json::to_string(&error_result).unwrap_or_default();
        return CString::new(json_output).map_or(std::ptr::null_mut(), |s| s.into_raw());
    }

    let extensions: Vec<String> = match serde_json::from_str(extensions_json_str) {
        Ok(exts) => exts,
        Err(e) => {
            // Use ffi_entry_debug_log here
            let mut current_debug_log = ffi_entry_debug_log;
            if debug_c { // This check is somewhat redundant
                 current_debug_log.get_or_insert_with(Vec::new).push(format!("Error parsing extensions_json_str: {}", e));
            }

            let error_result = ConceptSearchServiceResult {
                results: vec![],
                stats: ConceptSearchStats::default(),
                error: Some(format!(
                    "Failed to parse extensions JSON: {}. Input was: '{}'",
                    e, extensions_json_str
                )),
                debug_log: current_debug_log, // Use the potentially populated ffi_entry_debug_log
            };
            let json_output = serde_json::to_string(&error_result).unwrap_or_default();
            return CString::new(json_output).map_or(std::ptr::null_mut(), |s| s.into_raw());
        }
    };

    // If we pass the initial checks, call concept_search_inner
    // concept_search_inner will create its own debug_log_accumulator based on debug_c
    // We need to merge ffi_entry_debug_log with the one from concept_search_inner
    let mut inner_result = match concept_search_inner(
        root_path_str,
        query_str,
        extensions,
        top_n_c,
        timeout_ms_c,
        debug_c, // Pass the received debug_c
    ) {
        Ok(mut res) => {
            // Prepend ffi_entry_debug_log to the logs from concept_search_inner
            if let Some(mut entry_logs) = ffi_entry_debug_log {
                if let Some(inner_logs) = res.debug_log.take() {
                    entry_logs.extend(inner_logs);
                }
                res.debug_log = Some(entry_logs);
            } else {
                // If ffi_entry_debug_log was None (debug_c was false),
                // res.debug_log from inner will also be None.
            }
            res
        }
        Err(e) => {
            let mut current_debug_log = ffi_entry_debug_log;
            if debug_c { // This check is somewhat redundant
                current_debug_log.get_or_insert_with(Vec::new).push(e.to_string());
            }
            ConceptSearchServiceResult {
                results: vec![],
                stats: ConceptSearchStats::default(),
                error: Some(format!("Concept search internal error: {:?}", e)),
                debug_log: current_debug_log,
            }
        }
    };

    let json_output = serde_json::to_string(&inner_result).unwrap_or_else(|e| {
        // Attempt to use the debug log from inner_result if serialization fails
        let mut current_debug_log = inner_result.debug_log;
        if debug_c { // This check is somewhat redundant
            current_debug_log.get_or_insert_with(Vec::new).push(format!("Failed to serialize concept search result: {}", e));
        }
        let fallback_error = ConceptSearchServiceResult {
            results: vec![],
            stats: ConceptSearchStats::default(),
            error: Some(format!("Failed to serialize concept search result: {}", e)),
            debug_log: current_debug_log,
        };
        serde_json::to_string(&fallback_error).unwrap_or_else(|_| {
            if debug_c {
                 "{\"error\":\"Failed to serialize concept search result and fallback JSON\", \"debug_log\":[\"Serialization double fault\"]}".to_string()
            } else {
                "{\"error\":\"Failed to serialize concept search result and fallback JSON\"}".to_string()
            }
        })
    });
    CString::new(json_output).map_or(std::ptr::null_mut(), |s| s.into_raw())
}

/// # Safety
///
/// This function is unsafe because it dereferences raw pointers passed from C.
/// The caller must ensure that `root_path_c`, `search_string_c`, and `extensions_c`
/// are valid, non-null, null-terminated UTF-8 encoded strings.
/// The memory pointed to by these pointers must remain valid for the duration of this call.
/// The returned `*mut c_char` must be deallocated by the C caller using `free_string`.
#[no_mangle]
pub unsafe extern "C" fn project_wide_search(
    root_path_c: *const c_char,
    search_string_c: *const c_char,
    extensions_c: *const c_char,
    context_lines_c: u8,
    timeout_ms_c: u32,
    debug_c: bool,
) -> *mut c_char {
    let start_time = Instant::now();
    let mut debug_log: Option<Vec<String>> = if debug_c { Some(Vec::new()) } else { None };

    let root_path_str = match CStr::from_ptr(root_path_c).to_str() {
        Ok(s) if !s.is_empty() => s,
        _ => {
            let result = SearchServiceResult {
                results: vec![],
                stats: Default::default(),
                debug_log: if debug_c {
                    Some(vec![
                        "Error: Root path is null, empty, or invalid UTF-8.".to_string()
                    ])
                } else {
                    None
                },
            };
            return CString::new(serde_json::to_string(&result).unwrap_or_default())
                .map_or(std::ptr::null_mut(), |s| s.into_raw());
        }
    };
    let search_string = match CStr::from_ptr(search_string_c).to_str() {
        Ok(s) if !s.is_empty() => s,
        _ => {
            let result = SearchServiceResult {
                results: vec![],
                stats: Default::default(),
                debug_log: if debug_c {
                    Some(vec![
                        "Error: Search string is null, empty, or invalid UTF-8.".to_string(),
                    ])
                } else {
                    None
                },
            };
            return CString::new(serde_json::to_string(&result).unwrap_or_default())
                .map_or(std::ptr::null_mut(), |s| s.into_raw());
        }
    };
    let extensions_str = CStr::from_ptr(extensions_c).to_str().unwrap_or("");
    let extensions: Vec<&str> = extensions_str
        .split(',')
        .map(|s| s.trim())
        .filter(|s| !s.is_empty())
        .collect();

    if extensions.is_empty() {
        let result = SearchServiceResult {
            results: vec![],
            stats: Default::default(),
            debug_log: if debug_c {
                Some(vec![
                    "Error: Extensions string is empty or resulted in no valid extensions."
                        .to_string(),
                ])
            } else {
                None
            },
        };
        return CString::new(serde_json::to_string(&result).unwrap_or_default())
            .map_or(std::ptr::null_mut(), |s| s.into_raw());
    }

    if let Some(log) = &mut debug_log {
        log.push(format!(
            "[ProjectSearch] Root: {}, Query: '{}', Exts: {:?}, Timeout: {}ms",
            root_path_str, search_string, extensions, timeout_ms_c
        ));
    }

    let root_path = Path::new(root_path_str);
    let walker = WalkBuilder::new(root_path)
        .git_ignore(true) // Standard gitignore behavior
        .git_global(true) // Include global gitignore
        .build_parallel();

    let results_arc = Arc::new(Mutex::new(Vec::<FileSearchResult>::new()));
    let stats_arc = Arc::new(Mutex::new(SearchStats::default()));
    let timed_out_arc = Arc::new(AtomicBool::new(false));
    let debug_log_arc = Arc::new(Mutex::new(debug_log));

    walker.run(|| {
        let results_arc_box = Arc::clone(&results_arc); 
        let stats_arc_box = Arc::clone(&stats_arc); 
        let timed_out_clone_box = Arc::clone(&timed_out_arc); 
        let local_extensions_clone_box: Vec<String> =
            extensions.iter().map(|&s| s.to_string()).collect();
        let search_string_clone_box = search_string.to_string(); 
        let debug_log_arc_clone_box = Arc::clone(&debug_log_arc); 

        Box::new(move |entry_result| {
            if debug_c {
                if timeout_ms_c > 0 && start_time.elapsed().as_millis() as u32 > timeout_ms_c {
                    if !timed_out_clone_box.swap(true, Ordering::Relaxed) {
                        if let Ok(mut guard) = debug_log_arc_clone_box.lock() {
                            if let Some(log_vec) = guard.as_mut() {
                                log_vec.push(
                                    "[ProjectSearch] Timeout reached during walk.".to_string(),
                                );
                            }
                        }
                    }
                    return ignore::WalkState::Quit;
                }
                if timed_out_clone_box.load(Ordering::Relaxed) {
                    return ignore::WalkState::Quit;
                }
            } else {
                if timeout_ms_c > 0 && start_time.elapsed().as_millis() as u32 > timeout_ms_c {
                    timed_out_clone_box.swap(true, Ordering::Relaxed);
                    return ignore::WalkState::Quit;
                }
                if timed_out_clone_box.load(Ordering::Relaxed) {
                    return ignore::WalkState::Quit;
                }
            }

            if let Ok(entry) = entry_result {
                if entry.file_type().is_some_and(|ft| ft.is_file()) {
                    let path = entry.path();
                    if !local_extensions_clone_box.iter().any(|ext| {
                        path.to_str()
                            .unwrap_or("")
                            .ends_with(ext.trim_start_matches('.'))
                    }) {
                        return ignore::WalkState::Continue;
                    }

                    if entry.metadata().map_or(true, |m| m.len() > 5_000_000) {
                        if debug_c {
                            if let Ok(mut guard) = debug_log_arc_clone_box.lock() {
                                if let Some(log_vec) = guard.as_mut() {
                                    log_vec.push(format!(
                                        "[ProjectSearch] Skipping large file (5MB+): {:?}",
                                        path
                                    ));
                                }
                            }
                        }
                        return ignore::WalkState::Continue;
                    }
                    if utils::is_binary(path) {
                        if debug_c {
                            if let Ok(mut guard) = debug_log_arc_clone_box.lock() {
                                if let Some(log_vec) = guard.as_mut() {
                                    log_vec.push(format!(
                                        "[ProjectSearch] Skipping binary file: {:?}",
                                        path
                                    ));
                                }
                            }
                        }
                        return ignore::WalkState::Continue;
                    }

                    if let Ok(file) = fs::File::open(path) {
                        let reader = BufReader::new(file);
                        let lines: Vec<String> = reader.lines().map_while(Result::ok).collect();
                        let mut file_matches = Vec::new();

                        for (i, line) in lines.iter().enumerate() {
                            if line.contains(&search_string_clone_box) { // Corrected variable
                                let start_context = i.saturating_sub(context_lines_c as usize);
                                let end_context =
                                    (i + context_lines_c as usize + 1).min(lines.len());

                                let mut context_buffer = Vec::new();
                                for (j, context_line) in
                                    lines[start_context..end_context].iter().enumerate()
                                {
                                    if start_context + j == i {
                                        context_buffer.push(format!(">> {}", context_line));
                                    } else {
                                        context_buffer.push(format!("   {}", context_line));
                                    }
                                }
                                file_matches.push(SearchMatch {
                                    line_number: i + 1, 
                                    context: context_buffer.join("\n"),
                                });
                            }
                        }

                        if !file_matches.is_empty() {
                            let mut stats_guard = stats_arc_box.lock().unwrap(); 
                            stats_guard.total_matches += file_matches.len();
                            results_arc_box.lock().unwrap().push(FileSearchResult { 
                                path: path.to_str().unwrap_or_default().to_string(),
                                matches: file_matches,
                            });
                        }
                    }
                    stats_arc_box.lock().unwrap().files_scanned += 1; 
                }
            }
            ignore::WalkState::Continue
        })
    });

    let mut final_stats = stats_arc.lock().unwrap().clone(); 
    final_stats.timed_out = timed_out_arc.load(Ordering::Relaxed); 

    let final_results = results_arc.lock().unwrap().clone(); 
    let final_debug_log_val = if debug_c {
        debug_log_arc.lock().unwrap().clone()
    } else {
        None
    };

    let result = SearchServiceResult {
        results: final_results,
        stats: final_stats,
        debug_log: final_debug_log_val,
    };

    let json_output = serde_json::to_string(&result).unwrap_or_else(|e| {
        let mut current_debug_log = result.debug_log; 
         if debug_c {
            current_debug_log.get_or_insert_with(Vec::new).push(format!("Failed to serialize project_wide_search result: {}", e));
        }
        if debug_c {
            format!(
                "{{\"error\":\"Failed to serialize project_wide_search result: {}\", \"debug_log\":[\"Serialization error\"]}}",
                e
            )
        } else {
             format!(
                "{{\"error\":\"Failed to serialize project_wide_search result: {}\"}}",
                e
            )
        }
    });

    CString::new(json_output).map_or(std::ptr::null_mut(), |s| s.into_raw())
}

/// # Safety
///
/// This function is unsafe because it dereferences a raw pointer `s` passed from C.
/// The caller must ensure that `s` was previously allocated by a Rust function that
/// returned a `CString::into_raw` pointer (e.g., `scan_and_parse`, `concept_search`,
/// `project_wide_search`) and that it has not been freed yet.
/// This function takes ownership of the memory and deallocates it.
/// Calling this function with a null pointer or an already freed pointer is undefined behavior.
#[no_mangle]
pub unsafe extern "C" fn free_string(s: *mut c_char) {
    if !s.is_null() {
        let _ = CString::from_raw(s);
    }
}
