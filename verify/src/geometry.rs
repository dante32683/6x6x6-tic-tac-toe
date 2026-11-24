//! The cube, its lines (148 for 6x6x6), and the line-automorphism group G, all
//! derived here from scratch.

use std::collections::HashSet;

/// Side length: 6, or 5 when built with `--features n5`.
#[cfg(not(feature = "n5"))]
pub const SIDE: usize = 6;
#[cfg(feature = "n5")]
pub const SIDE: usize = 5;
pub const CELLS: usize = SIDE * SIDE * SIDE;
/// ((n+2)^3 - n^3) / 2: 148 for n = 6, 109 for n = 5.
pub const LINES: usize = ((SIDE + 2).pow(3) - CELLS) / 2;
/// Dvořák and Valla (2021): |G| = 2^(d-1+k) d! k! with d = 3, k = floor(n/2);
/// 1,152 for n = 6, 192 for n = 5. build_group finds G by brute force and
/// this only checks the count.
pub const GROUP_SIZE: usize = (1 << (2 + SIDE / 2)) * 6 * factorial(SIDE / 2);
/// Value-permutation candidates tried per axis permutation and reflection mask: n!.
const VALUE_PERMS: usize = factorial(SIDE);

const fn factorial(n: usize) -> usize {
    if n == 0 { 1 } else { n * factorial(n - 1) }
}

/// A map of cells to cells, `map[c]` being the image of cell `c`.
pub type CellMap = [u8; CELLS];

/// A set of cells (ids below 216) as two 128-bit words.
#[derive(Clone, Copy, PartialEq, Eq, Hash, PartialOrd, Ord, Default, Debug)]
pub struct Set(u128, u128);

impl Set {
    pub fn has(self, c: usize) -> bool {
        if c < 128 { self.0 >> c & 1 == 1 } else { self.1 >> (c - 128) & 1 == 1 }
    }
    pub fn with(mut self, c: usize) -> Set {
        if c < 128 { self.0 |= 1 << c } else { self.1 |= 1 << (c - 128) }
        self
    }
    pub fn union(self, o: Set) -> Set {
        Set(self.0 | o.0, self.1 | o.1)
    }
    pub fn inter(self, o: Set) -> Set {
        Set(self.0 & o.0, self.1 & o.1)
    }
    pub fn minus(self, o: Set) -> Set {
        Set(self.0 & !o.0, self.1 & !o.1)
    }
    pub fn is_empty(self) -> bool {
        self.0 == 0 && self.1 == 0
    }
    pub fn len(self) -> usize {
        (self.0.count_ones() + self.1.count_ones()) as usize
    }
    /// The cells in increasing order.
    pub fn to_vec(self) -> Vec<usize> {
        (0..CELLS).filter(|&c| self.has(c)).collect()
    }
    pub fn from_cells(cells: &[usize]) -> Set {
        cells.iter().fold(Set::default(), |s, &c| s.with(c))
    }
    /// Comma-separated ids, or "-" when empty (the proof file's notation).
    pub fn show(self) -> String {
        if self.is_empty() {
            return "-".into();
        }
        self.to_vec().iter().map(|c| c.to_string()).collect::<Vec<_>>().join(",")
    }
}

pub struct Geometry {
    /// The 148 lines as cell sets.
    pub lines: Vec<Set>,
    /// `line_through[a * CELLS + b]` is the index of the line containing both
    /// distinct cells a and b, if any.
    line_through: Vec<Option<u8>>,
    /// The group G and each element's inverse.
    pub group: Vec<CellMap>,
    pub inverse: Vec<CellMap>,
}

fn cell_id(x: usize, y: usize, z: usize) -> usize {
    x * SIDE * SIDE + y * SIDE + z
}

fn coords(c: usize) -> [usize; 3] {
    [c / (SIDE * SIDE), c / SIDE % SIDE, c % SIDE]
}

/// Every set of 6 cells p, p+d, ..., p+5d inside the cube, d in {-1,0,1}^3
/// minus 0; d and -d give the same set, so sets are deduplicated.
fn build_lines() -> Vec<Set> {
    let mut seen = HashSet::new();
    let mut lines = Vec::new();
    for dx in -1i32..=1 {
        for dy in -1i32..=1 {
            for dz in -1i32..=1 {
                if (dx, dy, dz) == (0, 0, 0) {
                    continue;
                }
                for p in 0..CELLS {
                    let [x, y, z] = coords(p).map(|v| v as i32);
                    let inside = |v: i32, d: i32| (0..SIDE as i32).contains(&(v + (SIDE as i32 - 1) * d));
                    if !(inside(x, dx) && inside(y, dy) && inside(z, dz)) {
                        continue;
                    }
                    let mut s = Set::default();
                    for k in 0..SIDE as i32 {
                        s = s.with(cell_id((x + k * dx) as usize, (y + k * dy) as usize, (z + k * dz) as usize));
                    }
                    if seen.insert(s) {
                        lines.push(s);
                    }
                }
            }
        }
    }
    lines
}

