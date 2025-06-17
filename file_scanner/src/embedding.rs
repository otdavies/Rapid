use anyhow::Context as AnyhowContext; // Alias to avoid conflict with struct Context if any
use fastembed::{EmbeddingModel, InitOptions, TextEmbedding};
use once_cell::sync::OnceCell;
use std::fs;
use std::path::Path;
use std::sync::{Arc, Mutex};
use tracing_subscriber::{fmt, EnvFilter};

pub static MODEL: OnceCell<TextEmbedding> = OnceCell::new();

// LogWriter captures tracing logs during model initialization.
struct LogWriter {
    buffer: Arc<Mutex<Vec<u8>>>,
}

impl std::io::Write for LogWriter {
    fn write(&mut self, buf: &[u8]) -> std::io::Result<usize> {
        let mut guard = self.buffer.lock().unwrap_or_else(|poisoned| {
            // Attempt to recover from a poisoned lock, though unlikely in this specific usage.
            eprintln!("[Embedding] LogWriter buffer lock poisoned: {}", poisoned);
            poisoned.into_inner()
        });
        guard.extend_from_slice(buf);
        Ok(buf.len())
    }

    fn flush(&mut self) -> std::io::Result<()> {
        Ok(())
    }
}

/// Initializes the TextEmbedding model, sets up tracing for initialization logs,
/// and configures the cache directory for Hugging Face models.
pub fn initialize_model(cache_dir: &Path) -> Result<TextEmbedding, anyhow::Error> {
    let log_buffer = Arc::new(Mutex::new(Vec::new()));
    let log_buffer_for_writer = Arc::clone(&log_buffer);

    let make_writer = move || LogWriter {
        buffer: Arc::clone(&log_buffer_for_writer),
    };

    // Configure tracing to capture logs specifically from `hf-hub` during initialization.
    // This attempts to set a global default subscriber. If one is already set,
    // initialization logs might not be captured here.
    // For robust library logging, consider alternative approaches or clear documentation
    // on application-level logger configuration requirements.
    let subscriber = fmt()
        .with_writer(make_writer)
        .with_env_filter(
            EnvFilter::try_from_default_env()
                .unwrap_or_else(|_| EnvFilter::new("info")) // Default to "info" if RUST_LOG is not set.
                .add_directive("hf-hub=trace".parse()?), // Enable trace level for hf-hub.
        )
        .finish();

    // Attempt to set the global default subscriber.
    // The guard ensures the subscriber remains active for the scope of `initialize_model`.
    // If `set_default` fails (e.g., a subscriber is already set), logs might be lost or go elsewhere.
    let _guard = tracing::subscriber::set_default(subscriber);

    fs::create_dir_all(cache_dir)
        .with_context(|| format!("Failed to create cache directory at {:?}", cache_dir))?;

    // Set HF_HOME environment variable to the specified cache directory.
    // Note: Modifying environment variables can have global effects and concurrency implications.
    // This is done to direct Hugging Face Hub where to store/load models.
    // Ideally, this would be configurable directly via `fastembed` or `hf-hub` APIs if available.
    let hf_home_path = cache_dir.to_str().ok_or_else(|| {
        anyhow::anyhow!("Cache directory path is not valid UTF-8: {:?}", cache_dir)
    })?;
    std::env::set_var("HF_HOME", hf_home_path);

    TextEmbedding::try_new(
        InitOptions::new(EmbeddingModel::BGEBaseENV15).with_show_download_progress(true),
    )
    .with_context(|| {
        // Attempt to get logs. Lock poisoning is a remote possibility.
        let logs = log_buffer.lock().map_or_else(
            |poisoned| format!("Log buffer lock was poisoned: {:?}", poisoned),
            |guard| String::from_utf8_lossy(&guard).to_string(),
        );
        format!(
            "Failed to initialize TextEmbedding model. Captured logs during init:\n{}",
            logs
        )
    })
}
