//! Strict parsing of proof records. Anything not exactly in the format of
//! docs/proof-format.md is an error; nothing is repaired or skipped.

use crate::cert::{Block, Cert};
use crate::geometry::{Set, CELLS};

#[derive(Debug, Clone)]
pub struct Record {
    pub m: Set,
    pub b: Set,
    pub reply: usize,
    /// `Some` for an `L` record, `None` for an `R` record.
    pub cert: Option<Cert>,
}

/// A decimal number written canonically (no sign, no leading zeros).
fn number(s: &str) -> Result<usize, String> {
    let n: usize = s.parse().map_err(|_| format!("bad number {s:?}"))?;
    if n.to_string() != s {
        return Err(format!("non-canonical number {s:?}"));
    }
    Ok(n)
}

fn cell(s: &str) -> Result<usize, String> {
    let n = number(s)?;
    if n >= CELLS {
        return Err(format!("cell id {n} is out of range"));
    }
    Ok(n)
}

/// Comma-separated cell ids, strictly increasing; "-" is the empty set.
fn cell_set(s: &str) -> Result<Set, String> {
    if s == "-" {
        return Ok(Set::default());
    }
    let ids = s.split(',').map(cell).collect::<Result<Vec<_>, _>>()?;
    if ids.windows(2).any(|w| w[0] >= w[1]) {
        return Err(format!("cells {s:?} are not strictly increasing"));
    }
    Ok(Set::from_cells(&ids))
}

/// `a/b`: two distinct cells.
fn cell_pair(s: &str) -> Result<(usize, usize), String> {
    let (a, b) = s.split_once('/').ok_or(format!("bad pair {s:?}"))?;
    let (a, b) = (cell(a)?, cell(b)?);
    if a == b {
        return Err(format!("pair {s:?} repeats a cell"));
    }
    Ok((a, b))
}

fn block(entry: &str) -> Result<Block, String> {
    let (cells, lines) = entry.split_once(" : ").ok_or(format!("bad block entry {entry:?}"))?;
    let lines = if lines.is_empty() { vec![] } else { lines.split(',').map(cell_pair).collect::<Result<Vec<_>, _>>()? };
    Ok(Block { cells: cell_set(cells)?, lines })
}

fn entries<T>(field: &str, one: fn(&str) -> Result<T, String>) -> Result<Vec<T>, String> {
    if field == "-" {
        return Ok(vec![]);
    }
    field.split(" ; ").map(one).collect()
}

/// Parse one non-comment line.
pub fn record(line: &str) -> Result<Record, String> {
    let f: Vec<&str> = line.split(" | ").collect();
    let (want, has_cert) = match f.first().copied() {
        Some("R") => (4, false),
        Some("L") => (6, true),
        _ => return Err("record must start with 'R | ' or 'L | '".into()),
    };
    if f.len() != want {
        return Err(format!("expected {want} fields, found {}", f.len()));
    }
    let (m, b, reply) = (cell_set(f[1])?, cell_set(f[2])?, cell(f[3])?);
    if !m.inter(b).is_empty() {
        return Err("M and B overlap".into());
    }
    if m.len() != b.len() + 1 {
        return Err(format!("|M| = {} but |B| = {} (need |M| = |B| + 1)", m.len(), b.len()));
    }
    if m.union(b).has(reply) {
        return Err(format!("reply {reply} is not empty"));
    }
    let cert = if has_cert { Some(Cert { blocks: entries(f[4], block)?, pairs: entries(f[5], cell_pair)? }) } else { None };
    Ok(Record { m, b, reply, cert })
}

/// Parse a whole file; comment lines start with '#'. Errors carry the line number.
pub fn file(text: &str) -> Result<Vec<Record>, String> {
    let mut out = Vec::new();
    for (i, line) in text.lines().enumerate() {
        if line.starts_with('#') {
            continue;
        }
        out.push(record(line).map_err(|e| format!("line {}: {e}", i + 1))?);
    }
    Ok(out)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parses_valid_records() {
        let r = record("R | 0 | - | 5").unwrap();
        assert_eq!((r.m.show(), r.b.show(), r.reply, r.cert.is_none()), ("0".into(), "-".into(), 5, true));
        let l = record("L | 0,1 | 2 | 3 | 0,1,2 : 0/1,1/2 ; 7 :  | 10/11 ; 12/13").unwrap();
        let c = l.cert.unwrap();
        assert_eq!((c.blocks.len(), c.blocks[0].lines.len(), c.pairs.len()), (2, 2, 2));
    }

    #[test]
    fn rejects_malformed_records() {
        for bad in [
            "R | 0 | - | 0",        // reply not empty
            "R | 0,1 | - | 5",      // |M| != |B| + 1
            "R | 1,0 | 2 | 5",      // unsorted
            "R | 0,0 | 2 | 5",      // duplicate
            "R | 0 | 0 | 5",        // M and B overlap
            "R | 216 | - | 5",      // id out of range
            "R | 00 | - | 5",       // non-canonical number
            "R | 0 | - | 5 | extra",
            "L | 0 | - | 5 | - ",
            "X | 0 | - | 5",
            "",
        ] {
            assert!(record(bad).is_err(), "accepted {bad:?}");
        }
    }
}
