//! The leaf certificate: a set of disjoint "gadgets" on empty cells that gives
//! Breaker a cell in every live line, with Maker to move.
//!
//! Gadgets are blocks (small grids where Breaker provably wins the sub-game by
//! answering inside the grid) and pairs (two cells of one line: Breaker takes
//! whichever one Maker leaves). Breaker always answers inside the gadget Maker
//! just played in, so the gadgets' strategies never interfere. A block with
//! Maker marks inside is used only if its exact sub-game (subgame.rs) is still
//! a Breaker win from that position; Breaker marks inside a block only help.

use crate::bits::{Cells, Lines, CELLS};
use crate::data::Data;

/// How many templates to try with the exact matching before giving up.
const MATCH_TRIES: usize = 8;

/// One template seen from a fixed set of Maker marks.
pub struct View {
    pub template: usize,
    /// lines covered by the template's blocks that Maker hasn't touched
    pub cover: Lines,
    /// empty-of-Maker cells outside those blocks (Breaker marks still to remove)
    pub free: Cells,
    /// the Breaker marks block validity was judged with, so the exact block
    /// set can be rebuilt for the proof file (`view_blocks`)
    pub marks: Cells,
}

/// The template blocks a view uses: those that held with the view's marks.
pub fn view_blocks(data: &Data, v: &View, maker: &Cells) -> Vec<usize> {
    data.templates[v.template].iter().copied().filter(|&bi| block_holds(data, bi, maker, &v.marks)).collect()
}

/// True if the block still guarantees Breaker a cell in each of its lines,
/// given the marks already inside it (Maker to move). Lines already holding a
/// Breaker mark anywhere count as dead edges.
pub fn block_holds(data: &Data, bi: usize, maker: &Cells, breaker: &Cells) -> bool {
    let b = &data.blocks[bi];
    if !b.conditional && !b.cells.meets(maker) {
        return true; // empty of Maker: the sub-game was solved from scratch
    }
    if !data.use_subgames {
        return false;
    }
    let dead = b
        .edge_lines
        .iter()
        .enumerate()
        .fold(0u16, |d, (i, &li)| if data.line_mask[li].meets(breaker) { d | 1 << i } else { d });
    data.subgames.breaker_holds(b.shape, dead, b.local(maker), b.local(breaker))
}

/// `block_holds` at one position, each block solved at most once and only
/// when asked. A block sits in many templates (and their 48 images), and in a
/// 2026-11-19 profile of the search the repeated block checks and sub-game
/// lookups were over half the time. Solving every library block up front was
/// 2.6 times slower (most blocks are in no template).
pub struct HoldsAt<'a> {
    data: &'a Data,
    pub maker: Cells,
    pub breaker: Cells,
    memo: Vec<u8>,
}

const HOLDS_UNKNOWN: u8 = 2;

impl<'a> HoldsAt<'a> {
    pub fn new(data: &'a Data, maker: &Cells, breaker: &Cells) -> Self {
        HoldsAt { data, maker: *maker, breaker: *breaker, memo: vec![HOLDS_UNKNOWN; data.blocks.len()] }
    }

    pub fn get(&mut self, bi: usize) -> bool {
        if self.memo[bi] == HOLDS_UNKNOWN {
            self.memo[bi] = block_holds(self.data, bi, &self.maker, &self.breaker) as u8;
        }
        self.memo[bi] == 1
    }

    /// `block_holds` once Breaker also owns `c`. A mark changes a block's
    /// sub-game only if it lands in the block or on one of its edge lines
    /// (`block_holds` reads nothing else), so every other block keeps its
    /// answer from before the reply.
    pub fn get_after(&mut self, bi: usize, c: usize) -> bool {
        let b = &self.data.blocks[bi];
        if b.cells.has(c) || b.edge_lines.iter().any(|&li| self.data.line_mask[li].has(c)) {
            block_holds(self.data, bi, &self.maker, &self.breaker.with(c))
        } else {
            self.get(bi)
        }
    }
}

