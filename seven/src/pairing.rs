//! Pairing check: does every surviving line get two free cells of its own?
//!
//! This is the paper's X(G)-perfect matching (section 3.1): each surviving
//! line is two "slots", each slot needs a distinct free cell on its line, and
//! a cell serves at most one slot. Found by augmenting paths (Kuhn), which is
//! all Hopcroft-Karp speeds up. Every pairing returned is checked by
//! `validate`, so a reported success never rests on the matching code.

use crate::board::{Board, CELLS};

const NONE: usize = usize::MAX;

pub struct Matcher {
    /// Survivor lines (indices into `Board::lines`), in board order.
    pub survivors: Vec<usize>,
    /// Free cells of each survivor (Maker's cells removed).
    pub free: Vec<Vec<usize>>,
    /// Index into `survivors` for each board line, or NONE if dead.
    pub survivor_of: Vec<usize>,
    /// Survivor index for each slot (two slots per survivor; `surplus` adds more).
    pub slot_line: Vec<usize>,
    pub slot_cell: Vec<usize>,
    pub cell_slot: Vec<usize>,
    seen: Vec<u32>,
    stamp: u32,
}

impl Matcher {
    pub fn new() -> Matcher {
        Matcher {
            survivors: Vec::with_capacity(200),
            free: Vec::with_capacity(200),
            survivor_of: vec![NONE; 200],
            slot_line: Vec::with_capacity(400),
            slot_cell: Vec::with_capacity(400),
            cell_slot: vec![NONE; CELLS],
            seen: vec![0; CELLS],
            stamp: 0,
        }
    }

    /// Set up the position: `maker` and `breaker` are the occupied cells.
    pub fn load(&mut self, board: &Board, maker: &[usize], breaker: &[usize]) {
        let mut is_m = [false; CELLS];
        let mut is_b = [false; CELLS];
        for &c in maker {
            is_m[c] = true;
        }
        for &c in breaker {
            assert!(!is_m[c], "a cell held by both players");
            is_b[c] = true;
        }
        self.survivors.clear();
        self.free.clear();
        self.survivor_of.clear();
        self.survivor_of.resize(board.lines.len(), NONE);
        for (i, l) in board.lines.iter().enumerate() {
            if l.iter().any(|&c| is_b[c]) {
                continue;
            }
            self.survivor_of[i] = self.survivors.len();
            self.survivors.push(i);
            self.free.push(l.iter().copied().filter(|&c| !is_m[c]).collect());
        }
        self.slot_line.clear();
        self.slot_line.extend((0..2 * self.survivors.len()).map(|s| s / 2));
        self.slot_cell.clear();
        self.slot_cell.resize(2 * self.survivors.len(), NONE);
        self.cell_slot.iter_mut().for_each(|s| *s = NONE);
    }

    fn augment(&mut self, slot: usize) -> bool {
        let line = self.slot_line[slot];
        // First a free cell nobody holds (cheap), then a path through a held one.
        for k in 0..self.free[line].len() {
            let c = self.free[line][k];
            if self.cell_slot[c] == NONE && self.seen[c] != self.stamp {
                self.seen[c] = self.stamp;
                self.cell_slot[c] = slot;
                self.slot_cell[slot] = c;
                return true;
            }
        }
        for k in 0..self.free[line].len() {
            let c = self.free[line][k];
            if self.seen[c] == self.stamp {
                continue;
            }
            self.seen[c] = self.stamp;
            let other = self.cell_slot[c];
            if other != NONE && self.augment(other) {
                self.cell_slot[c] = slot;
                self.slot_cell[slot] = c;
                return true;
            }
        }
        false
    }

    fn next_stamp(&mut self) {
        self.stamp = self.stamp.wrapping_add(1);
        if self.stamp == 0 {
            self.seen.iter_mut().for_each(|s| *s = 0);
            self.stamp = 1;
        }
    }

    /// Match every slot; returns the number of slots left unmatched (0 means a pairing exists).
    pub fn solve(&mut self) -> usize {
        let mut missing = 0;
        for s in 0..self.slot_cell.len() {
            self.next_stamp();
            if !self.augment(s) {
                missing += 1;
            }
        }
        missing
    }

    /// The pairing as (board line, cell, cell), after a successful `solve`.
    pub fn pairs(&self) -> Vec<(usize, usize, usize)> {
        (0..self.survivors.len())
            .map(|i| (self.survivors[i], self.slot_cell[2 * i], self.slot_cell[2 * i + 1]))
            .collect()
    }

