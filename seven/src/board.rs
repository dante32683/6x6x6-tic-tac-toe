//! The 7x7x7 board: cells, the 193 winning lines, and the 48 cube symmetries.
//!
//! Cells are `(x, y, z)` with coordinates 0..=6 and id `49x + 7y + z`. The
//! paper (arXiv:2509.21494) writes cells as three digits 1..=7, so its
//! `(4,4,4)` center is our `(3,3,3)`; `paper_cell` converts.

pub const SIDE: usize = 7;
pub const CELLS: usize = SIDE * SIDE * SIDE;
/// ((n+2)^3 - n^3) / 2 lines for n = 7 (Golomb and Hales).
pub const LINE_COUNT: usize = 193;

pub fn cell(x: usize, y: usize, z: usize) -> usize {
    SIDE * SIDE * x + SIDE * y + z
}

pub fn coords(c: usize) -> [usize; 3] {
    [c / (SIDE * SIDE), (c / SIDE) % SIDE, c % SIDE]
}

/// A cell in the paper's notation: three digits 1..=7, e.g. 444 is the center.
pub fn paper_cell(abc: usize) -> usize {
    let (a, b, c) = (abc / 100, (abc / 10) % 10, abc % 10);
    assert!((1..=7).contains(&a) && (1..=7).contains(&b) && (1..=7).contains(&c), "bad paper cell {abc}");
    cell(a - 1, b - 1, c - 1)
}

/// The inverse of `paper_cell`, for printing.
pub fn paper_name(c: usize) -> usize {
    let [x, y, z] = coords(c);
    100 * (x + 1) + 10 * (y + 1) + (z + 1)
}

pub const CENTER: usize = 3 * 49 + 3 * 7 + 3;

#[derive(Clone, Copy, PartialEq, Eq, Debug)]
pub enum Kind {
    Axis,
    FaceDiagonal,
    SpaceDiagonal,
}

pub struct Board {
    pub lines: Vec<[usize; SIDE]>,
    pub kind: Vec<Kind>,
    /// Lines through each cell.
    pub through: Vec<Vec<usize>>,
}

impl Board {
    pub fn new() -> Board {
        let mut lines = Vec::new();
        let mut kind = Vec::new();
        // One direction per line pair: the first nonzero component is +1.
        for dx in -1i32..=1 {
            for dy in -1i32..=1 {
                for dz in -1i32..=1 {
                    let d = [dx, dy, dz];
                    let first = d.iter().find(|&&v| v != 0);
                    if first != Some(&1) {
                        continue;
                    }
                    let moving = d.iter().filter(|&&v| v != 0).count();
                    // Start: coordinate 0 if it increases, 6 if it decreases, free if fixed.
                    let ranges: Vec<Vec<i32>> = d
                        .iter()
                        .map(|&v| match v {
                            1 => vec![0],
                            -1 => vec![SIDE as i32 - 1],
                            _ => (0..SIDE as i32).collect(),
                        })
                        .collect();
                    for &sx in &ranges[0] {
                        for &sy in &ranges[1] {
                            for &sz in &ranges[2] {
                                let mut l = [0usize; SIDE];
                                for (k, slot) in l.iter_mut().enumerate() {
                                    let k = k as i32;
                                    *slot = cell((sx + k * dx) as usize, (sy + k * dy) as usize, (sz + k * dz) as usize);
                                }
                                lines.push(l);
                                kind.push(match moving {
                                    1 => Kind::Axis,
                                    2 => Kind::FaceDiagonal,
                                    _ => Kind::SpaceDiagonal,
                                });
                            }
                        }
                    }
                }
            }
        }
        assert_eq!(lines.len(), LINE_COUNT);
        let mut through = vec![Vec::new(); CELLS];
        for (i, l) in lines.iter().enumerate() {
            for &c in l {
                through[c].push(i);
            }
        }
        assert_eq!(through[CENTER].len(), 13, "the center lies on 13 lines");
        Board { lines, kind, through }
    }
}

