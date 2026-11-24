//! Loads data6.json (data5.json with the n5 feature; made by gen/gen.py) and expands the layout templates by
//! the cube's 48 symmetries. Position keys use the full line-automorphism group (`full_group`).

use crate::bits::{Cells, Lines, CELLS, LINES, SIDE};
use crate::subgame::SubGames;
use serde::Deserialize;
use std::collections::{HashMap, HashSet};

#[derive(Deserialize)]
struct Raw {
    lines: Vec<Vec<usize>>,
    syms: Vec<Vec<usize>>,
    blocks: Vec<RawBlock>,
    templates: Vec<Vec<usize>>,
}
#[derive(Deserialize)]
struct RawBlock {
    cells: Vec<usize>,
    lines: Vec<usize>,
    #[serde(default)]
    conditional: bool,
}

/// Local masks are u16: a block's cells and its claimed edges each fit in 16 bits.
const MAX_BLOCK_BITS: usize = 16;

/// The lines of the cube (148 for 6x6x6), generated from the geometry (each as
/// a sorted cell list), so a wrong line table in the data file can't change the
/// game solved.
fn cube_lines() -> HashSet<Vec<usize>> {
    let n = SIDE as i32;
    let mut out = HashSet::new();
    // the 26 nonzero directions in {-1,0,1}^3 (d = 13 is the zero vector)
    for d in (0..27).filter(|&d| d != 13) {
        let dir = [d % 3 - 1, d / 3 % 3 - 1, d / 9 - 1];
        for start in 0..CELLS as i32 {
            let p = [start % n, start / n % n, start / (n * n)];
            let pts: Vec<[i32; 3]> = (0..n).map(|i| [0, 1, 2].map(|k| p[k] + i * dir[k])).collect();
            if pts.iter().all(|q| q.iter().all(|&x| (0..n).contains(&x))) {
                let mut l: Vec<usize> = pts.iter().map(|q| (q[0] + n * q[1] + n * n * q[2]) as usize).collect();
                l.sort();
                out.insert(l);
            }
        }
    }
    out
}

fn factorial(k: usize) -> usize {
    (1..=k).product()
}

/// All orderings of 0..n.
fn permutations(n: usize) -> Vec<Vec<usize>> {
    if n == 0 {
        return vec![Vec::new()];
    }
    let mut out = Vec::new();
    for p in permutations(n - 1) {
        for i in 0..=p.len() {
            let mut q = p.clone();
            q.insert(i, n - 1);
            out.push(q);
        }
    }
    out
}

/// The cube's full line-automorphism group (docs/proof-format.md): an axis
/// permutation, a reflection per axis, and one value permutation p of 0..n-1
/// that commutes with v -> n-1-v, applied to every coordinate. 1,152 maps for
/// 6x6x6 and 192 for 5x5x5, the verifier's GROUP_SIZE; the data file's 48
/// geometric maps are a subgroup. Built here, not read from the data file.
fn full_group() -> Vec<[u8; CELLS]> {
    let n = SIDE;
    let flip = |v: usize| n - 1 - v;
    let vals: Vec<Vec<usize>> = permutations(n).into_iter().filter(|p| (0..n).all(|v| p[flip(v)] == flip(p[v]))).collect();
    let coord = |c: usize| [c % n, c / n % n, c / (n * n)];
    let axes_orders = [[0, 1, 2], [0, 2, 1], [1, 0, 2], [1, 2, 0], [2, 0, 1], [2, 1, 0]];
    let mut seen = HashSet::new();
    let mut group = Vec::new();
    for axes in axes_orders {
        for p in &vals {
            for refl in 0..8 {
                let mut g = [0u8; CELLS];
                for (c, slot) in g.iter_mut().enumerate() {
                    let q = coord(c);
                    let img: Vec<usize> = (0..3).map(|k| if refl >> k & 1 == 1 { flip(p[q[axes[k]]]) } else { p[q[axes[k]]] }).collect();
                    *slot = (img[0] + n * img[1] + n * n * img[2]) as u8;
                }
                if seen.insert(g) {
                    group.push(g);
                }
            }
        }
    }
    let expected = (1 << (2 + n / 2)) * 6 * factorial(n / 2);
    assert_eq!(group.len(), expected, "the full group has {} maps, expected {expected}", group.len());
    let lines = cube_lines();
    for g in &group {
        for l in &lines {
            let mut img: Vec<usize> = l.iter().map(|&c| g[c] as usize).collect();
            img.sort();
            assert!(lines.contains(&img), "a full-group map does not map lines to lines");
        }
    }
    group
}

