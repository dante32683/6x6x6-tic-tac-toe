//! Strict check that Breaker can play the rule itself, in a frame the rule
//! defines, and still be covered by the proof (docs/rule.md, "Strict replay").
//!
//! `cube6 rules` compares each R record's reply with the rule's in the
//! record's own orientation, which is wherever the search happened to meet
//! the position. Here the rule is a standalone strategy instead:
//!
//! - Every rule feature is a geometric quantity (diagonals, layers,
//!   distances), so the rule's key for a cell is the same in all 48
//!   orientations of the cube. The other relabelings in the full group
//!   permute the three layer pairs, and the lowest-cell-id tiebreak depends
//!   on the labelling too, so the strategy needs a stated frame (`Frame`).
//!   The claim in docs/rule.md uses `Frame::Search`, which is how the
//!   search played: Maker's first move is cell 0, 2, or 8. After each later
//!   Maker move c from (M, B), take the lowest-id empty cell c' with
//!   (M + c', B) equivalent to (M + c, B) under the full group, and relabel
//!   the whole board by a map carrying (M + c, B) onto (M + c', B). The map
//!   may move Maker's earlier marks too: from M = {8}, B = {129} the moves
//!   103 and 156 both become 53, and the only map for 103 sends 103 to 8
//!   and 8 to 53. Every such map gives the same labelled board, so the
//!   frame is well defined; it is not "rename the move and keep the rest".
//! - Starting from the empty board it tries every Maker move the frame
//!   allows, answers each with the rule's reply where the proof has an R
//!   record for the position's class, and carries the result forward. A
//!   class can have both R and L records (a few hundred do); this plays the
//!   rule there. Playing the L record there instead is covered as well,
//!   since the checkers verify every record of a class they reach.
//!
//! `REPLAY OK` reads only R records and says nothing about leaves: that
//! each leaf exists and its certificate holds comes from `PROOF OK` by
//! `verify full` (or a Python checker with `--all-records`) on the same
//! file. The strategy claim needs both.
//!
//! A reply counts when the position after it is, under the proof's full
//! group, the position after one of the class's records' own replies. That
//! is what a winning strategy needs, given `verify/`, which checks every
//! record of each class it reaches: the verifier checked every Maker move
//! from that position. A Breaker-to-move position with no R record is a
//! leaf, which the verifier checked with its certificate (L record). The
//! Python checkers follow only the first record per class unless run with
//! `--all-records`; in the search frame the rule's reply depends on move
//! order, so some classes need two R records.
//!
//! It also counts, among the counted replies, those that are a matched
//! record's cell under a symmetry carrying the position onto the record
//! ("same cell"; only the first matching record is tried), and those where
//! every cell tied on the rule's key gives the same class ("tiebreak free").

use crate::bits::Cells;
use crate::data::Data;
use crate::rule::Rule;
use rayon::prelude::*;
use std::collections::{HashMap, HashSet};
use std::io::{BufRead, Write};

/// The orientation Breaker reads a position in before applying the rule.
#[derive(Clone, Copy, Debug)]
pub enum Frame {
    /// Least orientation under the 48 geometric maps (`Data::canonical_geometric`).
    Geometric,
    /// Least orientation under the proof's full group of 1,152 maps
    /// (`Data::canonical`), which also swaps the mid and core layers.
    Full,
    /// The search's own frame: Maker's first move is cell 0, 2, or 8 (one per
    /// opening class) and the labelling never changes after it. Every later
    /// Maker move is tried as itself, with no symmetry merging, so the result
    /// also covers every relabelling that keeps the first move in place.
    Fixed,
    /// The search's path: as `Fixed`, but after each Maker move the board is
    /// relabelled so that move is the lowest-id cell giving an equivalent
    /// position under the full group (the relabelling may move earlier
    /// marks; module comment), which is the one move per class
    /// `Search::maker_node` tries.
    Search,
}

