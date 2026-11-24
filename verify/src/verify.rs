//! The tree walk: every Maker move from the root must meet a record, and every
//! record's reply must lead to a checked subtree or a valid certificate.

use std::collections::{HashMap, HashSet};

use crate::block::Solver;
use crate::cert::{check_cert, CertStats};
use crate::geometry::{compose, CellMap, Geometry, Set, CELLS};
use crate::parse::Record;

const INDEX_THREADS: usize = 4;
const PROGRESS_EVERY: usize = 100_000;

/// Records grouped by canonical position: each entry is (record index, index
/// into G of a map taking the record's position to the canonical one).
pub type Index = HashMap<(Set, Set), Vec<(usize, usize)>>;

pub fn build_index(geo: &Geometry, records: &[Record]) -> Index {
    let chunk = records.len().div_ceil(INDEX_THREADS).max(1);
    let parts: Vec<Vec<((Set, Set), (usize, usize))>> = std::thread::scope(|scope| {
        let handles: Vec<_> = records
            .chunks(chunk)
            .enumerate()
            .map(|(k, rs)| {
                scope.spawn(move || {
                    rs.iter()
                        .enumerate()
                        .map(|(i, r)| {
                            let (m, b, s) = geo.canonical(r.m, r.b);
                            ((m, b), (k * chunk + i, s))
                        })
                        .collect()
                })
            })
            .collect();
        handles.into_iter().map(|h| h.join().unwrap()).collect()
    });
    let mut index = Index::new();
    for (key, entry) in parts.into_iter().flatten() {
        index.entry(key).or_default().push(entry);
    }
    index
}

#[derive(Default)]
pub struct Totals {
    pub leaf_certs: usize,
}

pub struct Verifier<'a> {
    geo: &'a Geometry,
    records: &'a [Record],
    index: &'a Index,
    /// Canonical forms of Maker-to-move positions already fully checked.
    done: HashSet<(Set, Set)>,
    pub solver: Solver,
    pub cert_stats: CertStats,
    pub totals: Totals,
}

impl<'a> Verifier<'a> {
    pub fn new(geo: &'a Geometry, records: &'a [Record], index: &'a Index) -> Self {
        Verifier { geo, records, index, done: HashSet::new(), solver: Solver::default(), cert_stats: CertStats::default(), totals: Totals::default() }
    }

    pub fn positions_checked(&self) -> usize {
        self.done.len()
    }

    /// Check the empty board with Maker to move, restricted to Maker's first
    /// moves in `first_moves`.
    pub fn check_root(&mut self, first_moves: &[usize]) -> Result<(), String> {
        self.check_moves(Set::default(), Set::default(), first_moves)
    }

    /// Maker to move in (m, b): no full Maker line, and every empty cell works.
    fn check_maker(&mut self, m: Set, b: Set) -> Result<(), String> {
        let (cm, cb, _) = self.geo.canonical(m, b);
        if self.done.contains(&(cm, cb)) {
            return Ok(());
        }
        if self.geo.lines.iter().any(|&l| l.minus(m).is_empty()) {
            return Err(format!("Maker owns a full line in M={} B={}", m.show(), b.show()));
        }
        let empty: Vec<usize> = (0..CELLS).filter(|&c| !m.has(c) && !b.has(c)).collect();
        self.check_moves(m, b, &empty)?;
        self.done.insert((cm, cb));
        if self.done.len() % PROGRESS_EVERY == 0 {
            eprintln!("  {} positions checked", self.done.len());
        }
        Ok(())
    }

    /// For each cell in `moves`, Maker plays it and every matching record must hold.
    fn check_moves(&mut self, m: Set, b: Set, moves: &[usize]) -> Result<(), String> {
        let (records, index) = (self.records, self.index);
        for &c in moves {
            if m.has(c) || b.has(c) {
                return Err(format!("cell {c} is not empty in M={} B={}", m.show(), b.show()));
            }
            let m2 = m.with(c);
            let (km, kb, q) = self.geo.canonical(m2, b);
            let entries = index.get(&(km, kb)).ok_or(format!("no record for M={} B={} (Maker played {c} in M={} B={})", m2.show(), b.show(), m.show(), b.show()))?;
            for &(ri, si) in entries {
                // s takes the record's position to (m2, b): inverse of q after the record's map.
                let s: CellMap = compose(&self.geo.inverse[q], &self.geo.group[si]);
                self.check_record(&records[ri], &s, m2, b)?;
            }
        }
        Ok(())
    }

    /// Record `rec`, taken to the position (m2, b) by `s`, with Breaker to move.
    fn check_record(&mut self, rec: &Record, s: &CellMap, m2: Set, b: Set) -> Result<(), String> {
        let r = s[rec.reply] as usize;
        if m2.has(r) || b.has(r) {
            return Err(format!("reply {r} is not empty in M={} B={}", m2.show(), b.show()));
        }
        let b2 = b.with(r);
        match &rec.cert {
            None => self.check_maker(m2, b2),
            Some(cert) => {
                self.totals.leaf_certs += 1;
                check_cert(self.geo, &mut self.solver, &mut self.cert_stats, m2, b2, &cert.mapped(s)).map_err(|e| format!("{e} (position M={} B={})", m2.show(), b2.show()))
            }
        }
    }
}

/// The records Breaker's strategy reaches when every position uses only its
/// first record in file order (`--emit-used`): record indices, ascending.
///
/// Run only after `check_root` has passed on the same first moves, so every
/// record visited here is already checked. It checks nothing itself: it
/// follows the first record of each reached position through the R replies
/// and collects what it meets, giving one record per position up to G.
pub fn used_records(geo: &Geometry, records: &[Record], index: &Index, first_moves: &[usize]) -> Result<Vec<usize>, String> {
    let mut used: HashSet<usize> = HashSet::new();
    let mut done: HashSet<(Set, Set)> = HashSet::new();
    // explicit stack of Maker-to-move positions with the moves left to try
    let mut stack: Vec<(Set, Set, Vec<usize>)> = vec![(Set::default(), Set::default(), first_moves.to_vec())];
    while let Some((m, b, mut moves)) = stack.pop() {
        let Some(c) = moves.pop() else { continue };
        stack.push((m, b, moves));
        let m2 = m.with(c);
        let (km, kb, q) = geo.canonical(m2, b);
        let &(ri, si) = index.get(&(km, kb)).and_then(|e| e.first()).ok_or(format!("no record for M={} B={}", m2.show(), b.show()))?;
        used.insert(ri);
        let rec = &records[ri];
        if rec.cert.is_some() {
            continue;
        }
        let s: CellMap = compose(&geo.inverse[q], &geo.group[si]);
        let b2 = b.with(s[rec.reply] as usize);
        let (cm, cb, _) = geo.canonical(m2, b2);
        if done.insert((cm, cb)) {
            let empty: Vec<usize> = (0..CELLS).rev().filter(|&x| !m2.has(x) && !b2.has(x)).collect();
            stack.push((m2, b2, empty));
        }
    }
    let mut out: Vec<usize> = used.into_iter().collect();
    out.sort_unstable();
    Ok(out)
}
