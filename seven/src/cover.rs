//! Check a static Breaker cover of the whole 7x7x7 board: disjoint blocks,
//! each a small game Breaker wins moving second, plus pairs, so that every
//! line is claimed by a block edge inside it or by a pair of its cells.
//! Breaker then answers every Maker move inside the same gadget (or anywhere,
//! if Maker plays a cell no gadget uses), which wins the whole game: this is
//! the composition argument of our 6x6x6 proof (docs/proof-format.md;
//! write-up section 6) with no opening moves at all.
//!
//! Shares no code with gen/ (which found the cover): it rebuilds the lines,
//! solves each block exhaustively, and checks every claim itself.

use crate::board::{cell, paper_name, Board, CELLS, LINE_COUNT, SIDE};
use std::collections::HashMap;

/// Largest block this solver accepts (cells are bits of a u32 mask).
const MAX_BLOCK: usize = 24;

fn parse_cell(s: &str) -> Result<usize, String> {
    let v: Vec<usize> = s.split(',').map(|t| t.trim().parse::<usize>().map_err(|e| format!("{s}: {e}"))).collect::<Result<_, _>>()?;
    if v.len() != 3 || v.iter().any(|&t| t >= SIDE) {
        return Err(format!("bad cell {s}"));
    }
    Ok(cell(v[0], v[1], v[2]))
}

/// The one board line holding all of `cells` (at least two of them).
fn line_through(board: &Board, cells: &[usize]) -> Result<usize, String> {
    if cells.len() < 2 {
        return Err("an edge or pair needs two cells".into());
    }
    let hits: Vec<usize> = board.through[cells[0]].iter().copied().filter(|&l| cells.iter().all(|c| board.lines[l].contains(c))).collect();
    match hits.as_slice() {
        [l] => Ok(*l),
        [] => Err(format!("cells {:?} lie on no line", cells.iter().map(|&c| paper_name(c)).collect::<Vec<_>>())),
        _ => Err("two cells determine at most one line".into()),
    }
}

/// Does Breaker, moving second, hit every edge? Exhaustive search with memo.
struct BlockGame {
    size: usize,
    edges: Vec<u32>,
    memo: HashMap<(u32, u32), bool>,
}

impl BlockGame {
    fn breaker_wins(&mut self, maker: u32, breaker: u32) -> bool {
        if self.edges.iter().any(|&e| e & maker == e) {
            return false;
        }
        let live: Vec<u32> = self.edges.iter().copied().filter(|&e| e & breaker == 0).collect();
        if live.is_empty() {
            return true;
        }
        if let Some(&r) = self.memo.get(&(maker, breaker)) {
            return r;
        }
        let full = if self.size == 32 { u32::MAX } else { (1u32 << self.size) - 1 };
        let free = full & !maker & !breaker;
        let maker_to_move = maker.count_ones() == breaker.count_ones();
        let result = if free == 0 {
            true // board full and no edge is all Maker's
        } else if maker_to_move {
            (0..self.size).filter(|&i| free >> i & 1 == 1).all(|i| self.breaker_wins(maker | 1 << i, breaker))
        } else {
            (0..self.size).filter(|&i| free >> i & 1 == 1).any(|i| self.breaker_wins(maker, breaker | 1 << i))
        };
        self.memo.insert((maker, breaker), result);
        result
    }
}

