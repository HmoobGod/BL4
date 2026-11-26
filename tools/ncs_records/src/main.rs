// Offline development record reader; private data stays local.
use std::io::{self, Read, Write};
use std::process::ExitCode;
const MAX: usize = 16 * 1024 * 1024;
fn read_document(input: &[u8]) -> Result<String, String> {
    if input.len() < 16 || input.len() > MAX { return Err("invalid input length".into()); }
    let doc = bl4_ncs::parse_ncs_binary(input).ok_or("structured record parse failed")?;
    if doc.tables.is_empty() { return Err("no decoded tables".into()); }
    serde_json::to_string_pretty(&doc).map_err(|e| e.to_string())
}
fn run() -> Result<(), String> {
    let mut input = Vec::new();
    io::stdin().take((MAX + 1) as u64).read_to_end(&mut input).map_err(|e| e.to_string())?;
    let out = read_document(&input)?;
    io::stdout().write_all(out.as_bytes()).map_err(|e| e.to_string())
}
fn main() -> ExitCode {
    match run() { Ok(()) => ExitCode::SUCCESS, Err(e) => { eprintln!("{e}"); ExitCode::FAILURE } }
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test] fn rejects_empty() { assert!(read_document(&[]).is_err()); }
    #[test] fn rejects_zero_header() { assert!(read_document(&[0; 32]).is_err()); }
}