/// One view per template, with `holds` deciding which of its blocks count.
fn build_views(data: &Data, maker: &Cells, marks: &Cells, templates: impl Iterator<Item = usize>, mut holds: impl FnMut(usize) -> bool) -> Vec<View> {
    let open = Cells::all().minus(maker);
    templates
        .map(|ti| {
            let (mut cover, mut used) = (Lines::EMPTY, Cells::EMPTY);
            for &bi in &data.templates[ti] {
                if holds(bi) {
                    let b = &data.blocks[bi];
                    cover = cover.or(&b.lines);
                    used = used.or(&b.cells);
                }
            }
            View { template: ti, cover, free: open.minus(&used), marks: *marks }
        })
        .collect()
}

/// Views of every template for one position. Shared by all Breaker candidates
/// at a node: a candidate's own mark can only help a block, so validity
/// computed without it is safe.
pub fn views_at(h: &mut HoldsAt) -> Vec<View> {
    let (data, maker, breaker) = (h.data, h.maker, h.breaker);
    build_views(data, &maker, &breaker, 0..data.templates.len(), |bi| h.get(bi))
}

/// `views_at` for a one-off position.
pub fn views(data: &Data, maker: &Cells, breaker: &Cells) -> Vec<View> {
    views_at(&mut HoldsAt::new(data, maker, breaker))
}

/// Views of every template after Breaker's reply `c`, reusing the answers
/// from before the reply for blocks the reply doesn't touch.
pub fn views_after(h: &mut HoldsAt, c: usize) -> Vec<View> {
    let (data, maker, after) = (h.data, h.maker, h.breaker.with(c));
    build_views(data, &maker, &after, 0..data.templates.len(), |bi| h.get_after(bi, c))
}

/// Template blocks that don't hold before Breaker's reply: Maker has played in
/// them and their sub-game is lost. A reply can revive one by answering inside
/// it or by killing one of its lines. Returns them with every cell a reviving
/// reply could be on.
pub fn dead_blocks(h: &mut HoldsAt) -> (Vec<usize>, Cells) {
    let data = h.data;
    let mut dead = Vec::new();
    let mut reach = Cells::EMPTY;
    for (bi, b) in data.blocks.iter().enumerate() {
        // a conditional block can be dead with no Maker mark in it (its sub-game
        // is lost from scratch) and revived by a reply that kills one of its lines
        let untouched_ok = !b.conditional && !b.cells.meets(&h.maker);
        if data.templates_by_block[bi].is_empty() || untouched_ok || h.get(bi) {
            continue;
        }
        dead.push(bi);
        reach = reach.or(&b.cells);
        for li in b.lines.iter() {
            reach = reach.or(&data.line_mask[li]);
        }
    }
    (dead, reach)
}

/// Views recomputed after Breaker's reply `c`, for the templates holding a
/// block from `dead` that the reply revives. Views built before the reply
/// can't see those blocks.
pub fn reply_views(h: &mut HoldsAt, c: usize, dead: &[usize]) -> Vec<View> {
    let data = h.data;
    let mut affected: Vec<usize> = dead
        .iter()
        .filter(|&&bi| h.get_after(bi, c))
        .flat_map(|&bi| data.templates_by_block[bi].iter().copied())
        .collect();
    affected.sort_unstable();
    affected.dedup();
    let (maker, after) = (h.maker, h.breaker.with(c));
    build_views(data, &maker, &after, affected.into_iter(), |bi| h.get_after(bi, c))
}

/// Cells left over minus twice the lines that still need a pair: a necessary
/// condition for the pairing (must be >= 0) and a ranking score.
pub fn slack(view: &View, live: &Lines, breaker: &Cells) -> i32 {
    let need = live.minus(&view.cover).count() as i32;
    view.free.minus(breaker).count() as i32 - 2 * need
}

/// No slot owns the cell (in `match_lines`'s owner table).
const NO_SLOT: u16 = u16::MAX;