pub fn run(board: &Board, path: &str) -> Result<(), String> {
    let text = std::fs::read_to_string(path).map_err(|e| format!("{path}: {e}"))?;
    let mut owner = vec![usize::MAX; CELLS];
    let mut claimed = vec![false; LINE_COUNT];
    let (mut blocks, mut pairs, mut block_lines) = (0, 0, 0);
    let mut shapes: HashMap<String, usize> = HashMap::new();
    for (no, raw) in text.lines().enumerate() {
        let line = raw.trim();
        if line.is_empty() || line.starts_with('#') {
            continue;
        }
        let at = |e: String| format!("line {}: {e}", no + 1);
        let gadget = no;
        if let Some(rest) = line.strip_prefix("block ") {
            let mut parts = rest.split('|');
            let cells: Vec<usize> = parts.next().unwrap_or("").split_whitespace().map(parse_cell).collect::<Result<_, _>>().map_err(at)?;
            if cells.len() > MAX_BLOCK {
                return Err(at(format!("block of {} cells is too big", cells.len())));
            }
            for &c in &cells {
                if owner[c] != usize::MAX {
                    return Err(at(format!("cell {} used twice", paper_name(c))));
                }
                owner[c] = gadget;
            }
            let local: HashMap<usize, usize> = cells.iter().enumerate().map(|(i, &c)| (c, i)).collect();
            let mut edges = Vec::new();
            for part in parts {
                let e = part.trim().strip_prefix("edge ").ok_or_else(|| at("expected 'edge'".into()))?;
                let ecells: Vec<usize> = e.split(';').map(parse_cell).collect::<Result<_, _>>().map_err(at)?;
                let mut mask = 0u32;
                for c in &ecells {
                    let i = local.get(c).ok_or_else(|| at(format!("edge cell {} is not in the block", paper_name(*c))))?;
                    mask |= 1 << i;
                }
                let l = line_through(board, &ecells).map_err(at)?;
                claimed[l] = true;
                block_lines += 1;
                edges.push(mask);
            }
            let mut game = BlockGame { size: cells.len(), edges: edges.clone(), memo: HashMap::new() };
            if !game.breaker_wins(0, 0) {
                return Err(at("Maker wins this block's game".into()));
            }
            blocks += 1;
            *shapes.entry(format!("{} cells, {} edges", cells.len(), edges.len())).or_default() += 1;
        } else if let Some(rest) = line.strip_prefix("pair ") {
            let cells: Vec<usize> = rest.split_whitespace().map(parse_cell).collect::<Result<_, _>>().map_err(at)?;
            if cells.len() != 2 || cells[0] == cells[1] {
                return Err(at("a pair is two different cells".into()));
            }
            for &c in &cells {
                if owner[c] != usize::MAX {
                    return Err(at(format!("cell {} used twice", paper_name(c))));
                }
                owner[c] = gadget;
            }
            claimed[line_through(board, &cells).map_err(at)?] = true;
            pairs += 1;
        } else {
            return Err(at(format!("unknown gadget: {line}")));
        }
    }
    let unclaimed: Vec<usize> = (0..LINE_COUNT).filter(|&l| !claimed[l]).collect();
    let unused = owner.iter().filter(|&&o| o == usize::MAX).count();
    println!("== static cover {path}");
    let distinct = claimed.iter().filter(|&&c| c).count();
    println!("blocks {blocks} ({block_lines} edges), pairs {pairs}, unused cells {unused}, lines claimed {distinct}");
    let mut s: Vec<_> = shapes.into_iter().collect();
    s.sort();
    for (k, v) in s {
        println!("  {v} x block of {k}");
    }
    if unclaimed.is_empty() {
        println!("COVER OK: every one of the {LINE_COUNT} lines is claimed, every block is a Breaker win moving second");
        Ok(())
    } else {
        Err(format!("{} lines unclaimed, first {:?}", unclaimed.len(), board.lines[unclaimed[0]].map(paper_name)))
    }
}

#[cfg(test)]
mod tests {
    use super::BlockGame;
    use std::collections::HashMap;

    fn wins(size: usize, edges: &[&[usize]]) -> bool {
        let edges = edges.iter().map(|e| e.iter().fold(0u32, |m, &i| m | 1 << i)).collect();
        BlockGame { size, edges, memo: HashMap::new() }.breaker_wins(0, 0)
    }

    #[test]
    fn small_games() {
        assert!(wins(2, &[&[0, 1]]), "a pair");
        assert!(!wins(1, &[&[0]]), "Maker takes a one-cell edge");
        assert!(!wins(3, &[&[0, 1], &[0, 2]]), "two edges through Maker's first cell");
        // The 3x3 grid with its rows and columns (write-up section 5): Breaker wins.
        let rc: [&[usize]; 6] = [&[0, 1, 2], &[3, 4, 5], &[6, 7, 8], &[0, 3, 6], &[1, 4, 7], &[2, 5, 8]];
        assert!(wins(9, &rc));
        // Add one diagonal and Maker wins (Maker takes the center; write-up section 5).
        let mut with_diag: Vec<&[usize]> = rc.to_vec();
        with_diag.push(&[0, 4, 8]);
        assert!(!wins(9, &with_diag));
    }
}

#[cfg(test)]
mod cover_file {
    /// The static 7x7x7 cover in `cover7.txt` (found by gen/gen.py and
    /// gen/cover_export.py) passes the checker: this test is the whole proof
    /// that Breaker wins 7x7x7, given the composition argument.
    #[test]
    fn cover7_is_a_breaker_win() {
        let board = crate::board::Board::new();
        let path = concat!(env!("CARGO_MANIFEST_DIR"), "/cover7.txt");
        assert_eq!(super::run(&board, path), Ok(()));
    }
}