/// Rejects input the search would otherwise trust: the line table, the
/// symmetry maps, block cells and lines, and template disjointness.
fn check_input(raw: &Raw) {
    let mut lines: Vec<Vec<usize>> = raw.lines.iter().map(|l| { let mut s = l.clone(); s.sort(); s }).collect();
    let as_set: HashSet<Vec<usize>> = lines.iter().cloned().collect();
    assert!(as_set.len() == LINES && as_set == cube_lines(), "the data file's lines are not the {LINES} cube lines");
    lines.sort();
    for (si, s) in raw.syms.iter().enumerate() {
        assert_eq!(s.len(), CELLS, "symmetry {si} has the wrong length");
        let mut hit = [false; CELLS];
        for &v in s {
            assert!(v < CELLS && !std::mem::replace(&mut hit[v], true), "symmetry {si} is not a permutation");
        }
        for l in &raw.lines {
            let mut img: Vec<usize> = l.iter().map(|&c| s[c]).collect();
            img.sort();
            assert!(as_set.contains(&img), "symmetry {si} does not map lines to lines");
        }
    }
    for (bi, b) in raw.blocks.iter().enumerate() {
        let mut c = b.cells.clone();
        c.sort();
        assert!(c.windows(2).all(|w| w[0] < w[1]) && c.iter().all(|&x| x < CELLS), "block {bi} has repeated or out-of-range cells");
        assert!(c.len() <= MAX_BLOCK_BITS, "block {bi} has more than {MAX_BLOCK_BITS} cells");
        let mut l = b.lines.clone();
        l.sort();
        assert!(l.windows(2).all(|w| w[0] < w[1]) && l.iter().all(|&x| x < LINES), "block {bi} has repeated or out-of-range lines");
        assert!(l.len() <= MAX_BLOCK_BITS, "block {bi} claims more than {MAX_BLOCK_BITS} lines");
    }
    for (ti, t) in raw.templates.iter().enumerate() {
        let mut used = HashSet::new();
        for &bi in t {
            assert!(bi < raw.blocks.len(), "template {ti} names a missing block");
            assert!(raw.blocks[bi].cells.iter().all(|&c| used.insert(c)), "template {ti} has overlapping blocks");
        }
    }
}

/// A small grid where Breaker, answering inside it, provably claims a cell of
/// every line in `lines` (checked exactly by gen/mb.py).
pub struct Block {
    pub cells: Cells,
    pub lines: Lines,
    /// the block's cells in local order (bit i of a local mask = cell_list[i])
    pub cell_list: Vec<usize>,
    /// sub-game shape id in `Data::subgames`
    pub shape: u16,
    /// the line behind each edge of the shape, in the shape's edge order
    pub edge_lines: Vec<usize>,
    /// Maker wins this sub-game from scratch: usable only where dead lines
    /// (already holding a Breaker mark) make it a Breaker win
    pub conditional: bool,
}

impl Block {
    pub fn local(&self, set: &Cells) -> u16 {
        self.cell_list.iter().enumerate().fold(0, |m, (i, &c)| if set.has(c) { m | 1 << i } else { m })
    }
}

pub struct Data {
    pub line_cells: Vec<[usize; crate::bits::SIDE]>,
    pub line_mask: Vec<Cells>,
    /// lines through each cell
    pub cell_lines: Vec<Vec<usize>>,
    pub blocks: Vec<Block>,
    /// each template is a set of pairwise disjoint block ids
    pub templates: Vec<Vec<usize>>,
    /// the 48 geometric symmetries (from the data file): template expansion
    /// and first-move class numbering
    pub syms: Vec<[u8; CELLS]>,
    /// the full line-automorphism group: keys for positions (`canonical`)
    pub full: Vec<[u8; CELLS]>,
    pub subgames: SubGames,
    /// false (env NOSUB set): drop any block Maker touches, the old rule
    pub use_subgames: bool,
    /// library blocks covering each line
    pub block_by_line: Vec<Vec<usize>>,
    /// templates (after symmetry expansion) that contain each library block
    pub templates_by_block: Vec<Vec<usize>>,
    /// false (env NOREPAIR set): skip the local-search leaf stage
    pub use_repair: bool,
}