/// Maximum matching of two slots per line (slot `s` belongs to `lines[s / 2]`)
/// onto distinct cells of `free` on that line: a greedy first pass, then
/// Kuhn's augmenting paths for the slots it left. Returns each cell's slot
/// (or `NO_SLOT`) and the unmatched slots in increasing order; with
/// `stop_on_fail` it returns at the first unmatched slot. Shared by the
/// pairing (`pair_lines`) and the repair stage's deficit, which were 15% of
/// leaf-check time in a 2026-11-19 profile as two copies that rebuilt
/// adjacency lists and cleared a visited array per slot.
pub fn match_lines(data: &Data, lines: &[usize], free: &Cells, stop_on_fail: bool) -> ([u16; CELLS], Vec<usize>) {
    let mut owner = [NO_SLOT; CELLS];
    let mut pending = Vec::new();
    for s in 0..lines.len() * 2 {
        match data.line_cells[lines[s / 2]].iter().find(|&&c| free.has(c) && owner[c] == NO_SLOT) {
            Some(&c) => owner[c] = s as u16,
            None => pending.push(s),
        }
    }
    // stamp[c] == round marks c visited in this round's search, so the
    // visited set never needs clearing
    struct Ctx<'a> {
        data: &'a Data,
        lines: &'a [usize],
        free: &'a Cells,
        owner: [u16; CELLS],
        stamp: [u32; CELLS],
        round: u32,
    }
    fn grow(x: &mut Ctx, s: usize) -> bool {
        for &c in &x.data.line_cells[x.lines[s / 2]] {
            if !x.free.has(c) || x.stamp[c] == x.round {
                continue;
            }
            x.stamp[c] = x.round;
            if x.owner[c] == NO_SLOT || grow(x, x.owner[c] as usize) {
                x.owner[c] = s as u16;
                return true;
            }
        }
        false
    }
    let mut x = Ctx { data, lines, free, owner, stamp: [0; CELLS], round: 0 };
    let mut unmatched = Vec::new();
    for s in pending {
        x.round += 1;
        if !grow(&mut x, s) {
            unmatched.push(s);
            if stop_on_fail {
                break;
            }
        }
    }
    (x.owner, unmatched)
}

/// Gives each line in `need` two cells from `free`, no cell used twice.
/// Returns the pairs, or None.
pub fn pair_lines(data: &Data, need: &Lines, free: &Cells) -> Option<Vec<(usize, usize, usize)>> {
    let lines: Vec<usize> = need.iter().collect();
    if lines.len() as u32 * 2 > free.count() {
        return None;
    }
    if lines.iter().any(|&li| data.line_mask[li].and(free).count() < 2) {
        return None;
    }
    let (owner, unmatched) = match_lines(data, &lines, free, true);
    if !unmatched.is_empty() {
        return None;
    }
    let mut got = vec![Vec::new(); lines.len()];
    for c in 0..CELLS {
        if owner[c] != NO_SLOT {
            got[owner[c] as usize / 2].push(c);
        }
    }
    Some(lines.iter().zip(got).map(|(&li, g)| (li, g[0], g[1])).collect())
}

/// A found certificate: the disjoint library blocks it uses and the pairs
/// (line, cell, cell) for the live lines no block covers.
#[derive(Clone)]
pub struct Cert {
    pub blocks: Vec<usize>,
    pub pairs: Vec<(usize, usize, usize)>,
}

