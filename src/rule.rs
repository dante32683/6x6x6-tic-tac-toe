//! Explicit reply rules for Breaker's opening replies (docs/rule.md).
//!
//! A rule is a lexicographic order on the empty cells: a comma-separated list
//! of feature names (below), each smaller-is-better, with `-` in front to
//! flip one; the lowest cell id breaks what ties remain. Features are read in
//! the position's own orientation, which for the search is the frame of the
//! first move it was started from (cell 0, 2, or 8), so "core" and "mid" mean
//! what docs/strategy.md draws.
//!
//! Depth 1 (Breaker's first reply) ignores the spec: the reply is the core
//! cell farthest from Maker's mark (keys `diag,layer,dist2`), which is (3,3,3)
//! for each of the proof's first moves, on Maker's own diagonal against a
//! corner. Every later depth uses the spec.
//!
//! Features (each a small integer per cell):
//! - `diag`: 0 on a space diagonal, 1 off them.
//! - `fresh`: 0 when the cell's diagonal has no Breaker mark (off-diagonal: 1).
//! - `clean`: 0 when the cell's diagonal has no Maker mark (off-diagonal: 1).
//! - `layer`: the cell's layer ranked by `LAYER_ORDER` for this depth (off-diagonal: 3).
//! - `s1`: minus the live lines through the cell that hold a Maker mark.
//! - `es`: minus the Erdos-Selfridge potential of the cell: the sum, over live
//!   lines through it, of 2 to the number of Maker marks on the line.
//! - `near`: the least Chebyshev distance from the cell to a Maker mark.
//! - `dist2`: minus the sum of squared distances from the cell to Maker's marks.
//! - `shared`: lines through the cell that already hold a Breaker mark.
//! - `mdiag`: Maker marks on the cell's diagonal (off-diagonal: 9).

use crate::bits::{Cells, SIDE};
use crate::data::Data;

/// Layers of a space-diagonal cell by its coordinate values (all three in the
/// same pair): 0 core {2,3}, 1 mid {1,4}, 2 corner {0,5}.
const CORE: usize = 0;
const MID: usize = 1;
const CORNER: usize = 2;

/// Preferred layer order per depth (Maker marks on the board), measured on
/// the proof's R replies (docs/patterns.md): depth 1 always core, depth 2
/// mid 99%, depth 3 core 66% / mid 20% / corner 14%. Index = layer, value = rank.
fn layer_rank(depth: usize, layer: usize) -> i64 {
    let order: [usize; 3] = match depth {
        2 => [MID, CORNER, CORE],
        _ => [CORE, MID, CORNER],
    };
    order.iter().position(|&l| l == layer).unwrap() as i64
}

fn xyz(c: usize) -> [i64; 3] {
    [(c / (SIDE * SIDE)) as i64, ((c / SIDE) % SIDE) as i64, (c % SIDE) as i64]
}

/// The space diagonal through `c` (0..4) and its layer, or None off them.
pub fn diagonal(c: usize) -> Option<(usize, usize)> {
    let [x, y, z] = xyz(c);
    let n = SIDE as i64 - 1;
    // a space-diagonal cell has each coordinate equal to t or n - t
    let t = x;
    let flip = |v: i64| if v == t { Some(false) } else if v == n - t { Some(true) } else { None };
    let (fy, fz) = (flip(y)?, flip(z)?);
    // when t == n - t (odd sides) the flips are ambiguous; 6x6x6 has no such cell
    let diag = (fy as usize) * 2 + fz as usize;
    let layer = t.min(n - t) as usize; // 0 corner, 1 mid, 2 core on 6x6x6
    Some((diag, 2 - layer.min(2)))
}

#[derive(Clone, Copy, Debug)]
enum Feature {
    Diag,
    Fresh,
    Clean,
    Layer,
    S1,
    Es,
    Near,
    Dist2,
    Shared,
    MDiag,
}

#[derive(Clone, Debug)]
pub struct Rule {
    pub spec: String,
    keys: Vec<(Feature, bool)>,
}

