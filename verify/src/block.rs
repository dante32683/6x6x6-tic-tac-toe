//! The block game: plain minimax on a small set of cells.

use std::collections::HashMap;

/// Blocks have at most this many cells (masks are `u16`).
pub const MAX_BLOCK: usize = 16;

/// A block game in block-local bit masks. Maker moves first at the root.
/// Edges are the live claimed lines restricted to the block.
#[derive(Clone, PartialEq, Eq, Hash, Debug)]
pub struct Game {
    pub edges: Vec<u16>,
    pub maker: u16,
    pub breaker: u16,
    pub full: u16,
}

/// Memoizes finished block games across the whole proof.
#[derive(Default)]
pub struct Solver {
    results: HashMap<Game, bool>,
}

impl Solver {
    pub fn distinct_games(&self) -> usize {
        self.results.len()
    }

    /// True when Breaker wins `game` with Maker to move.
    pub fn breaker_wins(&mut self, game: &Game) -> bool {
        if let Some(&r) = self.results.get(game) {
            return r;
        }
        let mut seen = HashMap::new();
        let r = breaker_wins_from(&game.edges, game.full, game.maker, game.breaker, true, &mut seen);
        self.results.insert(game.clone(), r);
        r
    }
}

/// Breaker wins from this position (`maker_to_move` says whose turn it is).
/// A completed Maker edge is checked first, at every node, for either player.
fn breaker_wins_from(
    edges: &[u16],
    full: u16,
    maker: u16,
    breaker: u16,
    maker_to_move: bool,
    seen: &mut HashMap<(u16, u16), bool>,
) -> bool {
    if edges.iter().any(|&e| e & maker == e) {
        return false;
    }
    if edges.iter().all(|&e| e & breaker != 0) {
        return true;
    }
    if let Some(&r) = seen.get(&(maker, breaker)) {
        return r;
    }
    let empty = full & !(maker | breaker);
    let moves = (0..MAX_BLOCK).filter(|&i| empty >> i & 1 == 1);
    let result = if maker_to_move {
        // Breaker must win against every Maker move.
        moves.into_iter().all(|i| breaker_wins_from(edges, full, maker | 1 << i, breaker, false, seen))
    } else {
        moves.into_iter().any(|i| breaker_wins_from(edges, full, maker, breaker | 1 << i, true, seen))
    };
    seen.insert((maker, breaker), result);
    result
}

#[cfg(test)]
mod tests {
    use super::*;

    fn game(edges: &[u16], cells: usize) -> Game {
        Game { edges: edges.to_vec(), maker: 0, breaker: 0, full: ((1u32 << cells) - 1) as u16 }
    }

    #[test]
    fn tic_tac_toe_is_a_maker_win() {
        // 3x3 grid, cell = 3*row + col, its 8 lines.
        let rows = (0..3).map(|r| 7u16 << (3 * r));
        let cols = (0..3).map(|c| 0b001_001_001u16 << c);
        let diags = [0b100_010_001u16, 0b001_010_100u16];
        let edges: Vec<u16> = rows.chain(cols).chain(diags).collect();
        assert!(!Solver::default().breaker_wins(&game(&edges, 9)));
    }

    #[test]
    fn two_disjoint_pairs_are_a_breaker_win() {
        // Pairing strategy: edges {0,1} and {2,3}.
        assert!(Solver::default().breaker_wins(&game(&[0b0011, 0b1100], 4)));
    }

    #[test]
    fn crossing_pairs_let_maker_fork() {
        // Edges {0,1} and {0,2} share cell 0: Maker takes 0 and threatens both.
        assert!(!Solver::default().breaker_wins(&game(&[0b011, 0b101], 3)));
    }

    #[test]
    fn existing_breaker_mark_ends_the_game() {
        let mut g = game(&[0b0011], 4);
        g.breaker = 0b0001;
        assert!(Solver::default().breaker_wins(&g));
    }

    #[test]
    fn completed_maker_edge_is_a_loss_at_the_root() {
        let mut g = game(&[0b0011], 4);
        g.maker = 0b0011;
        assert!(!Solver::default().breaker_wins(&g));
    }
}
