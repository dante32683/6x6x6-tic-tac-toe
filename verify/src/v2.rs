//! Reading the catalogue format v2 (docs/proof-format.md, "Catalogue format
//! (v2)") into the same records a v1 file parses to. Nothing here is trusted:
//! the records go through the same checks as v1 records, so a bad v2 file can
//! only fail. The pairs are rebuilt by the same matching rule as
//! gen/compact_v2.py's reference decoder.

use crate::cert::{Block, Cert};
use crate::geometry::{CellMap, Geometry, Set, CELLS};
use crate::parse::Record;

pub const MAGIC: &[u8] = b"C6PROOF2";

struct Reader<'a> {
    data: &'a [u8],
    at: usize,
}

impl<'a> Reader<'a> {
    fn take(&mut self, n: usize) -> Result<&'a [u8], String> {
        let end = self.at.checked_add(n).filter(|&e| e <= self.data.len()).ok_or("v2 file ends early")?;
        let out = &self.data[self.at..end];
        self.at = end;
        Ok(out)
    }
    fn u8(&mut self) -> Result<usize, String> {
        Ok(self.take(1)?[0] as usize)
    }
    fn u32(&mut self) -> Result<usize, String> {
        Ok(u32::from_le_bytes(self.take(4)?.try_into().unwrap()) as usize)
    }
    fn cell(&mut self) -> Result<usize, String> {
        let c = self.u8()?;
        if c >= CELLS {
            return Err(format!("cell id {c} is out of range"));
        }
        Ok(c)
    }
    /// A `u8` count and that many cells, strictly increasing.
    fn set(&mut self) -> Result<Vec<usize>, String> {
        let n = self.u8()?;
        let cells = (0..n).map(|_| self.cell()).collect::<Result<Vec<_>, _>>()?;
        if cells.windows(2).any(|w| w[0] >= w[1]) {
            return Err("cell set is not strictly increasing".into());
        }
        Ok(cells)
    }
    /// `n` little-endian unsigned integers of `width` bytes.
    fn column(&mut self, n: usize, width: usize) -> Result<Vec<usize>, String> {
        let bytes = self.take(n.checked_mul(width).ok_or("column too large")?)?;
        Ok(bytes.chunks(width).map(|c| c.iter().rev().fold(0usize, |v, &b| v << 8 | b as usize)).collect())
    }
}

type Layout = Vec<(Vec<usize>, Vec<(usize, usize)>)>;