fn permutations(n: usize) -> Vec<Vec<usize>> {
    if n == 0 {
        return vec![vec![]];
    }
    let mut out = Vec::new();
    for rest in permutations(n - 1) {
        for pos in 0..n {
            let mut p = rest.clone();
            p.insert(pos, n - 1);
            out.push(p);
        }
    }
    out
}

pub fn apply_map(map: &CellMap, s: Set) -> Set {
    s.to_vec().iter().fold(Set::default(), |acc, &c| acc.with(map[c] as usize))
}

/// All maps (x,y,z) -> reflect(t(coordinate p[i])) that send every line to a line.
fn build_group(lines: &[Set]) -> Vec<CellMap> {
    let line_set: HashSet<Set> = lines.iter().copied().collect();
    let axis_perms = permutations(3);
    let value_perms = permutations(SIDE);
    assert_eq!(value_perms.len(), VALUE_PERMS);
    let mut found: HashSet<CellMap> = HashSet::new();
    for p in &axis_perms {
        for mask in 0..8usize {
            for t in &value_perms {
                let mut map = [0u8; CELLS];
                for (c, slot) in map.iter_mut().enumerate() {
                    let v = coords(c);
                    let mut out = [0usize; 3];
                    for i in 0..3 {
                        let w = t[v[p[i]]];
                        out[i] = if mask >> i & 1 == 1 { SIDE - 1 - w } else { w };
                    }
                    *slot = cell_id(out[0], out[1], out[2]) as u8;
                }
                if lines.iter().all(|&l| line_set.contains(&apply_map(&map, l))) {
                    found.insert(map);
                }
            }
        }
    }
    let mut group: Vec<CellMap> = found.into_iter().collect();
    group.sort();
    group
}

pub fn compose(outer: &CellMap, inner: &CellMap) -> CellMap {
    let mut m = [0u8; CELLS];
    for c in 0..CELLS {
        m[c] = outer[inner[c] as usize];
    }
    m
}

fn invert(map: &CellMap) -> CellMap {
    let mut m = [0u8; CELLS];
    for c in 0..CELLS {
        m[map[c] as usize] = c as u8;
    }
    m
}

impl Geometry {
    pub fn new() -> Geometry {
        let lines = build_lines();
        assert_eq!(lines.len(), LINES, "line count");
        let mut line_through = vec![None; CELLS * CELLS];
        for (i, l) in lines.iter().enumerate() {
            for a in l.to_vec() {
                for b in l.to_vec() {
                    if a != b {
                        assert!(line_through[a * CELLS + b].is_none(), "two lines share two cells");
                        line_through[a * CELLS + b] = Some(i as u8);
                    }
                }
            }
        }
        let group = build_group(&lines);
        assert_eq!(group.len(), GROUP_SIZE, "|G|");
        let inverse = group.iter().map(invert).collect();
        let g = Geometry { lines, line_through, group, inverse };
        g.assert_closed();
        g
    }

    fn assert_closed(&self) {
        let members: HashSet<&CellMap> = self.group.iter().collect();
        for a in &self.group {
            for b in &self.group {
                assert!(members.contains(&compose(a, b)), "G is not closed under composition");
            }
        }
    }

    /// Index of the line through two cells, derived from the line table.
    pub fn line_through(&self, a: usize, b: usize) -> Option<usize> {
        if a >= CELLS || b >= CELLS {
            return None;
        }
        self.line_through[a * CELLS + b].map(|i| i as usize)
    }

    /// The orbit of a cell under G, as a set.
    pub fn orbit(&self, cell: usize) -> Set {
        self.group.iter().fold(Set::default(), |s, g| s.with(g[cell] as usize))
    }

    /// The least `(s(M), s(B))` over s in G (compared M first, then B), and
    /// the index of an `s` that attains it.
    pub fn canonical(&self, m: Set, b: Set) -> (Set, Set, usize) {
        let images: Vec<Set> = self.group.iter().map(|g| apply_map(g, m)).collect();
        let least_m = *images.iter().min().unwrap();
        let mut best: Option<(Set, usize)> = None;
        for (i, g) in self.group.iter().enumerate() {
            if images[i] != least_m {
                continue;
            }
            let bi = apply_map(g, b);
            if best.is_none_or(|(bb, _)| bi < bb) {
                best = Some((bi, i));
            }
        }
        let (bb, i) = best.unwrap();
        (least_m, bb, i)
    }

    /// Cells grouped into orbits, ordered by their least cell.
    #[cfg(test)]
    pub fn orbits(&self) -> Vec<Vec<usize>> {
        let mut out: Vec<Vec<usize>> = Vec::new();
        for c in 0..CELLS {
            if !out.iter().any(|o| o.contains(&c)) {
                out.push(self.orbit(c).to_vec());
            }
        }
        out
    }
}