    /// Lines in the largest tight set: survivor lines whose slots no free
    /// unmatched cell can reach by an alternating path. Their free cells are
    /// exactly their paired cells (Hall's condition holds with equality), so
    /// one more Maker mark among them would leave no pairing. Empty when the
    /// position has spare room everywhere.
    pub fn tight_lines(&self, board: &Board) -> Vec<usize> {
        let slots = 2 * self.survivors.len();
        let mut reached = vec![false; slots];
        let mut cell_done = vec![false; CELLS];
        let mut stack: Vec<usize> = Vec::new();
        for line in 0..self.survivors.len() {
            for &c in &self.free[line] {
                if self.cell_slot[c] == NONE && !cell_done[c] {
                    cell_done[c] = true;
                    stack.push(c);
                }
            }
        }
        while let Some(c) = stack.pop() {
            for &bl in &board.through[c] {
                let sv = self.survivor_of[bl];
                if sv == NONE || !self.free[sv].contains(&c) {
                    continue;
                }
                for s in [2 * sv, 2 * sv + 1] {
                    if reached[s] || self.cell_slot[c] == s {
                        continue;
                    }
                    reached[s] = true;
                    let mate = self.slot_cell[s];
                    if !cell_done[mate] {
                        cell_done[mate] = true;
                        stack.push(mate);
                    }
                }
            }
        }
        (0..self.survivors.len())
            .filter(|&i| !reached[2 * i] && !reached[2 * i + 1])
            .map(|i| self.survivors[i])
            .collect()
    }

    /// Exact surplus: the largest k (up to `cap`) such that every set G of
    /// survivors has at least 2|G| + k free cells, so k + 1 extra Maker marks
    /// are needed to destroy every pairing. The surplus is at least k exactly
    /// when each single line can take k extra slots on top of a full pairing
    /// (Hall's theorem applied to the enlarged demand). Call after a
    /// successful `solve`; the pairing is restored afterwards.
    pub fn surplus(&mut self, cap: usize) -> usize {
        let base = 2 * self.survivors.len();
        let saved_slots = self.slot_cell.clone();
        let saved_cells = self.cell_slot.clone();
        let mut best = cap;
        for line in 0..self.survivors.len() {
            let mut ok = 0;
            while ok < best {
                self.slot_line.push(line);
                self.slot_cell.push(NONE);
                self.next_stamp();
                if !self.augment(self.slot_cell.len() - 1) {
                    break;
                }
                ok += 1;
            }
            best = best.min(ok);
            self.slot_line.truncate(base);
            self.slot_cell.clone_from(&saved_slots);
            self.cell_slot.clone_from(&saved_cells);
            if best == 0 {
                break;
            }
        }
        best
    }

    /// Check a pairing from scratch: each survivor has two distinct free cells
    /// of its own, and no cell is used twice.
    pub fn validate(&self, board: &Board, maker: &[usize], breaker: &[usize]) -> bool {
        let mut used = [false; CELLS];
        let mut is_occ = [false; CELLS];
        for &c in maker.iter().chain(breaker) {
            is_occ[c] = true;
        }
        let pairs = self.pairs();
        let mut covered = vec![false; board.lines.len()];
        for &(l, a, b) in &pairs {
            if a == NONE || b == NONE || a == b || is_occ[a] || is_occ[b] || used[a] || used[b] {
                return false;
            }
            if !board.lines[l].contains(&a) || !board.lines[l].contains(&b) {
                return false;
            }
            used[a] = true;
            used[b] = true;
            covered[l] = true;
        }
        // Every line must be dead (a Breaker cell) or paired.
        board.lines.iter().enumerate().all(|(i, l)| covered[i] || l.iter().any(|c| breaker.contains(c)))
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::board::{paper_cell, Board};

    #[test]
    fn empty_board_has_no_pairing() {
        // 193 lines need 386 cells and the board has 343.
        let b = Board::new();
        let mut m = Matcher::new();
        m.load(&b, &[], &[]);
        assert!(m.solve() >= 2 * 193 - 343);
    }

    #[test]
    fn paper_position_pairs_and_validation_catches_tampering() {
        let b = Board::new();
        let mut m = Matcher::new();
        let maker = [444, 111, 222, 333].map(paper_cell);
        let breaker = [555, 626, 117, 177].map(paper_cell);
        m.load(&b, &maker, &breaker);
        assert_eq!(m.survivors.len(), 166);
        assert_eq!(m.solve(), 0);
        assert!(m.validate(&b, &maker, &breaker));
        assert!(m.surplus(4) >= 1);
        // Point one slot at a Maker cell: validation must refuse it.
        m.slot_cell[0] = maker[1];
        assert!(!m.validate(&b, &maker, &breaker));
    }
}
