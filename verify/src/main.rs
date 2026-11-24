//! Independent verifier for the 6x6x6 Maker-Breaker proof (docs/proof-format.md).
//!
//!     verify full <proof> [--root <cell>] [--emit-used <file>]
//!                                           walk the tree from the empty board
//!     verify certs <proof>                  check every record and certificate, no tree walk
//!
//! `--emit-used` changes nothing about the check. After a passing walk it
//! writes the 1-based file line numbers of the records the strategy reaches,
//! one record per position (the first in file order), for `gen/compact_prune.py`.
//!
//! `<proof>` may also be a catalogue-format v2 file (starts with `C6PROOF2`):
//! v2.rs decodes it into the same records, which are then checked as usual.

mod block;
mod cert;
mod geometry;
mod parse;
mod v2;
mod verify;
// the unit tests use 6x6x6 facts (orbits, line lengths, a sample proof)
#[cfg(all(test, not(feature = "n5")))]
mod tests;

use std::time::Instant;

use cert::{check_cert, CertStats};
use geometry::{Geometry, CELLS};

const STACK_BYTES: usize = 512 << 20;

fn main() {
    let handle = std::thread::Builder::new().stack_size(STACK_BYTES).spawn(run).unwrap();
    let ok = handle.join().unwrap_or(false);
    std::process::exit(if ok { 0 } else { 1 });
}

fn run() -> bool {
    let args: Vec<String> = std::env::args().collect();
    let usage = "usage: verify full <proof> [--root <cell>] [--emit-used <file>] | verify certs <proof>";
    let (mode, path) = match (args.get(1), args.get(2)) {
        (Some(m), Some(p)) => (m.as_str(), p.as_str()),
        _ => return fail(usage),
    };
    let (mut root, mut emit): (Option<usize>, Option<&str>) = (None, None);
    let mut rest = args[3..].iter().map(String::as_str);
    while let Some(flag) = rest.next() {
        match (mode, flag, rest.next()) {
            ("full", "--root", Some(v)) if root.is_none() => match v.parse() {
                Ok(c) if c < CELLS => root = Some(c),
                _ => return fail(&format!("--root needs a cell id below {CELLS}")),
            },
            ("full", "--emit-used", Some(v)) if emit.is_none() => emit = Some(v),
            _ => return fail(usage),
        }
    }
    let data = match std::fs::read(path) {
        Ok(t) => t,
        Err(e) => return fail(&format!("reading {path}: {e}")),
    };
    let t0 = Instant::now();
    let geo = Geometry::new();
    // a v2 file is decoded to v1 records (v2.rs); either way every record is checked
    let is_v2 = data.starts_with(v2::MAGIC);
    if is_v2 && emit.is_some() {
        return fail("--emit-used needs a v1 file (its line numbers)");
    }
    let parsed = if is_v2 {
        v2::records(&data, &geo).map(|r| (r, String::new()))
    } else {
        String::from_utf8(data).map_err(|e| e.to_string()).and_then(|t| parse::file(&t).map(|r| (r, t)))
    };
    let (records, text) = match parsed {
        Ok(r) => r,
        Err(e) => return fail(&format!("{path}: {e}")),
    };
    if is_v2 {
        println!("{path}: catalogue format v2, decoded in {:.1}s", t0.elapsed().as_secs_f64());
    }
    println!("{} cells, {} lines, |G| = {}; {} records parsed", CELLS, geo.lines.len(), geo.group.len(), records.len());
    let leaves = records.iter().filter(|r| r.cert.is_some()).count();
    println!("{} R records, {leaves} L records", records.len() - leaves);
    match mode {
        "certs" => certs(&geo, &records, t0),
        "full" => full(&geo, &records, root, t0, emit.map(|out| (out, text.as_str()))),
        _ => fail(usage),
    }
}

/// `--emit-used`: the walk of `verify::used_records`, written as file line numbers.
fn emit_used(geo: &Geometry, records: &[parse::Record], index: &verify::Index, first_moves: &[usize], out: &str, text: &str) -> bool {
    let used = match verify::used_records(geo, records, index, first_moves) {
        Ok(u) => u,
        Err(e) => return fail(&e),
    };
    // record i is the i-th non-comment line, as in parse::file
    let line_of: Vec<usize> = text.lines().enumerate().filter(|(_, l)| !l.starts_with('#')).map(|(i, _)| i + 1).collect();
    let body: String = used.iter().map(|&i| format!("{}\n", line_of[i])).collect();
    if let Err(e) = std::fs::write(out, body) {
        return fail(&format!("writing {out}: {e}"));
    }
    let leaves = used.iter().filter(|&&i| records[i].cert.is_some()).count();
    println!("used records: {} ({} R, {leaves} L), line numbers written to {out}", used.len(), used.len() - leaves);
    true
}

fn first_moves(geo: &Geometry, root: Option<usize>) -> Vec<usize> {
    match root {
        Some(c) => geo.orbit(c).to_vec(),
        None => (0..CELLS).collect(),
    }
}

fn fail(msg: &str) -> bool {
    eprintln!("FAIL: {msg}");
    false
}

/// Every L record's certificate, at the record's own position (M, B + r).
fn certs(geo: &Geometry, records: &[parse::Record], t0: Instant) -> bool {
    let mut solver = block::Solver::default();
    let mut stats = CertStats::default();
    let mut checked = 0;
    for (i, r) in records.iter().enumerate() {
        let Some(c) = &r.cert else { continue };
        let b2 = r.b.with(r.reply);
        if let Err(e) = check_cert(geo, &mut solver, &mut stats, r.m, b2, c) {
            return fail(&format!("record {} (M={} B={}): {e}", i + 1, r.m.show(), r.b.show()));
        }
        checked += 1;
    }
    if checked == 0 {
        return fail("no L records to check");
    }
    println!("{checked} certificates OK, {} distinct block games, largest block {} cells, {:.1}s", solver.distinct_games(), stats.largest_block, t0.elapsed().as_secs_f64());
    // only the leaf certificates: says nothing about the tree above them
    println!("CERTS OK");
    true
}

/// `emit`: (output path, proof text) for `--emit-used`, run only after the walk passes.
fn full(geo: &Geometry, records: &[parse::Record], root: Option<usize>, t0: Instant, emit: Option<(&str, &str)>) -> bool {
    let first_moves = first_moves(geo, root);
    match root {
        Some(c) => println!("root orbit of cell {c}: {} cells, first moves checked: {:?}", first_moves.len(), first_moves),
        None => println!("all {} first moves checked", first_moves.len()),
    }
    let index = verify::build_index(geo, records);
    println!("{} distinct canonical positions among the records", index.len());
    let mut v = verify::Verifier::new(geo, records, &index);
    if let Err(e) = v.check_root(&first_moves) {
        return fail(&e);
    }
    println!(
        "{} distinct positions checked, {} leaf certificates checked, {} distinct block games, largest block {} cells, {:.1}s",
        v.positions_checked(),
        v.totals.leaf_certs,
        v.solver.distinct_games(),
        v.cert_stats.largest_block,
        t0.elapsed().as_secs_f64()
    );
    // PROOF OK is reserved for the whole game; a root orbit is one piece of it
    match root {
        Some(c) => println!("ROOT ORBIT OK (orbit of cell {c} only; not a full proof)"),
        None => {
            let n = geometry::SIDE;
            println!("PROOF OK ({n}x{n}x{n} Maker-Breaker: Breaker wins)");
        }
    }
    emit.is_none_or(|(out, text)| emit_used(geo, records, &index, &first_moves, out, text))
}