/// The records of a v2 file, in the order the reference decoder writes them.
pub fn records(data: &[u8], geo: &Geometry) -> Result<Vec<Record>, String> {
    let mut rd = Reader { data, at: 0 };
    if rd.take(MAGIC.len())? != MAGIC {
        return Err("not a v2 file".into());
    }
    let (text_len, n_layouts, n_r, n_leaves, id_width) = (rd.u32()?, rd.u32()?, rd.u32()?, rd.u32()?, rd.u8()?);
    if id_width != 2 && id_width != 4 {
        return Err(format!("layout id width {id_width} (must be 2 or 4)"));
    }
    rd.take(text_len)?; // the v1 header comments
    let mut layouts: Vec<Layout> = Vec::with_capacity(n_layouts.min(1 << 20));
    for _ in 0..n_layouts {
        let n_blocks = rd.u8()?;
        let mut layout = Vec::with_capacity(n_blocks);
        for _ in 0..n_blocks {
            let cells = rd.set()?;
            let claims = (0..rd.u8()?).map(|_| Ok((rd.cell()?, rd.cell()?))).collect::<Result<Vec<_>, String>>()?;
            layout.push((cells, claims));
        }
        layouts.push(layout);
    }
    let mut rrec = Vec::with_capacity(n_r.min(1 << 20));
    for _ in 0..n_r {
        let (m, b, reply) = (Set::from_cells(&rd.set()?), Set::from_cells(&rd.set()?), rd.cell()?);
        if !m.inter(b).is_empty() || m.len() != b.len() + 1 || m.union(b).has(reply) {
            return Err(format!("R record M={} B={} r={reply}: needs disjoint M and B, |M| = |B| + 1, and an empty reply", m.show(), b.show()));
        }
        rrec.push(Record { m, b, reply, cert: None });
    }
    let counts = rd.column(n_r, 1)?;
    let moves = rd.column(n_leaves, 1)?;
    let replies = rd.column(n_leaves, 1)?;
    let ids = rd.column(n_leaves, id_width)?;
    let syms = rd.column(n_leaves, 2)?;
    if rd.at != data.len() || counts.iter().sum::<usize>() != n_leaves {
        return Err("v2 sizes do not add up".into());
    }
    let mut group: Vec<CellMap> = geo.group.clone();
    group.sort_unstable(); // the spec's map order: images in lexicographic order
    let mut line_order: Vec<usize> = (0..geo.lines.len()).collect();
    line_order.sort_by_key(|&i| geo.lines[i].to_vec());

    let mut out = rrec.clone();
    let mut k = 0;
    for (parent, &count) in rrec.iter().zip(&counts) {
        let b = parent.b.with(parent.reply);
        for _ in 0..count {
            let (mv, reply) = (moves[k], replies[k]);
            let layout = layouts.get(ids[k]).ok_or(format!("leaf {k}: layout id {} out of range", ids[k]))?;
            let g = group.get(syms[k]).ok_or(format!("leaf {k}: symmetry index {} out of range", syms[k]))?;
            let f = |c: usize| g[c] as usize;
            let mut blocks: Vec<(Vec<usize>, Vec<(usize, usize)>)> = layout
                .iter()
                .map(|(cells, claims)| {
                    let mut cs: Vec<usize> = cells.iter().map(|&c| f(c)).collect();
                    cs.sort_unstable();
                    (cs, claims.iter().map(|&(a, c)| (f(a).min(f(c)), f(a).max(f(c)))).collect())
                })
                .collect();
            blocks.sort();
            let m2 = parent.m.with(mv);
            if parent.m.union(b).has(mv) || m2.union(b).has(reply) {
                return Err(format!("leaf {k}: move {mv} or reply {reply} is not empty"));
            }
            let blocks: Vec<Block> = blocks.into_iter().map(|(cs, lines)| Block { cells: Set::from_cells(&cs), lines }).collect();
            let pairs = pairs_for(geo, &line_order, m2, b.with(reply), &blocks).ok_or(format!("leaf {k}: no pairing for M={} B={}", m2.show(), b.show()))?;
            out.push(Record { m: m2, b, reply, cert: Some(Cert { blocks, pairs }) });
            k += 1;
        }
    }
    Ok(out)
}

/// Pairs covering every live line no block claims, with empty cells outside
/// every block: Kuhn's augmenting paths, two slots per line, lines in the
/// spec's line order, each line's cells in increasing order.
fn pairs_for(geo: &Geometry, line_order: &[usize], m: Set, b: Set, blocks: &[Block]) -> Option<Vec<(usize, usize)>> {
    let used = blocks.iter().fold(m.union(b), |u, bl| u.union(bl.cells));
    let claimed: Vec<usize> = blocks.iter().flat_map(|bl| bl.lines.iter().filter_map(|&(a, c)| geo.line_through(a, c))).collect();
    let need: Vec<usize> = line_order.iter().copied().filter(|&l| geo.lines[l].inter(b).is_empty() && !claimed.contains(&l)).collect();
    let cand: Vec<Vec<usize>> = need.iter().map(|&l| geo.lines[l].minus(used).to_vec()).collect();
    let slots = 2 * need.len();
    let mut owner: [Option<usize>; CELLS] = [None; CELLS]; // cell -> slot

    fn augment(s: usize, cand: &[Vec<usize>], owner: &mut [Option<usize>; CELLS], seen: &mut [bool; CELLS]) -> bool {
        for &c in &cand[s / 2] {
            if seen[c] {
                continue;
            }
            seen[c] = true;
            if owner[c].is_none_or(|o| augment(o, cand, owner, seen)) {
                owner[c] = Some(s);
                return true;
            }
        }
        false
    }

    for s in 0..slots {
        if !augment(s, &cand, &mut owner, &mut [false; CELLS]) {
            return None;
        }
    }
    let mut by_slot: Vec<(usize, usize)> = (0..CELLS).filter_map(|c| owner[c].map(|s| (s, c))).collect();
    by_slot.sort_unstable();
    let mut pairs: Vec<(usize, usize)> = by_slot.chunks(2).map(|p| (p[0].1.min(p[1].1), p[0].1.max(p[1].1))).collect();
    pairs.sort_unstable();
    Some(pairs)
}