impl Frame {
    pub fn parse(s: &str) -> Option<Frame> {
        match s {
            "geometric" => Some(Frame::Geometric),
            "full" => Some(Frame::Full),
            "fixed" => Some(Frame::Fixed),
            "search" => Some(Frame::Search),
            _ => None,
        }
    }

    fn orient(self, d: &Data, m: &Cells, b: &Cells) -> (Cells, Cells) {
        match self {
            Frame::Geometric => d.canonical_geometric(m, b),
            Frame::Full => d.canonical(m, b),
            Frame::Fixed | Frame::Search => (*m, *b),
        }
    }

    /// Maker's moves from a Maker-to-move position (the fixed frame opens
    /// only at the proof's three first moves).
    fn moves(self, d: &Data, m: &Cells, b: &Cells) -> Vec<usize> {
        match self {
            Frame::Fixed | Frame::Search if m.count() == 0 => FIXED_FIRST_MOVES.to_vec(),
            Frame::Search => {
                let mut seen = HashSet::new();
                Cells::all().minus(m).minus(b).iter().filter(|&c| seen.insert(d.canonical(&m.with(c), b))).collect()
            }
            _ => Cells::all().minus(m).minus(b).iter().collect(),
        }
    }
}

/// The proof's first moves, one per opening class under the full group
/// (docs/strategy.md).
#[cfg(not(feature = "n5"))]
const FIXED_FIRST_MOVES: [usize; 3] = [0, 2, 8];
#[cfg(feature = "n5")]
const FIXED_FIRST_MOVES: [usize; 0] = [];

/// One R record, as read: Maker's and Breaker's marks and the reply.
struct Record {
    maker: Cells,
    breaker: Cells,
    reply: usize,
}

/// Per Maker depth: positions met, R positions, rule replies counted, same
/// cell, tiebreak free, failures.
#[derive(Default, Clone, Copy)]
struct Tally {
    met: u64,
    r: u64,
    ok: u64,
    same_cell: u64,
    tie_free: u64,
    fail: u64,
}

fn parse_cells(s: &str) -> Cells {
    if s == "-" {
        Cells::EMPTY
    } else {
        s.split(',').fold(Cells::EMPTY, |a, t| a.with(t.parse().expect("cell id")))
    }
}

fn fmt(s: &Cells) -> String {
    let v: Vec<String> = s.iter().map(|c| c.to_string()).collect();
    if v.is_empty() { "-".into() } else { v.join(",") }
}

/// The R records of a proof file, keyed by canonical form under the full group.
fn read_records(d: &Data, path: &str) -> HashMap<(Cells, Cells), Vec<Record>> {
    let file = std::fs::File::open(path).unwrap_or_else(|e| panic!("{path}: {e}"));
    let recs: Vec<Record> = std::io::BufReader::with_capacity(1 << 20, file)
        .lines()
        .map(|l| l.unwrap_or_else(|e| panic!("{path}: {e}")))
        .filter(|l| l.starts_with("R |"))
        .map(|l| {
            let p: Vec<&str> = l.split(" | ").collect();
            Record { maker: parse_cells(p[1]), breaker: parse_cells(p[2]), reply: p[3].parse().expect("reply") }
        })
        .collect();
    let mut index: HashMap<(Cells, Cells), Vec<Record>> = HashMap::new();
    for r in recs {
        index.entry(d.canonical(&r.maker, &r.breaker)).or_default().push(r);
    }
    index
}

