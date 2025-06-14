use serde::{Deserialize, Serialize};

#[derive(Serialize, Deserialize, Debug, Clone)]
pub struct FunctionInfo {
    pub name: String,
    pub body: Option<String>,
    pub comment: Option<String>,
}

#[derive(Serialize, Deserialize, Debug, Clone)]
pub struct FileContext {
    pub path: String,
    // TODO: Evaluate if FileContext::description is still necessary or can be derived from other sources.
    pub description: String,
    pub functions: Vec<FunctionInfo>,
}

#[derive(Serialize, Deserialize, Debug)]
pub struct ScanResult {
    pub file_contexts: Vec<FileContext>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub debug_log: Option<Vec<String>>,
    pub timed_out_internally: bool,
    pub files_processed_before_timeout: usize,
}

#[derive(Serialize, Deserialize, Debug, Clone)]
pub struct SearchMatch {
    pub line_number: usize,
    pub context: String,
}

#[derive(Serialize, Deserialize, Debug, Clone)]
pub struct FileSearchResult {
    pub path: String,
    pub matches: Vec<SearchMatch>,
}

#[derive(Serialize, Deserialize, Debug)]
pub struct SearchServiceResult {
    pub results: Vec<FileSearchResult>,
    pub stats: SearchStats,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub debug_log: Option<Vec<String>>,
}

#[derive(Serialize, Deserialize, Debug, Default, Clone)]
pub struct SearchStats {
    pub files_scanned: usize,
    pub total_matches: usize,
    pub timed_out: bool,
}

#[derive(Serialize, Deserialize, Debug, Clone)]
pub struct ConceptSearchResultItem {
    pub file: String,
    pub function: String,
    pub similarity: f32,
    pub body: Option<String>, // Added to include the function body
}

#[derive(Serialize, Deserialize, Debug)]
pub struct ConceptSearchServiceResult {
    pub results: Vec<ConceptSearchResultItem>,
    pub stats: ConceptSearchStats,
    pub error: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub debug_log: Option<Vec<String>>,
}

#[derive(Serialize, Deserialize, Debug, Default)]
pub struct ConceptSearchStats {
    pub functions_analyzed: usize,
    pub search_duration_seconds: f32,
}
