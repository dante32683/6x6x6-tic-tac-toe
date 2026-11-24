//! Certificate check: disjoint gadgets covering every live line, each block a
//! Breaker win. Everything is recomputed from the line table; nothing in the
//! file is trusted beyond being a claim.

use crate::block::{Game, Solver, MAX_BLOCK};
use crate::geometry::{apply_map, CellMap, Geometry, Set, CELLS};

/// One block entry: its cells and claimed lines, each written as two cells.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Block {
    pub cells: Set,
    pub lines: Vec<(usize, usize)>,
}

#[derive(Clone, Debug, PartialEq, Eq, Default)]
pub struct Cert {
    pub blocks: Vec<Block>,
    pub pairs: Vec<(usize, usize)>,
}

impl Cert {
    /// The certificate with every cell sent through `map`.
    pub fn mapped(&self, map: &CellMap) -> Cert {
        let f = |c: usize| map[c] as usize;
        Cert {
            blocks: self
                .blocks
                .iter()
                .map(|b| Block { cells: apply_map(map, b.cells), lines: b.lines.iter().map(|&(a, c)| (f(a), f(c))).collect() })
                .collect(),
            pairs: self.pairs.iter().map(|&(a, b)| (f(a), f(b))).collect(),
        }
    }
}

/// Size of the largest block seen, for the final report.
#[derive(Default)]
pub struct CertStats {
    pub largest_block: usize,
}

/// Check that `cert` proves Breaker holds position (m, b) with Maker to move.
pub fn check_cert(geo: &Geometry, solver: &mut Solver, stats: &mut CertStats, m: Set, b: Set, cert: &Cert) -> Result<(), String> {
    let marked = m.union(b);
    let mut used = Set::default();
    let mut claimed = vec![false; geo.lines.len()];
    // (block cells, indices of its claimed lines)
    let mut block_lines: Vec<(Set, Vec<usize>)> = Vec::new();

    for (i, block) in cert.blocks.iter().enumerate() {
        let cells = block.cells;
        if cells.is_empty() || cells.len() > MAX_BLOCK {
            return Err(format!("block {i} has {} cells (need 1..={MAX_BLOCK})", cells.len()));
        }
        if !used.inter(cells).is_empty() {
            return Err(format!("block {i} overlaps an earlier gadget"));
        }
        used = used.union(cells);
        let mut idx = Vec::new();
        for &(a, c) in &block.lines {
            if !cells.has(a) || !cells.has(c) {
                return Err(format!("block {i}: claimed line {a}/{c} has a cell outside the block"));
            }
            let li = geo.line_through(a, c).ok_or(format!("block {i}: {a}/{c} is not on a line"))?;
            claimed[li] = true;
            idx.push(li);
        }
        block_lines.push((cells, idx));
    }
    for &(a, c) in &cert.pairs {
        if a >= CELLS || c >= CELLS || marked.has(a) || marked.has(c) {
            return Err(format!("pair {a}/{c} has a marked or invalid cell"));
        }
        let cells = Set::from_cells(&[a, c]);
        if cells.len() != 2 || !used.inter(cells).is_empty() {
            return Err(format!("pair {a}/{c} overlaps another gadget"));
        }
        used = used.union(cells);
        claimed[geo.line_through(a, c).ok_or(format!("pair {a}/{c} is not on a line"))?] = true;
    }

    for (li, line) in geo.lines.iter().enumerate() {
        let live = line.inter(b).is_empty();
        if live && !claimed[li] {
            return Err(format!("live line {} is not covered", line.show()));
        }
    }

    for (i, (cells, idx)) in block_lines.iter().enumerate() {
        let local = cells.to_vec();
        let mask = |s: Set| -> u16 { local.iter().enumerate().filter(|&(_, &c)| s.has(c)).fold(0, |acc, (k, _)| acc | 1 << k) };
        let mut edges: Vec<u16> = idx
            .iter()
            .filter(|&&li| geo.lines[li].inter(b).is_empty())
            .map(|&li| mask(geo.lines[li].inter(*cells)))
            .collect();
        edges.sort();
        edges.dedup();
        let game = Game { edges, maker: mask(m), breaker: mask(b), full: mask(*cells) };
        if !solver.breaker_wins(&game) {
            return Err(format!("block {i} (cells {}) is not a Breaker win", cells.show()));
        }
        stats.largest_block = stats.largest_block.max(local.len());
    }
    Ok(())
}