/// Runs the replay over `proof`; returns 0 when every rule reply counts.
pub fn run(d: &Data, rule: &Rule, proof: &str, frame: Frame) -> i32 {
    if matches!(frame, Frame::Fixed | Frame::Search) && FIXED_FIRST_MOVES.is_empty() {
        eprintln!("FRAME {frame:?} needs the board's first-move representatives, which only 6x6x6 has");
        return 2;
    }
    let t0 = std::time::Instant::now();
    let index = read_records(d, proof);
    let n_rec: usize = index.values().map(|v| v.len()).sum();
    eprintln!("{n_rec} R records in {} classes ({:.0} s)", index.len(), t0.elapsed().as_secs_f64());
    let mut exc = std::env::var("EXCEPTIONS").ok().map(|p| std::io::BufWriter::new(std::fs::File::create(&p).unwrap_or_else(|e| panic!("{p}: {e}"))));

    // Maker-to-move positions under rule play, as the frame labels them
    let mut frontier: Vec<(Cells, Cells)> = vec![(Cells::EMPTY, Cells::EMPTY)];
    let mut tallies: Vec<(u32, Tally)> = Vec::new();
    let mut failed = 0u64;
    while !frontier.is_empty() {
        let depth = frontier[0].0.count() + 1;
        // Breaker-to-move positions after each Maker move, in the frame's labelling
        let met: HashSet<(Cells, Cells)> = frontier
            .par_iter()
            .flat_map_iter(|(m, b)| {
                frame.moves(d, m, b).into_iter().map(|c| frame.orient(d, &m.with(c), b)).collect::<Vec<_>>()
            })
            .collect();
        let results: Vec<(Tally, Option<(Cells, Cells)>, Option<String>)> = met
            .par_iter()
            .map(|(m, b)| {
                let mut t = Tally { met: 1, ..Tally::default() };
                let Some(recs) = index.get(&d.canonical(m, b)) else { return (t, None, None) };
                t.r = 1;
                let top = rule.top(d, m, b);
                let x = top[0];
                let after = |c: usize| d.canonical(m, &b.with(c));
                let got = after(x);
                let hit = recs.iter().find(|r| d.canonical(&r.maker, &r.breaker.with(r.reply)) == got);
                let Some(r) = hit else {
                    t.fail = 1;
                    let line = format!("FAIL | {} | {} | rule {} | record {} | {} | {}", fmt(m), fmt(b), x, fmt(&recs[0].maker), fmt(&recs[0].breaker), recs[0].reply);
                    return (t, None, Some(line));
                };
                t.ok = 1;
                let map = |g: &[u8; crate::bits::CELLS], s: &Cells| s.iter().fold(Cells::EMPTY, |a, c| a.with(g[c] as usize));
                t.same_cell = d.full.iter().any(|g| g[x] as usize == r.reply && map(g, m) == r.maker && map(g, b) == r.breaker) as u64;
                t.tie_free = top.iter().all(|&c| after(c) == got) as u64;
                (t, Some((*m, b.with(x))), None)
            })
            .collect();
        let mut sum = Tally::default();
        let mut next = Vec::new();
        for (t, n, line) in results {
            sum.met += t.met;
            sum.r += t.r;
            sum.ok += t.ok;
            sum.same_cell += t.same_cell;
            sum.tie_free += t.tie_free;
            sum.fail += t.fail;
            if let Some(p) = n {
                next.push(p);
            }
            if let (Some(l), Some(w)) = (line, exc.as_mut()) {
                writeln!(w, "{l}").unwrap();
            }
        }
        failed += sum.fail;
        eprintln!("depth {depth}: {} positions, {} R ({:.0} s)", sum.met, sum.r, t0.elapsed().as_secs_f64());
        tallies.push((depth, sum));
        frontier = next;
    }
    for (depth, t) in &tallies {
        println!(
            "depth {depth} | {} positions met | {} with an R record | rule reply covered {} | same cell {} | tiebreak free {} | failed {}",
            t.met, t.r, t.ok, t.same_cell, t.tie_free, t.fail
        );
    }
    println!("{}", if failed == 0 { format!("REPLAY OK ({frame:?} frame): the rule's reply is covered by the proof at every R position") } else { format!("REPLAY FAILED ({frame:?} frame)") });
    (failed > 0) as i32
}
