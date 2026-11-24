//! Second-stage leaf check: local search over block choices when no fixed
//! template pairs up. The pairing usually fails on a few lines whose cells the
//! template's blocks occupy, so each step looks only at the lines the matching
//! leaves unserved: drop a block that sits on one of their cells, or add a
//! library block that covers one (evicting any block it overlaps).

use crate::bits::{Cells, Lines};
use crate::check::{block_holds, Cert};
use crate::data::Data;

/// Search steps per starting template before giving up.
const STEPS: usize = 60;
/// Steps without a new best deficit before giving up early.
const PATIENCE: usize = 8;
/// Moves examined per step (the focused candidates, then a cutoff).
const MAX_MOVES: usize = 48;

/// Max matching of two slots per needed line onto free cells. Returns the
/// number of unfilled slots and the lines that own them.
fn deficit(data: &Data, need: &Lines, free: &Cells) -> (usize, Vec<usize>) {
    let lines: Vec<usize> = need.iter().collect();
    let (_, unmatched) = crate::check::match_lines(data, &lines, free, false);
    let mut short: Vec<usize> = unmatched.iter().map(|&s| lines[s / 2]).collect();
    short.dedup();
    (unmatched.len(), short)
}

struct State<'a> {
    data: &'a Data,
    live: Lines,
    /// cells a pair may use: empty cells not inside a chosen block
    empty: Cells,
    chosen: Vec<usize>,
}

impl State<'_> {
    fn score(&self, chosen: &[usize]) -> (usize, Vec<usize>, Lines, Cells) {
        let mut cover = Lines::EMPTY;
        let mut used = Cells::EMPTY;
        for &bi in chosen {
            cover = cover.or(&self.data.blocks[bi].lines);
            used = used.or(&self.data.blocks[bi].cells);
        }
        let need = self.live.minus(&cover);
        let free = self.empty.minus(&used);
        let (d, short) = deficit(self.data, &need, &free);
        (d, short, need, free)
    }
}

/// Tries to turn the given starting blocks (already checked to hold) into a
/// certificate. Deterministic: ties go to the first move found.
pub fn repair(
    data: &Data,
    start: Vec<usize>,
    maker: &Cells,
    breaker: &Cells,
) -> Option<Cert> {
    let live = data.live_lines(breaker);
    let empty = Cells::all().minus(maker).minus(breaker);
    let mut st = State { data, live, empty, chosen: start };
    let mut held_cache: Vec<Option<bool>> = vec![None; data.blocks.len()];
    let mut holds = |bi: usize| *held_cache[bi].get_or_insert_with(|| block_holds(data, bi, maker, breaker));
    let (mut cur, mut short, _, _) = st.score(&st.chosen);
    let mut tabu: Vec<usize> = Vec::new();
    let (mut best_seen, mut since_best) = (cur, 0);
    for _ in 0..STEPS {
        if cur == 0 || since_best >= PATIENCE {
            break;
        }
        // focused moves around the lines the matching can't serve
        let mut moves: Vec<Vec<usize>> = Vec::new();
        'gather: for &li in &short {
            for &c in &data.line_cells[li] {
                if let Some(pos) = st.chosen.iter().position(|&bi| data.blocks[bi].cells.has(c)) {
                    let mut next = st.chosen.clone();
                    next.remove(pos);
                    moves.push(next);
                }
            }
            for &bi in &data.block_by_line[li] {
                if st.chosen.contains(&bi) || tabu.contains(&bi) || !holds(bi) {
                    continue;
                }
                let cells = data.blocks[bi].cells;
                let mut next: Vec<usize> =
                    st.chosen.iter().copied().filter(|&o| !data.blocks[o].cells.meets(&cells)).collect();
                next.push(bi);
                moves.push(next);
                if moves.len() >= MAX_MOVES {
                    break 'gather;
                }
            }
        }
        let best = moves
            .into_iter()
            .map(|m| {
                let (d, s, _, _) = st.score(&m);
                (d, m, s)
            })
            .min_by_key(|x| x.0);
        let Some((d, m, s)) = best else { break };
        // take the best move even if it's no better (plateau walk); tabu the
        // blocks it dropped so the walk doesn't undo itself at once
        for &o in &st.chosen {
            if !m.contains(&o) {
                tabu.push(o);
            }
        }
        if tabu.len() > 16 {
            tabu.drain(..tabu.len() - 16);
        }
        st.chosen = m;
        cur = d;
        short = s;
        if cur < best_seen {
            (best_seen, since_best) = (cur, 0);
        } else {
            since_best += 1;
        }
    }
    if cur != 0 {
        return None;
    }
    let (_, _, need, free) = st.score(&st.chosen);
    let pairs = crate::check::pair_lines(data, &need, &free)?;
    Some(Cert { blocks: st.chosen, pairs })
}
