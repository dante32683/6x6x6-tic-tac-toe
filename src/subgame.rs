//! Exact Maker-Breaker solver for one block (at most 16 cells), used to keep a
//! block in the certificate when it already has marks inside. Results are
//! cached across the whole search.

use crate::fasthash::FxDashMap;
use std::cell::RefCell;
use std::sync::atomic::{AtomicU32, Ordering::Relaxed};

/// Entries in each thread's direct-mapped cache in front of the shared memo
/// (16 bytes each, so 1 MB per thread). The shared map's lock atomics were
/// 15% of leaf-check time in a 2026-11-19 profile; most lookups repeat
/// recent ones.
const L1_SIZE: usize = 1 << 16;
/// Set on every stored L1 key, so an empty slot (0) never matches; shape ids
/// stay below 2^15 (checked in `SubGames::new`).
const L1_VALID: u64 = 1 << 63;

/// Shape ids mean something only inside one `SubGames`, so each instance gets
/// an id and a thread's L1 holds one instance's results at a time.
static NEXT_ID: AtomicU32 = AtomicU32::new(0);
const NO_OWNER: u32 = u32::MAX;

struct L1Cache {
    owner: u32,
    slots: Vec<(u64, bool)>,
}

thread_local! {
    static L1: RefCell<L1Cache> = RefCell::new(L1Cache { owner: NO_OWNER, slots: vec![(0, false); L1_SIZE] });
}

fn l1_slot(key: u64) -> usize {
    (key.wrapping_mul(0x9E37_79B9_7F4A_7C15) >> (64 - L1_SIZE.trailing_zeros())) as usize
}

fn l1_get(owner: u32, key: u64) -> Option<bool> {
    L1.with(|c| {
        let c = c.borrow();
        let (k, v) = c.slots[l1_slot(key)];
        (c.owner == owner && k == key | L1_VALID).then_some(v)
    })
}

fn l1_put(owner: u32, key: u64, v: bool) {
    L1.with(|c| {
        let mut c = c.borrow_mut();
        if c.owner != owner {
            c.slots.fill((0, false));
            c.owner = owner;
        }
        c.slots[l1_slot(key)] = (key | L1_VALID, v);
    });
}

/// (block shape, edges already dead, Maker cells, Breaker cells) in local
/// bits, packed into one word: 16 bits each.
type Key = u64;

fn key(shape: u16, dead: u16, m: u16, b: u16) -> Key {
    (shape as u64) << 48 | (dead as u64) << 32 | (m as u64) << 16 | b as u64
}

pub struct SubGames {
    /// per shape: the edges as local cell masks
    pub shapes: Vec<Vec<u16>>,
    pub full: Vec<u16>,
    memo: FxDashMap<Key, bool>,
    id: u32,
}

impl SubGames {
    pub fn new(shapes: Vec<Vec<u16>>, sizes: Vec<u32>) -> Self {
        assert!(shapes.len() < 1 << 15, "shape ids must leave the L1 valid bit free");
        let full = sizes.iter().map(|&n| ((1u32 << n) - 1) as u16).collect();
        let id = NEXT_ID.fetch_add(1, Relaxed);
        assert!(id != NO_OWNER, "too many SubGames instances");
        SubGames { shapes, full, memo: FxDashMap::default(), id }
    }

    /// True if Breaker, answering inside the block, keeps a cell in every edge
    /// not listed in `dead`, with Maker to move.
    pub fn breaker_holds(&self, shape: u16, dead: u16, m: u16, b: u16) -> bool {
        !self.maker_wins(shape, dead, m, b)
    }

    fn maker_wins(&self, shape: u16, dead: u16, m: u16, b: u16) -> bool {
        let key = key(shape, dead, m, b);
        if let Some(r) = l1_get(self.id, key) {
            return r;
        }
        if let Some(r) = self.memo.get(&key).map(|r| *r) {
            l1_put(self.id, key, r);
            return r;
        }
        let edges = &self.shapes[shape as usize];
        let live = || edges.iter().enumerate().filter(|&(i, &e)| dead >> i & 1 == 0 && e & b == 0).map(|(_, &e)| e);
        let free = self.full[shape as usize] & !(m | b);
        // the completed-edge test goes first: a full block can still hold a
        // finished Maker edge
        let result = if live().any(|e| (e & !m).count_ones() <= 1) {
            true // Maker has completed an edge, or completes one now
        } else if live().next().is_none() || free == 0 {
            false
        } else {
            let mut f = free;
            let mut win = false;
            while f != 0 {
                let c = f & f.wrapping_neg();
                f ^= c;
                if !self.breaker_reply_holds(shape, dead, m | c, b) {
                    win = true;
                    break;
                }
            }
            win
        };
        self.memo.insert(key, result);
        l1_put(self.id, key, result);
        result
    }

    /// Breaker to move: true if some reply keeps Breaker winning.
    fn breaker_reply_holds(&self, shape: u16, dead: u16, m: u16, b: u16) -> bool {
        let edges = &self.shapes[shape as usize];
        let free = self.full[shape as usize] & !(m | b);
        let mut threats = 0u16;
        for (i, &e) in edges.iter().enumerate() {
            if dead >> i & 1 == 0 && e & b == 0 {
                let rest = e & !m;
                if rest.count_ones() == 1 {
                    threats |= rest;
                }
            }
        }
        if threats.count_ones() >= 2 {
            return false;
        }
        let cands = if threats != 0 { threats } else { free };
        if cands == 0 {
            return true; // board full, every edge has a Breaker cell or is dead
        }
        let mut f = cands;
        while f != 0 {
            let c = f & f.wrapping_neg();
            f ^= c;
            if !self.maker_wins(shape, dead, m, b | c) {
                return true;
            }
        }
        false
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    /// 4x4 grid, cell i = 4*row + col: rows, columns, and both diagonals.
    fn grid4() -> SubGames {
        let mut e = Vec::new();
        for r in 0..4 {
            e.push((0..4).fold(0u16, |m, c| m | 1 << (4 * r + c)));
            e.push((0..4).fold(0u16, |m, c| m | 1 << (4 * c + r)));
        }
        e.push((0..4).fold(0u16, |m, i| m | 1 << (5 * i)));
        e.push((0..4).fold(0u16, |m, i| m | 1 << (3 * i + 3)));
        SubGames::new(vec![e], vec![16])
    }

    #[test]
    fn empty_4x4_is_breaker_win() {
        assert!(grid4().breaker_holds(0, 0, 0, 0));
    }

    #[test]
    fn one_answered_maker_mark_still_holds() {
        let g = grid4();
        // Maker played a corner, Breaker answered: still a Breaker win (it's
        // a position from Breaker's own winning strategy, for some answer)
        let held = (1..16).any(|b| g.breaker_holds(0, 0, 1, 1 << b));
        assert!(held);
        // an unanswered extra Maker mark, Maker to move again
        println!("corner unanswered holds: {}", g.breaker_holds(0, 0, 1, 0));
        println!("center unanswered holds: {}", g.breaker_holds(0, 0, 1 << 5, 0));
        // cell 0 lies on edge 0 (row 0), edge 1 (column 0), and edge 8 (main diagonal)
        const CORNER_EDGES: u16 = 1 << 0 | 1 << 1 | 1 << 8;
        println!("corner, its 3 lines dead: {}", g.breaker_holds(0, CORNER_EDGES, 1, 0));
    }
}