/// The rule `RULE=default` names: a space-diagonal cell, on a diagonal with
/// no Breaker mark, then one with no Maker mark, then the depth's usual
/// layer, then farthest from Maker's marks (docs/rule.md has the
/// measurements behind the choice).
pub const DEFAULT_RULE: &str = "diag,fresh,clean,layer,dist2";

/// Breaker's first reply, whatever the spec: the core cell farthest from Maker.
const FIRST_REPLY: [(Feature, bool); 3] = [(Feature::Diag, false), (Feature::Layer, false), (Feature::Dist2, false)];

impl Rule {
    pub fn parse(spec: &str) -> Result<Rule, String> {
        let spec = if spec == "default" { DEFAULT_RULE } else { spec };
        let mut keys = Vec::new();
        for t in spec.split(',').map(str::trim).filter(|t| !t.is_empty()) {
            let (flip, name) = match t.strip_prefix('-') {
                Some(n) => (true, n),
                None => (false, t),
            };
            let f = match name {
                "diag" => Feature::Diag,
                "fresh" => Feature::Fresh,
                "clean" => Feature::Clean,
                "layer" => Feature::Layer,
                "s1" => Feature::S1,
                "es" => Feature::Es,
                "near" => Feature::Near,
                "dist2" => Feature::Dist2,
                "shared" => Feature::Shared,
                "mdiag" => Feature::MDiag,
                _ => return Err(format!("unknown rule feature {name:?} in {spec:?}")),
            };
            keys.push((f, flip));
        }
        Ok(Rule { spec: spec.to_string(), keys })
    }

    /// Every empty cell with its key (smaller is better); the rule's reply is
    /// the least key, ties to the lowest cell id.
    pub fn keyed(&self, d: &Data, maker: &Cells, breaker: &Cells) -> Vec<(Vec<i64>, usize)> {
        let depth = maker.count() as usize;
        let keys: &[(Feature, bool)] = if depth <= 1 { &FIRST_REPLY } else { &self.keys };
        let empty = Cells::all().minus(maker).minus(breaker);
        let live = d.live_lines(breaker);
        let mut bdiag = [false; 4];
        let mut mdiag = [0i64; 4];
        for c in breaker.iter() {
            if let Some((g, _)) = diagonal(c) {
                bdiag[g] = true;
            }
        }
        for c in maker.iter() {
            if let Some((g, _)) = diagonal(c) {
                mdiag[g] += 1;
            }
        }
        let marks: Vec<[i64; 3]> = maker.iter().map(xyz).collect();
        empty
            .iter()
            .map(|c| {
                let dg = diagonal(c);
                let p = xyz(c);
                let key = keys
                    .iter()
                    .map(|&(f, flip)| {
                        let v = match f {
                            Feature::Diag => dg.is_none() as i64,
                            Feature::Fresh => dg.map_or(1, |(g, _)| bdiag[g] as i64),
                            Feature::Clean => dg.map_or(1, |(g, _)| (mdiag[g] > 0) as i64),
                            Feature::Layer => dg.map_or(3, |(_, l)| layer_rank(depth, l)),
                            Feature::MDiag => dg.map_or(9, |(g, _)| mdiag[g]),
                            Feature::S1 => -(d.cell_lines[c].iter().filter(|&&li| live.has(li) && d.line_mask[li].meets(maker)).count() as i64),
                            Feature::Es => -d.cell_lines[c].iter().filter(|&&li| live.has(li)).map(|&li| 1i64 << d.line_mask[li].and(maker).count()).sum::<i64>(),
                            Feature::Shared => d.cell_lines[c].iter().filter(|&&li| !live.has(li)).count() as i64,
                            Feature::Near => marks.iter().map(|q| (0..3).map(|i| (p[i] - q[i]).abs()).max().unwrap()).min().unwrap_or(0),
                            Feature::Dist2 => -marks.iter().map(|q| (0..3).map(|i| (p[i] - q[i]).pow(2)).sum::<i64>()).sum::<i64>(),
                        };
                        if flip {
                            -v
                        } else {
                            v
                        }
                    })
                    .collect();
                (key, c)
            })
            .collect()
    }