/// The 48 symmetries of the cube as maps on cells (signed coordinate permutations about the center).
pub fn symmetries() -> Vec<Vec<usize>> {
    let perms = [[0, 1, 2], [0, 2, 1], [1, 0, 2], [1, 2, 0], [2, 0, 1], [2, 1, 0]];
    let mut out = Vec::new();
    for p in perms {
        for flips in 0..8 {
            let map: Vec<usize> = (0..CELLS)
                .map(|c| {
                    let v = coords(c);
                    let mut w = [0usize; 3];
                    for i in 0..3 {
                        let t = v[p[i]];
                        w[i] = if flips >> i & 1 == 1 { SIDE - 1 - t } else { t };
                    }
                    cell(w[0], w[1], w[2])
                })
                .collect();
            out.push(map);
        }
    }
    out
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn lines_and_degrees() {
        let b = Board::new();
        let axis = b.kind.iter().filter(|&&k| k == Kind::Axis).count();
        let face = b.kind.iter().filter(|&&k| k == Kind::FaceDiagonal).count();
        assert_eq!((axis, face, LINE_COUNT - axis - face), (147, 42, 4));
        // The paper (section 4.2): only the center has degree above 7, and the
        // other space-diagonal cells have degree 7.
        for c in 0..CELLS {
            let [x, y, z] = coords(c);
            let on_diag = (x == y || x + y == 6) && (y == z || y + z == 6) && (x == z || x + z == 6);
            let d = b.through[c].len();
            if c == CENTER {
                assert_eq!(d, 13);
            } else if on_diag {
                assert_eq!(d, 7, "cell {}", paper_name(c));
            } else {
                assert!(d < 7);
            }
        }
    }

    /// The paper's opening kills 27 lines with four cells off the center; no
    /// four cells kill more. Only the 24 other space-diagonal cells lie on 7
    /// lines (every other cell on at most 5), so a set with any other cell
    /// kills at most 3 * 7 + 5 = 26, and four diagonal cells are checked here.
    #[test]
    fn four_cells_off_the_center_kill_at_most_27_lines() {
        let b = Board::new();
        let deg7: Vec<usize> = (0..CELLS).filter(|&c| c != CENTER && b.through[c].len() == 7).collect();
        assert_eq!(deg7.len(), 24);
        assert!((0..CELLS).all(|c| c == CENTER || deg7.contains(&c) || b.through[c].len() <= 5));
        let mut best = 0;
        for i in 0..24 {
            for j in i + 1..24 {
                for k in j + 1..24 {
                    for l in k + 1..24 {
                        let mut hit = vec![false; LINE_COUNT];
                        for &c in &[deg7[i], deg7[j], deg7[k], deg7[l]] {
                            for &line in &b.through[c] {
                                hit[line] = true;
                            }
                        }
                        best = best.max(hit.iter().filter(|&&h| h).count());
                    }
                }
            }
        }
        assert_eq!(best, 27);
        // The paper's own four marks (center opening, usual case) reach it.
        let mut hit = vec![false; LINE_COUNT];
        for c in [555, 626, 117, 177].map(paper_cell) {
            for &line in &b.through[c] {
                hit[line] = true;
            }
        }
        assert_eq!(hit.iter().filter(|&&h| h).count(), 27);
    }

    #[test]
    fn symmetries_preserve_lines() {
        let b = Board::new();
        let mut set: Vec<Vec<usize>> = b.lines.iter().map(|l| { let mut v = l.to_vec(); v.sort(); v }).collect();
        set.sort();
        for g in symmetries() {
            let mut img: Vec<Vec<usize>> = b.lines.iter().map(|l| { let mut v: Vec<usize> = l.iter().map(|&c| g[c]).collect(); v.sort(); v }).collect();
            img.sort();
            assert_eq!(img, set);
        }
    }
}
