//! Fixed-size bit sets for the cells and lines of the n x n x n cube, and the
//! board size itself.

/// Side length: 6 by default, 5 when built with `--features n5`
/// Everything else derives from it.
#[cfg(not(feature = "n5"))]
pub const SIDE: usize = 6;
#[cfg(feature = "n5")]
pub const SIDE: usize = 5;
pub const CELLS: usize = SIDE * SIDE * SIDE;
/// Lines of the n^3 board: ((n+2)^3 - n^3) / 2, 148 for n = 6 and 109 for n = 5.
pub const LINES: usize = ((SIDE + 2).pow(3) - CELLS) / 2;
const CELL_WORDS: usize = CELLS.div_ceil(64);
const LINE_WORDS: usize = LINES.div_ceil(64);
/// The data file gen/gen.py writes for this size.
pub const DATA_FILE: &str = if SIDE == 6 { "data6.json" } else { "data5.json" };

/// A set of cells (bit i = cell i).
#[derive(Clone, Copy, PartialEq, Eq, Hash, PartialOrd, Ord, Default, Debug)]
pub struct Cells(pub [u64; CELL_WORDS]);

/// A set of lines (bit i = line i).
#[derive(Clone, Copy, PartialEq, Eq, Default, Debug)]
pub struct Lines(pub [u64; LINE_WORDS]);

macro_rules! set_ops {
    ($t:ident, $n:expr) => {
        impl $t {
            pub const EMPTY: $t = $t([0; $n]);
            pub fn has(&self, i: usize) -> bool {
                self.0[i / 64] >> (i % 64) & 1 == 1
            }
            pub fn insert(&mut self, i: usize) {
                self.0[i / 64] |= 1 << (i % 64);
            }
            pub fn with(mut self, i: usize) -> $t {
                self.insert(i);
                self
            }
            pub fn count(&self) -> u32 {
                self.0.iter().map(|w| w.count_ones()).sum()
            }
            pub fn is_empty(&self) -> bool {
                self.0.iter().all(|&w| w == 0)
            }
            pub fn and(&self, o: &$t) -> $t {
                let mut r = *self;
                for k in 0..$n {
                    r.0[k] &= o.0[k];
                }
                r
            }
            pub fn or(&self, o: &$t) -> $t {
                let mut r = *self;
                for k in 0..$n {
                    r.0[k] |= o.0[k];
                }
                r
            }
            pub fn minus(&self, o: &$t) -> $t {
                let mut r = *self;
                for k in 0..$n {
                    r.0[k] &= !o.0[k];
                }
                r
            }
            pub fn meets(&self, o: &$t) -> bool {
                (0..$n).any(|k| self.0[k] & o.0[k] != 0)
            }
            pub fn iter(&self) -> impl Iterator<Item = usize> + '_ {
                (0..$n).flat_map(move |k| {
                    let mut w = self.0[k];
                    std::iter::from_fn(move || {
                        if w == 0 {
                            return None;
                        }
                        let b = w.trailing_zeros() as usize;
                        w &= w - 1;
                        Some(k * 64 + b)
                    })
                })
            }
        }
    };
}
set_ops!(Cells, CELL_WORDS);
set_ops!(Lines, LINE_WORDS);

impl Cells {
    pub fn all() -> Cells {
        let mut c = Cells::EMPTY;
        for i in 0..CELLS {
            c.insert(i);
        }
        c
    }
}
