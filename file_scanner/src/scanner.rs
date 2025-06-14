use crate::parsing;
use crate::structs::{FileContext, ScanResult};

use ignore::WalkBuilder;
use std::path::Path;
use std::sync::atomic::{AtomicBool, AtomicUsize, Ordering};
use std::sync::{Arc, Mutex};
use std::time::Instant;

/// Performs a file scan in the given `root_path_str` for specified `extensions`.
///
/// This function walks the directory tree, filters files by extension,
/// and parses them using `parsing::parse_file`. It handles timeouts and
/// collects results into a `ScanResult`.
///
/// # Arguments
/// * `root_path_str` - The root directory to start scanning from.
/// * `extensions` - A list of file extensions (e.g., "py", "rs") to include.
/// * `compactness_level` - Controls the detail of parsed content.
/// * `timeout_milliseconds` - Maximum duration for the scan. If 0, no internal timeout is applied,
///                            though external callers (like FFI) might still impose one.
///
/// # Returns
/// A `ScanResult` containing parsed file contexts, debug logs, and timeout status.
pub fn perform_scan(
    root_path_str: &str,
    extensions: Vec<String>, // TODO: Consider using &[String] or similar to avoid clone if called internally often.
    compactness_level: u8,
    timeout_milliseconds: u32,
    debug: bool,
) -> ScanResult {
    let start_time = Instant::now();
    let mut debug_log: Option<Vec<String>> = if debug { Some(Vec::new()) } else { None };

    if let Some(log) = &mut debug_log {
        log.push(format!("[Scanner] Scanning root path: {}", root_path_str));
        log.push(format!("[Scanner] Extensions: {:?}", extensions));
        log.push(format!("[Scanner] Compactness: {}", compactness_level));
        log.push(format!("[Scanner] Timeout (ms): {}", timeout_milliseconds));
    }

    let root_path = Path::new(root_path_str);
    if !root_path.exists() {
        if let Some(log) = &mut debug_log {
            log.push(format!(
                "[Scanner] Error: Root path does not exist: {}",
                root_path_str
            ));
        }
        return ScanResult {
            file_contexts: Vec::new(),
            debug_log,
            timed_out_internally: false,
            files_processed_before_timeout: 0,
        };
    }
    if !root_path.is_dir() {
        if let Some(log) = &mut debug_log {
            log.push(format!(
                "[Scanner] Error: Root path is not a directory: {}",
                root_path_str
            ));
        }
        return ScanResult {
            file_contexts: Vec::new(),
            debug_log,
            timed_out_internally: false,
            files_processed_before_timeout: 0,
        };
    }

    // Using parallel walk for potential performance benefits.
    // This aligns with the FFI's `scan_and_parse` original behavior.
    let mut walker_builder = WalkBuilder::new(root_path);
    walker_builder.git_ignore(true).git_global(true);
    // TODO: Consider adding fallback_ignore if this becomes the primary scanning entry point.

    let walker = walker_builder.build_parallel();

    let file_contexts_arc = Arc::new(Mutex::new(Vec::<FileContext>::new()));
    let debug_log_arc = Arc::new(Mutex::new(debug_log)); // `debug_log` is moved into the Arc.
    let timed_out_flag = Arc::new(AtomicBool::new(false));
    let files_processed_count = Arc::new(AtomicUsize::new(0));

    // Clone Arcs for the walker's closure.
    let start_time_clone = start_time; // `Instant` is Copy.
    let timeout_ms_clone = timeout_milliseconds; // `u32` is Copy.
    let timed_out_flag_clone = Arc::clone(&timed_out_flag);
    let files_processed_count_clone = Arc::clone(&files_processed_count);
    let debug_log_arc_walker = Arc::clone(&debug_log_arc);
    let file_contexts_arc_walker = Arc::clone(&file_contexts_arc);
    let extensions_clone = extensions; // `Vec<String>` is cloned for the closure.

    walker.run(move || {
        // Per-thread clones of Arcs and other necessary data.
        let file_contexts_thread_arc = Arc::clone(&file_contexts_arc_walker);
        let debug_log_thread_arc = Arc::clone(&debug_log_arc_walker);
        let timed_out_thread_flag = Arc::clone(&timed_out_flag_clone);
        let files_processed_thread_count = Arc::clone(&files_processed_count_clone);
        let extensions_thread_clone = extensions_clone.clone();

        Box::new(move |entry_result| {
            if timeout_ms_clone > 0
                && start_time_clone.elapsed().as_millis() as u32 > timeout_ms_clone
            {
                if !timed_out_thread_flag.swap(true, Ordering::Relaxed) {
                    // Log timeout only once.
                    if let Some(log) = &mut *debug_log_thread_arc.lock().unwrap() {
                        log.push(format!(
                            "[Scanner] Timeout of {}ms reached. Processed approx. {} files before stopping.",
                            timeout_ms_clone,
                            files_processed_thread_count.load(Ordering::Relaxed)
                        ));
                    }
                }
                return ignore::WalkState::Quit;
            }
            // If already timed out by another thread, quit.
            if timed_out_thread_flag.load(Ordering::Relaxed) {
                return ignore::WalkState::Quit;
            }

            let entry = match entry_result {
                Ok(e) => e,
                Err(err) => {
                    if let Some(log) = &mut *debug_log_thread_arc.lock().unwrap() {
                        log.push(format!("[Scanner] Error walking directory entry: {}", err));
                    }
                    return ignore::WalkState::Continue; // Skip problematic entries.
                }
            };

            let path = entry.path();
            if path.is_file() {
                let current_processed_count =
                    files_processed_thread_count.fetch_add(1, Ordering::Relaxed) + 1; // +1 because fetch_add returns previous value.
                let ext_str = path.extension().and_then(|s| s.to_str()).unwrap_or("");

                if let Some(log) = &mut *debug_log_thread_arc.lock().unwrap() {
                    log.push(format!(
                        "[Scanner] ({}) Processing: {:?}, ext: {}",
                        current_processed_count, path, ext_str
                    ));
                }

                if !extensions_thread_clone
                    .iter()
                    .any(|e| e.trim_start_matches('.') == ext_str)
                {
                    if let Some(log) = &mut *debug_log_thread_arc.lock().unwrap() {
                        log.push(format!("[Scanner] Skipping (extension mismatch): {:?}", path));
                    }
                    return ignore::WalkState::Continue;
                }

                // File size check (1MB limit).
                if entry.metadata().map_or(true, |m| m.len() > 1_000_000) {
                    if let Some(log) = &mut *debug_log_thread_arc.lock().unwrap() {
                        log.push(format!("[Scanner] Skipping (large file >1MB): {:?}", path));
                    }
                    return ignore::WalkState::Continue;
                }
                // Note: `is_binary` check is handled within `parsing::parse_file`.

                if let Some(context) = parsing::parse_file(path, compactness_level) {
                    if !context.functions.is_empty() {
                        file_contexts_thread_arc.lock().unwrap().push(context);
                    } else {
                        if let Some(log) = &mut *debug_log_thread_arc.lock().unwrap() {
                            log.push(format!("[Scanner] No functions extracted from: {:?}", path));
                        }
                    }
                } else {
                    // `parse_file` returns `None` if binary, unreadable, or no relevant content found.
                    if let Some(log) = &mut *debug_log_thread_arc.lock().unwrap() {
                        log.push(format!(
                            "[Scanner] Skipping (failed to parse or no relevant content): {:?}",
                            path
                        ));
                    }
                }
            }
            ignore::WalkState::Continue
        })
    });

    // Attempt to unwrap Arcs. This should succeed if the walker has finished.
    // Provide default empty Vecs on error to prevent panic, though this indicates an issue.
    let final_file_contexts = Arc::try_unwrap(file_contexts_arc)
        .unwrap_or_else(|arc| {
            // This case should ideally not be reached if walker completes.
            // Log or handle error appropriately if Arc is still shared.
            eprintln!("[Scanner] Warning: file_contexts_arc still shared after walk.");
            Mutex::new(arc.lock().unwrap().clone()) // Clone data if still shared.
        })
        .into_inner()
        .unwrap_or_default();

    let final_debug_log = Arc::try_unwrap(debug_log_arc)
        .unwrap_or_else(|arc| {
            eprintln!("[Scanner] Warning: debug_log_arc still shared after walk.");
            Mutex::new(arc.lock().unwrap().clone())
        })
        .into_inner()
        .unwrap_or_default();

    let final_files_processed_count = files_processed_count.load(Ordering::Relaxed);
    let was_timed_out = timed_out_flag.load(Ordering::Relaxed);

    ScanResult {
        file_contexts: final_file_contexts,
        debug_log: final_debug_log,
        timed_out_internally: was_timed_out,
        files_processed_before_timeout: final_files_processed_count,
    }
}
