// Standalone development utility; not a runtime mod component.
use std::io::{self, Read, Write};
use std::process::ExitCode;
const MAX: usize = 16 * 1024 * 1024;
fn decode(input: &[u8], expected: usize) -> Result<Vec<u8>, String> {
    if input.len() < 2 || input.len() > MAX || expected == 0 || expected > MAX {
        return Err("invalid block length".into());
    }
    let mut output = vec![0u8; expected];
    let actual = oozextract::Extractor::new().read_from_slice(input, &mut output)
        .map_err(|e| format!("decoder: {e:?}"))?;
    if actual != expected { return Err(format!("size mismatch: {actual} != {expected}")); }
    Ok(output)
}
fn run() -> Result<(), String> {
    let args: Vec<_> = std::env::args().collect();
    if args.len() != 3 || args[1] != "decompress" { return Err("usage: bl4-ncs-block-decoder decompress RAW_SIZE < block > output".into()); }
    let expected: usize = args[2].parse().map_err(|_| "invalid size")?;
    let mut input = Vec::new();
    io::stdin().take((MAX + 1) as u64).read_to_end(&mut input).map_err(|e| e.to_string())?;
    let output = decode(&input, expected)?;
    io::stdout().write_all(&output).map_err(|e| e.to_string())
}
fn main() -> ExitCode {
    match run() { Ok(()) => ExitCode::SUCCESS, Err(e) => { eprintln!("{e}"); ExitCode::FAILURE } }
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test] fn raw_oodle_block() {
        let input = [0x4c, 0x06, 65, 66, 67, 68];
        assert_eq!(decode(&input, 4).unwrap(), b"ABCD");
    }
    #[test] fn invalid_lengths() {
        assert!(decode(&[], 1).is_err());
        assert!(decode(&[0x4c, 0x06], 0).is_err());
        assert!(decode(&[0x4c, 0x06], MAX + 1).is_err());
    }
    #[test] fn two_raw_blocks() {
        let mut input = vec![0x4c, 0x06];
        input.extend(std::iter::repeat(0xAB).take(0x40000));
        input.extend([0x4c, 0x06, 0xCD, 0xDE]);
        let out = decode(&input, 0x40002).unwrap();
        assert!(out[..0x40000].iter().all(|v| *v == 0xAB));
        assert_eq!(&out[0x40000..], &[0xCD, 0xDE]);
    }
}
