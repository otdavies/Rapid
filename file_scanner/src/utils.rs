use std::fs;
use std::path::Path;

/// Checks if a file is likely binary by looking for null bytes.
pub fn is_binary(path: &Path) -> bool {
    fs::read(path)
        .map(|bytes| bytes.iter().any(|&b| b == 0))
        .unwrap_or(true) // Treat read errors as if the file is binary or inaccessible
}

/// Calculates the cosine similarity between two f32 slices.
///
/// Returns `0.0` if either slice is empty or if the norm of either vector is zero.
///
/// # Panics
/// Panics if the slices have different lengths.
pub fn cosine_similarity(v1: &[f32], v2: &[f32]) -> f32 {
    if v1.is_empty() || v2.is_empty() {
        return 0.0;
    }
    debug_assert_eq!(
        v1.len(),
        v2.len(),
        "Vectors must have the same length for cosine similarity"
    );

    let dot_product: f32 = v1.iter().zip(v2).map(|(a, b)| a * b).sum();

    let norm_v1: f32 = v1.iter().map(|x| x.powi(2)).sum::<f32>().sqrt();
    let norm_v2: f32 = v2.iter().map(|x| x.powi(2)).sum::<f32>().sqrt();

    if norm_v1 == 0.0 || norm_v2 == 0.0 {
        // If either vector has zero magnitude, similarity is undefined or can be treated as 0.
        return 0.0;
    }

    dot_product / (norm_v1 * norm_v2)
}