impl Data {
    pub fn load(path: &str) -> Data {
        let raw: Raw = serde_json::from_str(&std::fs::read_to_string(path).expect("read data")).expect("parse data");
        assert_eq!(raw.lines.len(), LINES);
        check_input(&raw);
        let line_cells: Vec<[usize; crate::bits::SIDE]> = raw
            .lines
            .iter()
            .map(|l| l.clone().try_into().unwrap_or_else(|_| panic!("a line in the data file does not have {} cells", crate::bits::SIDE)))
            .collect();
        let line_mask: Vec<Cells> = line_cells
            .iter()
            .map(|l| l.iter().fold(Cells::EMPTY, |m, &c| m.with(c)))
            .collect();
        let mut cell_lines = vec![Vec::new(); CELLS];
        for (li, l) in line_cells.iter().enumerate() {
            for &c in l {
                cell_lines[c].push(li);
            }
        }
        // each block's sub-game: edges as local masks; identical shapes share an id
        let mut shape_ids: HashMap<(usize, Vec<u16>), u16> = HashMap::new();
        let mut shapes = Vec::new();
        let mut sizes = Vec::new();
        let blocks: Vec<Block> = raw
            .blocks
            .iter()
            .map(|b| {
                let mut cell_list = b.cells.clone();
                cell_list.sort();
                let mut edges: Vec<(u16, usize)> = b
                    .lines
                    .iter()
                    .map(|&li| {
                        let m = cell_list.iter().enumerate().fold(0u16, |m, (i, c)| {
                            if raw.lines[li].contains(c) { m | 1 << i } else { m }
                        });
                        (m, li)
                    })
                    .collect();
                edges.sort();
                let key = (cell_list.len(), edges.iter().map(|e| e.0).collect::<Vec<_>>());
                let shape = *shape_ids.entry(key.clone()).or_insert_with(|| {
                    shapes.push(key.1.clone());
                    sizes.push(key.0 as u32);
                    u16::try_from(shapes.len() - 1).expect("more than 65,536 block shapes")
                });
                Block {
                    cells: b.cells.iter().fold(Cells::EMPTY, |m, &c| m.with(c)),
                    lines: b.lines.iter().fold(Lines::EMPTY, |m, &l| m.with(l)),
                    cell_list,
                    shape,
                    edge_lines: edges.iter().map(|e| e.1).collect(),
                    conditional: b.conditional,
                }
            })
            .collect();
        let subgames = SubGames::new(shapes, sizes);
        // an unconditional block is trusted untouched (check::block_holds), so
        // solve each of their shapes once from the empty block here
        let mut solved = HashSet::new();
        for (bi, b) in blocks.iter().enumerate() {
            if !b.conditional && solved.insert(b.shape) {
                assert!(subgames.breaker_holds(b.shape, 0, 0, 0), "block {bi} is marked unconditional but Maker wins it");
            }
        }
        let syms: Vec<[u8; CELLS]> = raw
            .syms
            .iter()
            .map(|s| {
                let mut a = [0u8; CELLS];
                for (i, &v) in s.iter().enumerate() {
                    a[i] = v as u8;
                }
                a
            })
            .collect();
        // expand templates by symmetry (the block library is closed under symmetry)
        let by_cells: HashMap<Cells, usize> = blocks.iter().enumerate().map(|(i, b)| (b.cells, i)).collect();
        let mut seen = HashSet::new();
        let mut templates = Vec::new();
        for t in &raw.templates {
            for s in &syms {
                let mut img: Vec<usize> = t
                    .iter()
                    .map(|&bi| {
                        let moved = blocks[bi].cells.iter().fold(Cells::EMPTY, |m, c| m.with(s[c] as usize));
                        let img = *by_cells.get(&moved).expect("block library not closed under symmetry");
                        let lines = blocks[bi].lines.iter().map(|li| {
                            let mut l: Vec<usize> = line_cells[li].iter().map(|&c| s[c] as usize).collect();
                            l.sort();
                            l
                        });
                        let claimed: HashSet<Vec<usize>> = blocks[img].lines.iter().map(|li| { let mut l = line_cells[li].to_vec(); l.sort(); l }).collect();
                        assert!(lines.into_iter().all(|l| claimed.contains(&l)), "block {img} is not the symmetric image of block {bi}");
                        img
                    })
                    .collect();
                img.sort();
                if seen.insert(img.clone()) {
                    templates.push(img);
                }
            }
        }
        let use_subgames = std::env::var("NOSUB").is_err();
        let mut block_by_line = vec![Vec::new(); LINES];
        for (bi, b) in blocks.iter().enumerate() {
            for li in b.lines.iter() {
                block_by_line[li].push(bi);
            }
        }
        let use_repair = std::env::var("NOREPAIR").is_err();
        let mut templates_by_block = vec![Vec::new(); blocks.len()];
        for (ti, t) in templates.iter().enumerate() {
            for &bi in t {
                templates_by_block[bi].push(ti);
            }
        }
        Data {
            line_cells,
            line_mask,
            cell_lines,
            blocks,
            templates,
            syms,
            full: full_group(),
            subgames,
            use_subgames,
            block_by_line,
            use_repair,
            templates_by_block,
        }
    }