/// Looks for a certificate at a position with Maker to move.
/// `deep` adds the slow local-search stage (repair.rs) after the fast ones.
/// `extra` holds views recomputed for this reply (`reply_views`), tried beside `views`.
pub fn certify(data: &Data, views: &[View], extra: &[View], maker: &Cells, breaker: &Cells, deep: bool) -> Option<Cert> {
    let views: Vec<&View> = views.iter().chain(extra).collect();
    let live = data.live_lines(breaker);
    let empty = Cells::all().minus(maker).minus(breaker);
    // a live line with fewer than two empty cells can't get a pair or a block
    for li in live.iter() {
        if data.line_mask[li].and(&empty).count() < 2 {
            return None;
        }
    }
    let mut ranked: Vec<(i32, usize)> = views
        .iter()
        .enumerate()
        .map(|(i, v)| (slack(v, &live, breaker), i))
        .filter(|&(s, _)| s >= 0)
        .collect();
    ranked.sort_unstable_by(|a, b| b.cmp(a));
    // slack ranks templates poorly once a matching is near-tight, so the deep
    // check runs the matching on every template with slack
    let tries = if deep { ranked.len() } else { MATCH_TRIES };
    for &(_, i) in ranked.iter().take(tries) {
        let v = views[i];
        let need = live.minus(&v.cover);
        if let Some(pairs) = pair_lines(data, &need, &v.free.minus(breaker)) {
            return Some(Cert { blocks: view_blocks(data, v, maker), pairs });
        }
    }
    // second chance: add library blocks on cells the best templates left over
    for &(_, i) in ranked.iter().take(AUGMENT_TRIES) {
        if let Some(c) = augment(data, views[i], &live, maker, breaker) {
            return Some(c);
        }
    }
    // third chance: local search on block choices from the best templates
    if deep && data.use_repair {
        for &(_, i) in ranked.iter().take(REPAIR_TRIES) {
            let t = views[i].template;
            let start = data.templates[t].iter().copied().filter(|&bi| block_holds(data, bi, maker, breaker)).collect();
            if let Some(c) = crate::repair::repair(data, start, maker, breaker) {
                return Some(c);
            }
        }
    }
    None
}

/// A certificate from a given block list, such as a CP-SAT layout from
/// gen/harvest.py: the blocks must be library blocks, pairwise disjoint, and
/// hold at this position (Maker to move); the pairs come from the matching.
pub fn cert_from_blocks(data: &Data, blocks: &[usize], maker: &Cells, breaker: &Cells) -> Option<Cert> {
    let live = data.live_lines(breaker);
    let (mut cover, mut used) = (Lines::EMPTY, Cells::EMPTY);
    for &bi in blocks {
        let b = data.blocks.get(bi)?;
        if b.cells.meets(&used) || !block_holds(data, bi, maker, breaker) {
            return None;
        }
        cover = cover.or(&b.lines);
        used = used.or(&b.cells);
    }
    let free = Cells::all().minus(maker).minus(&used).minus(breaker);
    let pairs = pair_lines(data, &live.minus(&cover), &free)?;
    Some(Cert { blocks: blocks.to_vec(), pairs })
}

/// Templates to try extra blocks on after plain matching fails.
const AUGMENT_TRIES: usize = 3;
/// Templates to start the local-search repair from.
const REPAIR_TRIES: usize = 3;

/// Greedily adds blocks that sit entirely on the template's leftover cells (no
/// Maker mark), picking the one that saves the most pairing cells each time,
/// then retries the pairing.
fn augment(data: &Data, v: &View, live: &Lines, maker: &Cells, breaker: &Cells) -> Option<Cert> {
    let mut need = live.minus(&v.cover);
    // leftover cells, Breaker marks included: a block may contain them
    let mut room = v.free;
    let mut extra = Vec::new();
    loop {
        let mut best: Option<(i32, usize)> = None;
        for (bi, b) in data.blocks.iter().enumerate() {
            if b.cells.minus(&room).count() != 0 || !block_holds(data, bi, maker, breaker) {
                continue;
            }
            let covers = b.lines.and(&need).count() as i32;
            // each covered line saves two cells; the block uses its empty cells
            let gain = 2 * covers - b.cells.minus(breaker).count() as i32;
            if gain > 0 && best.map_or(true, |(g, _)| gain > g) {
                best = Some((gain, bi));
            }
        }
        let Some((_, bi)) = best else { break };
        let b = &data.blocks[bi];
        need = need.minus(&b.lines);
        room = room.minus(&b.cells);
        extra.push(bi);
    }
    if extra.is_empty() {
        return None;
    }
    let mut blocks = view_blocks(data, v, maker);
    blocks.extend(extra);
    pair_lines(data, &need, &room.minus(breaker)).map(|pairs| Cert { blocks, pairs })
}