    /// The rule's reply: the empty cell with the least key, lowest id on ties.
    /// None on a full board.
    pub fn reply(&self, d: &Data, maker: &Cells, breaker: &Cells) -> Option<usize> {
        self.keyed(d, maker, breaker).into_iter().min().map(|(_, c)| c)
    }

    /// The cells tied for the least key (the id tiebreak picks the first).
    pub fn top(&self, d: &Data, maker: &Cells, breaker: &Cells) -> Vec<usize> {
        let k = self.keyed(d, maker, breaker);
        let Some(best) = k.iter().map(|(v, _)| v).min().cloned() else { return Vec::new() };
        k.into_iter().filter(|(v, _)| *v == best).map(|(_, c)| c).collect()
    }
}

/// The rule from env `RULE` (unset: none). A bad spec stops the run.
pub fn from_env() -> Option<Rule> {
    let v = std::env::var("RULE").ok()?;
    Some(Rule::parse(&v).unwrap_or_else(|e| panic!("RULE: {e}")))
}

#[cfg(all(test, not(feature = "n5")))]
mod tests {
    use super::*;
    use crate::bits::CELLS;

    #[test]
    fn diagonals_have_six_cells_two_per_layer() {
        let mut count = [[0; 3]; 4];
        for c in 0..CELLS {
            if let Some((g, l)) = diagonal(c) {
                count[g][l] += 1;
            }
        }
        assert_eq!(count, [[2; 3]; 4]);
        assert_eq!(diagonal(129), Some((0, CORE))); // (3,3,3)
        assert_eq!(diagonal(0), Some((0, CORNER)));
        assert_eq!(diagonal(43), Some((0, MID))); // (1,1,1)
        assert_eq!(diagonal(1), None);
    }

    #[test]
    fn default_rule_opens_in_the_far_core_for_every_proof_first_move() {
        let d = Data::load(crate::bits::DATA_FILE);
        let r = Rule::parse("default").unwrap();
        for m in [0, 2, 8] {
            assert_eq!(r.reply(&d, &Cells::EMPTY.with(m), &Cells::EMPTY), Some(129), "first move {m}");
        }
        assert!(Rule::parse("diag,bogus").is_err());
    }

    /// The replay (src/replay.rs) relies on this: every feature is
    /// geometric, so a cell's key is the same in all 48 orientations.
    #[test]
    fn keys_are_the_same_in_every_geometric_orientation() {
        let d = Data::load(crate::bits::DATA_FILE);
        let r = Rule::parse("diag,fresh,clean,layer,dist2,s1,es,near,shared,mdiag").unwrap();
        let positions = [(vec![0, 87, 168], vec![64, 129]), (vec![8, 18, 30], vec![129, 154]), (vec![2, 100], vec![129])];
        for (m, b) in positions {
            let (m, b) = (m.into_iter().fold(Cells::EMPTY, |a, c| a.with(c)), b.into_iter().fold(Cells::EMPTY, |a, c| a.with(c)));
            let base: std::collections::HashMap<usize, Vec<i64>> = r.keyed(&d, &m, &b).into_iter().map(|(k, c)| (c, k)).collect();
            for s in 0..d.syms.len() {
                let mapped = r.keyed(&d, &d.map_cells(s, &m), &d.map_cells(s, &b));
                for (k, c) in mapped {
                    let pre = (0..CELLS).find(|&p| d.syms[s][p] as usize == c).unwrap();
                    assert_eq!(base[&pre], k, "map {s}, cell {pre}");
                }
            }
        }
    }

    #[test]
    fn second_reply_takes_a_mid_cell_of_an_untouched_diagonal() {
        let d = Data::load(crate::bits::DATA_FILE);
        let r = Rule::parse("default").unwrap();
        // Maker on corner 0 (diagonal 0) and corner 5 = (0,0,5) (diagonal 1); Breaker on (3,3,3)
        let (m, b) = (Cells::EMPTY.with(0).with(5), Cells::EMPTY.with(129));
        let c = r.reply(&d, &m, &b).unwrap();
        let (g, l) = diagonal(c).unwrap();
        assert!(g >= 2 && l == MID, "reply {c} on diagonal {g}, layer {l}");
    }
}