    /// Lines with no Breaker mark.
    pub fn live_lines(&self, breaker: &Cells) -> Lines {
        let mut live = Lines::EMPTY;
        for (li, m) in self.line_mask.iter().enumerate() {
            if !m.meets(breaker) {
                live.insert(li);
            }
        }
        live
    }

    pub fn map_cells(&self, s: usize, set: &Cells) -> Cells {
        set.iter().fold(Cells::EMPTY, |m, c| m.with(self.syms[s][c] as usize))
    }

    /// Canonical form of a position under the full group: the search's key
    /// for Maker-move classes, memo, CACHE, and HARD. The verifier looks
    /// records up by the same group, so one record serves a whole class.
    pub fn canonical(&self, maker: &Cells, breaker: &Cells) -> (Cells, Cells) {
        let map = |g: &[u8; CELLS], set: &Cells| set.iter().fold(Cells::EMPTY, |m, c| m.with(g[c] as usize));
        let mut best = (map(&self.full[0], maker), map(&self.full[0], breaker));
        for g in &self.full[1..] {
            // most maps lose on the Maker cells alone; skip mapping Breaker's then
            let m = map(g, maker);
            if m > best.0 {
                continue;
            }
            let pos = (m, map(g, breaker));
            if pos < best {
                best = pos;
            }
        }
        best
    }

    /// Canonical form under the 48 geometric symmetries only: numbers the
    /// first-move classes (0..10 for 6x6x6), which `prove` and the docs use.
    pub fn canonical_geometric(&self, maker: &Cells, breaker: &Cells) -> (Cells, Cells) {
        (0..self.syms.len())
            .map(|s| (self.map_cells(s, maker), self.map_cells(s, breaker)))
            .min()
            .unwrap()
    }
}

#[cfg(all(test, not(feature = "n5")))]
mod tests {
    use super::*;

    #[test]
    fn full_group_contains_the_geometric_maps_and_keys_are_invariant() {
        let d = Data::load(crate::bits::DATA_FILE);
        assert_eq!(d.full.len(), 1152);
        let full: HashSet<[u8; CELLS]> = d.full.iter().copied().collect();
        assert!(d.syms.iter().all(|s| full.contains(s)), "a geometric map is missing from the full group");
        // random positions: every image under the group has the same key
        let mut x = 0x9E37_79B9_7F4A_7C15u64;
        let mut next = || {
            x ^= x << 13;
            x ^= x >> 7;
            x ^= x << 17;
            (x % CELLS as u64) as usize
        };
        for _ in 0..20 {
            let (mut m, mut b) = (Cells::EMPTY, Cells::EMPTY);
            for _ in 0..5 {
                m.insert(next());
            }
            for _ in 0..4 {
                let c = next();
                if !m.has(c) {
                    b.insert(c);
                }
            }
            let key = d.canonical(&m, &b);
            for g in d.full.iter().step_by(37) {
                let img = |s: &Cells| s.iter().fold(Cells::EMPTY, |a, c| a.with(g[c] as usize));
                assert_eq!(d.canonical(&img(&m), &img(&b)), key);
            }
        }
        // the full group merges geometric first-move classes: 10 become 3
        let e = Cells::EMPTY;
        let classes: HashSet<_> = (0..CELLS).map(|c| d.canonical(&e.with(c), &e)).collect();
        assert_eq!(classes.len(), 3);
    }
}
