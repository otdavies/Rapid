// Module for our data structures
mod structs;

// Module for utility functions
mod utils;

// Module for parser and query configurations
mod config;

// Module for core parsing logic
mod parsing;

// Module for embedding model and initialization
mod embedding;

// Module for core scanning logic
mod scanner;

// Module for FFI functions
mod ffi;
pub use ffi::*; // Re-export all FFI functions
