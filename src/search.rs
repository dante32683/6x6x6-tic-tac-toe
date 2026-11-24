//! AND-OR search over the opening. Maker nodes must hold for every Maker move;
//! Breaker nodes need one good reply. A Breaker reply ends the search when the
//! position after it has a certificate (check.rs).
//!
//! Environment switches (docs/search.md has the workflow):
//! - `PROOF=<path>`: write every Breaker node that held as a proof record
//!   (docs/proof-format.md) when the run ends.
//! - `CACHE=<path>`: proof records from earlier runs. Every Breaker position
//!   they cover counts as proven without a search, and new records are
//!   appended as they are found, so a stopped or failed run keeps its work.
//! - `COLLECT=1`: a last-round position with no certificate becomes pending
//!   instead of failed, and the search keeps going instead of backing up, so
//!   one pass lists every position that still needs a template.
//! - `HARD=<path>`: `FAIL` lines already harvested without success; in collect
//!   mode a leaf whose written replies are all listed fails for real.
//! - `FRONTIER=<path>`: failed or pending leaves as `FAIL` lines for gen/harvest.py.
//! - `SPLIT=k/n` (collect mode): at Maker's second move search only every
//!   n-th move class starting at k and leave the rest pending, so n machines
//!   can share one pass; concatenate their caches before the next pass.
//! - `RULE=<spec>` (rule.rs, docs/rule.md): at nodes that are not leaves,
//!   try the rule's reply before the slack-ranked ones, so the proof's R
//!   records follow the rule except where it had to fall back. Leaf replies
//!   (L records) stay free. Unset: the default search, unchanged.
//! - `SEED=<path>[,<path>...]` (needs CACHE): proof or cache files whose leaf
//!   (L) records count as proven, read-only; their R records are ignored, so
//!   a rule run reuses an earlier proof's certificates without its replies.
//!   The first time the search uses a seed leaf it copies that record into
//!   CACHE, so CACHE stays a complete proof of what it holds.
//! - `NOCERT=1`: no certificate search in the last round (only CACHE and
//!   SEED leaves count there; earlier rounds still look for leaves); with
//!   COLLECT, one pass counts the last-round leaves a rule needs.

use crate::bits::Cells;
use crate::check::{certify, dead_blocks, reply_views, slack, views_after, views_at, Cert, HoldsAt, View};
use crate::data::Data;
use crate::fasthash::{FxDashMap as DashMap, FxHashSet as HashSet};
use rayon::prelude::*;
use std::io::Write;
use std::sync::atomic::{AtomicBool, AtomicU64, Ordering::Relaxed};
use std::sync::Mutex;

/// What a search of one node established. Ordered from best to worst, so
/// combining the children of a Maker node is `max`.
#[derive(Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Debug)]
pub enum Outcome {
    Proven,
    /// Collect mode only: proven except for leaves still waiting on templates.
    Pending,
    Failed,
}

/// Highest `rounds` value the per-depth progress counters track (main.rs caps rounds at 64).
const MAX_ROUNDS: usize = 64;

pub struct Search<'a> {
    pub data: &'a Data,
    /// Breaker replies explored per Breaker node (best by slack first)
    pub width: usize,
    /// canonical Maker-to-move position -> (fewest rounds proven, most rounds refuted)
    memo: DashMap<(Cells, Cells), (u8, u8)>,
    pub breaker_nodes: AtomicU64,
    pub certified: AtomicU64,
    /// env FRONTIER=<path>: write failed last-round Breaker nodes there as
    /// `FAIL maker=.. breaker=..` lines (Maker to move, after each of the top
    /// FRONTIER_REPLIES replies) for gen/harvest.py
    frontier: Option<Mutex<std::fs::File>>,
    frontier_seen: DashMap<(Cells, Cells), ()>,
    /// env PROOF set: Breaker's winning reply at every Breaker node that held,
    /// keyed by its exact (Maker, Breaker) position, with the certificate when
    /// the reply ends the line of play (docs/proof-format.md)
    witness: Option<DashMap<(Cells, Cells), (usize, Option<Cert>)>>,
    collect: bool,
    /// canonical Maker-to-move position -> most rounds found pending (collect mode)
    pending_memo: DashMap<(Cells, Cells), u8>,
    /// canonical `FAIL` positions from HARD
    hard: HashSet<(Cells, Cells)>,
    /// canonical Breaker-to-move positions with a record in CACHE
    cache: HashSet<(Cells, Cells)>,
    /// the CACHE file, copied into the proof by `write_proof`
    cache_path: Option<String>,
    cache_out: Option<Mutex<std::fs::File>>,
    pub cache_hits: AtomicU64,
    /// distinct last-round positions written as FAIL lines (failed or pending)
    pub leaves_failed: AtomicU64,
    /// Maker moves started and finished at Maker nodes, by `rounds` left
    pub moves_started: Vec<AtomicU64>,
    pub moves_done: Vec<AtomicU64>,
    /// SPLIT=k/n: (k, n)
    split: Option<(usize, usize)>,
    /// `rounds` at the Maker nodes SPLIT divides (Maker's second move); set by `prove`
    pub split_rounds: u8,
    /// RULE: the reply tried first at non-leaf nodes
    rule: Option<crate::rule::Rule>,
    /// non-leaf nodes that held, and those that held with a reply other than the rule's
    pub rule_nodes: AtomicU64,
    pub rule_exceptions: AtomicU64,
    /// SEED files, and canonical leaf position -> (file, byte offset of its L record)
    seed_files: Vec<String>,
    seed: crate::fasthash::FxHashMap<(Cells, Cells), (usize, u64)>,
    /// seed positions already copied into CACHE
    seed_used: DashMap<(Cells, Cells), ()>,
    /// NOCERT: no certificate search, only cached leaves
    nocert: bool,
}

/// `-` or a comma list of cell ids, as in docs/proof-format.md.
fn parse_cells(s: &str) -> Option<Cells> {
    let mut c = Cells::EMPTY;
    if s != "-" {
        for t in s.split(',') {
            let i: usize = t.parse().ok()?;
            if i >= crate::bits::CELLS {
                return None;
            }
            c.insert(i);
        }
    }
    Some(c)
}

fn fmt_cells(s: &Cells) -> String {
    if s.is_empty() {
        "-".to_string()
    } else {
        s.iter().map(|c| c.to_string()).collect::<Vec<_>>().join(",")
    }
}

/// A `FAIL maker=.. breaker=.. [reply=..]` line: Maker to move, Breaker's
/// cells with his last reply included, and that reply when the line names it.
pub fn parse_fail_line(l: &str) -> Option<(Cells, Cells, Option<usize>)> {
    let mut f = l.split_whitespace();
    if f.next()? != "FAIL" {
        return None;
    }
    let m = parse_cells(f.next()?.strip_prefix("maker=")?)?;
    let b = parse_cells(f.next()?.strip_prefix("breaker=")?)?;
    let reply = match f.next() {
        Some(t) => Some(t.strip_prefix("reply=")?.parse().ok().filter(|&r| b.has(r))?),
        None => None,
    };
    Some((m, b, reply))
}

/// `FAIL` lines as (Maker, Breaker) cell sets.
fn read_fail_lines(path: &str) -> Vec<(Cells, Cells)> {
    let text = std::fs::read_to_string(path).unwrap_or_else(|e| panic!("reading {path}: {e}"));
    text.lines().filter_map(parse_fail_line).map(|(m, b, _)| (m, b)).collect()
}

/// Views kept per node for ranking and certifying replies. Every learned
/// template adds 48 symmetric views, and ranking scores each view for each of
/// ~200 replies; one reply changes a view's slack by only a few cells, so the
/// best views before the reply are the ones worth scoring after it.
const VIEW_SHORTLIST: usize = 128;

/// The `VIEW_SHORTLIST` views with the best slack before Breaker's reply.
/// First line of a cache file: the board it belongs to (a comment to the verifier).
const BOARD_PREFIX: &str = "# board ";

pub fn board_line() -> String {
    let n = crate::bits::SIDE;
    format!("{BOARD_PREFIX}{n}x{n}x{n}")
}

/// The cells Breaker must take now: the empty cell of each live line Maker is
/// one mark short of. None when Maker has already completed a line or has two
/// such threats, since Breaker can block only one.
pub fn forced_replies(d: &Data, maker: &Cells, empty: &Cells, live: &crate::bits::Lines) -> Option<Vec<usize>> {
    let mut forced = Vec::new();
    for li in live.iter() {
        let m = d.line_mask[li];
        let n = m.and(maker).count() as usize;
        if n == crate::bits::SIDE {
            return None;
        }
        if n == crate::bits::SIDE - 1 {
            forced.extend(m.and(empty).iter());
        }
    }
    forced.sort();
    forced.dedup();
    (forced.len() <= 1).then_some(forced)
}

/// What `scan_cache` found in a cache file's text.
pub struct CacheScan {
    pub records: usize,
    /// the file has a `# board` line (it matched this build's board)
    pub sized: bool,
    /// bytes after the last newline: a torn last write, not yet removed
    pub torn: usize,
}

/// Checks a cache file's text and calls `on_record(maker, breaker, line)`
/// for each record. Panics, before anything is changed on disk, on a board
/// line for another board, a line that is not a whole record, or a torn tail
/// that cannot be the start of a record (so `CACHE=data6.json` is refused,
/// not truncated). Caches written before the board line existed are 6x6x6.
pub fn scan_cache(p: &str, text: &str, mut on_record: impl FnMut(&Cells, &Cells, &str)) -> CacheScan {
    let whole_len = text.rfind('\n').map_or(0, |i| i + 1);
    let tail = &text[whole_len..];
    if !(tail.is_empty() || tail.starts_with('#') || tail.starts_with("R |") || tail.starts_with("L |") || "R |".starts_with(tail) || "L |".starts_with(tail)) {
        panic!("{p}: not a cache file (its last line is not a proof record): {tail:.60}");
    }
    let board = board_line();
    let (mut sized, mut records) = (false, 0);
    for (n, l) in text[..whole_len].lines().enumerate() {
        if let Some(size) = l.strip_prefix(BOARD_PREFIX) {
            if l != board {
                panic!("{p}:{}: cache is for a {size} board; this build plays {}", n + 1, &board[BOARD_PREFIX.len()..]);
            }
            sized = true;
            continue;
        }
        if l.starts_with('#') {
            continue;
        }
        // only this program writes caches; anything else means corruption,
        // a second writer, or a bad merge, so stop rather than guess
        let f: Vec<&str> = l.split(" | ").collect();
        let whole = matches!((f.first(), f.len()), (Some(&"R"), 4) | (Some(&"L"), 6));
        let reply = f.get(3).and_then(|s| s.parse::<usize>().ok()).filter(|&r| r < crate::bits::CELLS);
        match (whole, f.get(1).and_then(|s| parse_cells(s)), f.get(2).and_then(|s| parse_cells(s)), reply) {
            (true, Some(m), Some(b), Some(_)) => {
                on_record(&m, &b, l);
                records += 1;
            }
            _ => panic!("{p}:{}: not a proof record: {l:.80}", n + 1),
        }
    }
    if !sized && records > 0 && crate::bits::SIDE != 6 {
        panic!("{p} has no board-size line, so a 6x6x6 build wrote it; use a new CACHE file");
    }
    CacheScan { records, sized, torn: tail.len() }
}

fn shortlist(mut vs: Vec<View>, live: &crate::bits::Lines, breaker: &Cells) -> Vec<View> {
    if vs.len() > VIEW_SHORTLIST && std::env::var("NOSHORTLIST").is_err() {
        vs.sort_by_cached_key(|v| std::cmp::Reverse(slack(v, live, breaker)));
        vs.truncate(VIEW_SHORTLIST);
    }
    vs
}

/// Views kept for the last-resort leaf check, ranked at the position after
/// Breaker's reply. Measured 2026-11-18 on class 2's 50 frontier positions
/// (check mode, SHORTLIST=n): 128 certified 7, 512 certified 15, 2048 and
/// all 61,872 certified 17.
const WIDE_SHORTLIST: usize = 2048;

/// Replies per failed frontier node written out for harvesting.
const FRONTIER_REPLIES: usize = 2;

const UNKNOWN_TRUE: u8 = u8::MAX;
/// Breaker replies per node that get the slow repair stage of the leaf check.
const DEEP_REPLIES: usize = 3;

impl<'a> Search<'a> {
    /// A search with no files: no CACHE, HARD, FRONTIER, PROOF, or SPLIT,
    /// whatever the environment says (playouts and tests).
    pub fn new(data: &'a Data, width: usize) -> Self {
        Self::build(data, width, false)
    }

    /// A search configured from PROOF, CACHE, COLLECT, HARD, FRONTIER, and
    /// SPLIT (module docs); only `prove` and `import` use this.
    pub fn from_env(data: &'a Data, width: usize) -> Self {
        Self::build(data, width, true)
    }

    fn build(data: &'a Data, width: usize, use_env: bool) -> Self {
        let var = |k: &str| if use_env { std::env::var(k).ok() } else { None };
        let frontier = var("FRONTIER").map(|p| Mutex::new(std::fs::File::create(p).unwrap()));
        let hard = match var("HARD") {
            Some(p) => read_fail_lines(&p).iter().map(|(m, b)| data.canonical(m, b)).collect(),
            None => HashSet::default(),
        };
        let mut cache = HashSet::default();
        let mut cache_out = None;
        let cache_path = var("CACHE");
        if let Some(p) = &cache_path {
            let text = match std::fs::read_to_string(p) {
                Ok(t) => t,
                Err(e) if e.kind() == std::io::ErrorKind::NotFound => String::new(),
                Err(e) => panic!("reading {p}: {e}"),
            };
            let scan = scan_cache(p, &text, |m, b, _| {
                cache.insert(data.canonical(m, b));
            });
            // only a stopped run's last write can be torn (each record is one
            // write ending in a newline); the file was checked above, so
            // dropping the tail can't cut into something that isn't a cache
            if scan.torn > 0 {
                let f = std::fs::OpenOptions::new().write(true).open(p).unwrap_or_else(|e| panic!("opening {p}: {e}"));
                f.set_len((text.len() - scan.torn) as u64).unwrap_or_else(|e| panic!("truncating {p}: {e}"));
            }
            println!("cache {p}: {} records, {} positions, {} bytes of a torn last line dropped", scan.records, cache.len(), scan.torn);
            let mut f = std::fs::OpenOptions::new().create(true).append(true).open(p).unwrap_or_else(|e| panic!("opening {p}: {e}"));
            if !scan.sized && scan.records == 0 {
                writeln!(f, "{}", board_line()).unwrap_or_else(|e| panic!("writing {p}: {e}"));
            }
            cache_out = Some(Mutex::new(f));
        }
        let seed_files: Vec<String> = var("SEED").map(|v| v.split(',').map(String::from).collect()).unwrap_or_default();
        if !seed_files.is_empty() && cache_out.is_none() {
            panic!("SEED needs CACHE: used seed leaves are copied there");
        }
        let mut seed = crate::fasthash::FxHashMap::default();
        for (fi, p) in seed_files.iter().enumerate() {
            let text = std::fs::read_to_string(p).unwrap_or_else(|e| panic!("reading SEED {p}: {e}"));
            let mut leaves = 0;
            let scan = scan_cache(p, &text, |m, b, line| {
                if line.starts_with("L |") {
                    // `line` is a slice of `text`, so its offset is the pointer difference
                    let at = line.as_ptr() as u64 - text.as_ptr() as u64;
                    seed.entry(data.canonical(m, b)).or_insert((fi, at));
                    leaves += 1;
                }
            });
            if scan.torn > 0 {
                panic!("SEED {p} has a torn last line; seeds are read-only, so repair it with merge-cache first");
            }
            println!("seed {p}: {leaves} leaf records of {}; {} seed positions in all", scan.records, seed.len());
        }
        let collect = var("COLLECT").is_some();
        let split = var("SPLIT").map(|v| {
            let parsed = v.split_once('/').and_then(|(k, n)| Some((k.parse::<usize>().ok()?, n.parse::<usize>().ok()?)));
            match parsed {
                Some((k, n)) if k < n && collect => (k, n),
                _ => panic!("SPLIT must be k/n with k < n, and needs COLLECT=1 (got {v})"),
            }
        });
        // with a cache every record is already on disk, so `write_proof`
        // copies the file instead of keeping the whole strategy in memory
        let witness = (var("PROOF").is_some() && cache_out.is_none()).then(DashMap::default);
        let counters = || (0..=MAX_ROUNDS).map(|_| AtomicU64::new(0)).collect();
        Search {
            data,
            width,
            memo: DashMap::default(),
            breaker_nodes: AtomicU64::new(0),
            certified: AtomicU64::new(0),
            frontier,
            frontier_seen: DashMap::default(),
            witness,
            collect,
            pending_memo: DashMap::default(),
            hard,
            cache,
            cache_path,
            cache_out,
            cache_hits: AtomicU64::new(0),
            leaves_failed: AtomicU64::new(0),
            moves_started: counters(),
            moves_done: counters(),
            split,
            split_rounds: 0,
            rule: if use_env { crate::rule::from_env() } else { None },
            rule_nodes: AtomicU64::new(0),
            rule_exceptions: AtomicU64::new(0),
            seed_files,
            seed,
            seed_used: DashMap::default(),
            nocert: var("NOCERT").is_some(),
        }
    }

    /// Maker to move. Proven if Breaker holds with at most `rounds` more
    /// replies before reaching a certified (or cached) position.
    pub fn maker_node(&self, maker: &Cells, breaker: &Cells, rounds: u8) -> Outcome {
        if rounds == 0 {
            return Outcome::Failed;
        }
        let key = self.data.canonical(maker, breaker);
        if let Some(e) = self.memo.get(&key) {
            let (t, f) = *e;
            if t != UNKNOWN_TRUE && t <= rounds {
                return Outcome::Proven;
            }
            if f != 0 && f >= rounds {
                return Outcome::Failed;
            }
        }
        if self.collect && self.pending_memo.get(&key).is_some_and(|r| *r >= rounds) {
            return Outcome::Pending;
        }
        // one child per symmetry class of Maker's move
        let empty = Cells::all().minus(maker).minus(breaker);
        let mut seen = HashSet::default();
        let moves: Vec<usize> = empty
            .iter()
            .filter(|&m| seen.insert(self.data.canonical(&maker.with(m), breaker)))
            .collect();
        let r = rounds as usize;
        self.moves_started[r].fetch_add(moves.len() as u64, Relaxed);
        // stop early once the answer is known: any failure decides it, and
        // outside collect mode anything short of proven does
        let stop = AtomicBool::new(false);
        // SPLIT: another machine searches the other move classes here
        let mine = |i: usize| match self.split {
            Some((k, n)) if rounds == self.split_rounds => i % n == k,
            _ => true,
        };
        let child = |&(i, m): &(usize, usize)| {
            let o = if stop.load(Relaxed) {
                Outcome::Failed
            } else if !mine(i) {
                Outcome::Pending
            } else {
                self.breaker_node(&maker.with(m), breaker, rounds)
            };
            if o == Outcome::Failed || (!self.collect && o != Outcome::Proven) {
                stop.store(true, Relaxed);
            }
            self.moves_done[r].fetch_add(1, Relaxed);
            o
        };
        let moves: Vec<(usize, usize)> = moves.into_iter().enumerate().collect();
        let worst = if rounds >= 2 { moves.par_iter().map(child).max() } else { moves.iter().map(child).max() };
        let out = worst.unwrap_or(Outcome::Proven);
        match out {
            Outcome::Proven => {
                let mut e = self.memo.entry(key).or_insert((UNKNOWN_TRUE, 0));
                e.0 = e.0.min(rounds);
            }
            Outcome::Failed => {
                let mut e = self.memo.entry(key).or_insert((UNKNOWN_TRUE, 0));
                e.1 = e.1.max(rounds);
            }
            Outcome::Pending => {
                let mut e = self.pending_memo.entry(key).or_insert(0);
                *e = (*e).max(rounds);
            }
        }
        out
    }

    /// Breaker to move with `rounds` replies left (this one included).
    pub fn breaker_node(&self, maker: &Cells, breaker: &Cells, rounds: u8) -> Outcome {
        self.breaker_nodes.fetch_add(1, Relaxed);
        let d = self.data;
        if !self.cache.is_empty() || !self.seed.is_empty() {
            let key = d.canonical(maker, breaker);
            if self.cache.contains(&key) {
                self.cache_hits.fetch_add(1, Relaxed);
                return Outcome::Proven;
            }
            if let Some(&(fi, at)) = self.seed.get(&key) {
                if self.seed_used.insert(key, ()).is_none() {
                    self.copy_seed(fi, at);
                }
                self.cache_hits.fetch_add(1, Relaxed);
                return Outcome::Proven;
            }
        }
        let empty = Cells::all().minus(maker).minus(breaker);
        let live = d.live_lines(breaker);
        // a finished Maker line or a double threat is a loss; one threat forces the reply
        let Some(forced) = forced_replies(d, maker, &empty, &live) else {
            return Outcome::Failed;
        };
        // NOCERT: an uncached leaf is only counted (ranking it costs more than the count is worth)
        if self.nocert && rounds <= 1 {
            if self.frontier_seen.insert(d.canonical(maker, breaker), ()).is_none() {
                self.leaves_failed.fetch_add(1, Relaxed);
            }
            return if self.collect { Outcome::Pending } else { Outcome::Failed };
        }
        let mut h = HoldsAt::new(d, maker, breaker);
        let vs = shortlist(views_at(&mut h), &live, breaker);
        let (dead, reach) = dead_blocks(&mut h);
        let candidates: Vec<usize> = if forced.is_empty() { empty.iter().collect() } else { forced };
        // views a reply inside a Maker-touched block may revive
        let extras: Vec<Vec<View>> = candidates
            .iter()
            .map(|&c| if reach.has(c) { reply_views(&mut h, c, &dead) } else { Vec::new() })
            .collect();
        // rank replies by the best template slack after them
        let mut ranked: Vec<(i32, usize, usize)> = candidates
            .iter()
            .enumerate()
            .map(|(k, &c)| {
                let b = breaker.with(c);
                let mut lv = live;
                for &li in &d.cell_lines[c] {
                    lv.0[li / 64] &= !(1 << (li % 64));
                }
                let best = vs.iter().chain(&extras[k]).map(|v| slack(v, &lv, &b)).max().unwrap_or(i32::MIN);
                (best, c, k)
            })
            .collect();
        ranked.sort_unstable_by(|a, b| b.cmp(a));
        let viable: Vec<(usize, usize)> = ranked.iter().take_while(|r| r.0 >= 0).map(|r| (r.1, r.2)).collect();
        // fast checks on every viable reply, the slow repair on the best few, then
        // a last resort for those few: views rebuilt after the reply (the reply
        // changes which templates rank best) with a much wider shortlist
        for stage in 0..3 {
            let n = if stage == 0 { viable.len() } else { DEEP_REPLIES };
            for &(c, k) in viable.iter().take(n) {
                let b2 = breaker.with(c);
                let found = if stage < 2 {
                    certify(d, &vs, &extras[k], maker, &b2, stage == 1)
                } else {
                    let lv = d.live_lines(&b2);
                    let mut wide = views_after(&mut h, c);
                    wide.sort_by_cached_key(|v| std::cmp::Reverse(slack(v, &lv, &b2)));
                    wide.truncate(WIDE_SHORTLIST);
                    certify(d, &wide, &[], maker, &b2, true)
                };
                if let Some(cert) = found {
                    self.certified.fetch_add(1, Relaxed);
                    self.record(maker, breaker, c, Some(cert));
                    return Outcome::Proven;
                }
            }
        }
        if rounds <= 1 {
            let fails: Vec<Cells> = ranked.iter().take(FRONTIER_REPLIES).map(|&(_, c, _)| breaker.with(c)).collect();
            // collect mode: pending unless every written reply was already
            // harvested without success
            let pending = self.collect && !fails.iter().all(|b| self.hard.contains(&d.canonical(maker, b)));
            if (pending || !self.collect) && self.frontier_seen.insert(d.canonical(maker, breaker), ()).is_none() {
                self.leaves_failed.fetch_add(1, Relaxed);
                if let Some(f) = &self.frontier {
                    let out: String = ranked
                        .iter()
                        .take(FRONTIER_REPLIES)
                        .map(|&(_, c, _)| format!("FAIL maker={} breaker={} reply={c}\n", fmt_cells(maker), fmt_cells(&breaker.with(c))))
                        .collect();
                    f.lock().unwrap().write_all(out.as_bytes()).unwrap();
                }
            }
            return if pending { Outcome::Pending } else { Outcome::Failed };
        }
        // RULE: the rule's reply first, then the best-slack others within width
        let rule_reply = self.rule.as_ref().and_then(|r| r.reply(d, maker, breaker)).filter(|c| candidates.contains(c));
        let order: Vec<usize> = match rule_reply {
            Some(rc) => std::iter::once(rc).chain(ranked.iter().map(|r| r.1).filter(|&c| c != rc)).take(self.width).collect(),
            None => ranked.iter().take(self.width).map(|r| r.1).collect(),
        };
        for c in order {
            match self.maker_node(maker, &breaker.with(c), rounds - 1) {
                Outcome::Proven => {
                    self.record(maker, breaker, c, None);
                    if self.rule.is_some() {
                        self.rule_nodes.fetch_add(1, Relaxed);
                        if rule_reply != Some(c) {
                            self.rule_exceptions.fetch_add(1, Relaxed);
                        }
                    }
                    return Outcome::Proven;
                }
                // collect mode commits to the first reply that isn't refuted
                Outcome::Pending => return Outcome::Pending,
                Outcome::Failed => {}
            }
        }
        Outcome::Failed
    }

    /// Imports a leaf certificate found outside the search (a CP-SAT layout
    /// from gen/harvest.py): Breaker to move at (maker, breaker), replying
    /// `reply`, then `blocks` plus a pairing. Checked like a search
    /// certificate (`cert_from_blocks`); recorded only if it holds.
    pub fn import_leaf(&self, maker: &Cells, breaker: &Cells, reply: usize, blocks: &[usize]) -> bool {
        let b2 = breaker.with(reply);
        if maker.has(reply) || breaker.has(reply) {
            return false;
        }
        match crate::check::cert_from_blocks(self.data, blocks, maker, &b2) {
            Some(cert) => {
                self.record(maker, breaker, reply, Some(cert));
                true
            }
            None => false,
        }
    }

    /// Keeps Breaker's reply `c` at a node that held (with its certificate when
    /// the reply ends the line of play), and appends it to CACHE. A node's
    /// children always finish first, so the cache file is in children-first
    /// order and any prefix of it is closed under the strategy.
    pub fn record(&self, maker: &Cells, breaker: &Cells, c: usize, cert: Option<Cert>) {
        if let Some(f) = &self.cache_out {
            let line = self.record_line(maker, breaker, c, &cert) + "\n";
            f.lock().unwrap().write_all(line.as_bytes()).unwrap();
        }
        if let Some(w) = &self.witness {
            w.insert((*maker, *breaker), (c, cert));
        }
    }

    /// Appends the seed record at byte `at` of seed file `fi` to CACHE.
    fn copy_seed(&self, fi: usize, at: u64) {
        use std::io::{BufRead, Seek};
        let p = &self.seed_files[fi];
        let mut r = std::io::BufReader::new(std::fs::File::open(p).unwrap_or_else(|e| panic!("opening SEED {p}: {e}")));
        r.seek(std::io::SeekFrom::Start(at)).unwrap_or_else(|e| panic!("seeking SEED {p}: {e}"));
        let mut line = String::new();
        r.read_line(&mut line).unwrap_or_else(|e| panic!("reading SEED {p}: {e}"));
        assert!(line.starts_with("L |") && line.ends_with('\n'), "SEED {p} changed during the run (offset {at})");
        let f = self.cache_out.as_ref().expect("SEED needs CACHE");
        f.lock().unwrap().write_all(line.as_bytes()).unwrap();
    }

    /// One record in the format of docs/proof-format.md.
    fn record_line(&self, m: &Cells, b: &Cells, r: usize, cert: &Option<Cert>) -> String {
        let d = self.data;
        let Some(cert) = cert else { return format!("R | {} | {} | {}", fmt_cells(m), fmt_cells(b), r) };
        let blocks: Vec<String> = cert
            .blocks
            .iter()
            .map(|&bi| {
                let blk = &d.blocks[bi];
                // each claimed line as two of its cells inside the block
                let lines: Vec<String> = blk
                    .lines
                    .iter()
                    .map(|li| {
                        let mut two = d.line_cells[li].iter().filter(|&&c| blk.cells.has(c));
                        format!("{}/{}", two.next().unwrap(), two.next().unwrap())
                    })
                    .collect();
                format!("{} : {}", fmt_cells(&blk.cells), lines.join(","))
            })
            .collect();
        let pairs: Vec<String> = cert.pairs.iter().map(|&(_, a, b2)| format!("{}/{}", a.min(b2), a.max(b2))).collect();
        let or_dash = |v: Vec<String>| if v.is_empty() { "-".to_string() } else { v.join(" ; ") };
        format!("L | {} | {} | {} | {} | {}", fmt_cells(m), fmt_cells(b), r, or_dash(blocks), or_dash(pairs))
    }

    /// Writes every record: the CACHE file's (loaded at start and appended
    /// during the run), or without a cache the ones kept in memory. Only a
    /// complete proof after `prove` returned proven for the classes run.
    pub fn write_proof(&self, path: &str) -> std::io::Result<usize> {
        // write beside the target, then rename, so a crash or full disk never
        // leaves a truncated file under the proof's name
        let tmp = format!("{path}.partial");
        let mut f = std::io::BufWriter::new(std::fs::File::create(&tmp)?);
        let n = crate::bits::SIDE;
        writeln!(f, "# {n}x{n}x{n} Maker-Breaker proof; format: docs/proof-format.md")?;
        let mut count = 0;
        if let Some(p) = &self.cache_path {
            let text = std::fs::read_to_string(p)?;
            let mut err = Ok(());
            scan_cache(p, &text, |_, _, line| {
                if err.is_ok() {
                    err = writeln!(f, "{line}");
                    count += 1;
                }
            });
            err?;
        } else if let Some(w) = &self.witness {
            for e in w.iter() {
                let ((m, b), (r, cert)) = (e.key(), e.value());
                writeln!(f, "{}", self.record_line(m, b, *r, cert))?;
                count += 1;
            }
        }
        f.into_inner().map_err(|e| e.into_error())?.sync_all()?;
        std::fs::rename(&tmp, path)?;
        Ok(count)
    }

    /// One status line: work counts and, per depth, Maker moves finished out
    /// of those started (depth 1 is Maker's second move).
    pub fn progress_line(&self, rounds: u8) -> String {
        let mut depth = String::new();
        for (k, r) in (1..rounds as usize).rev().enumerate() {
            let (done, started) = (self.moves_done[r].load(Relaxed), self.moves_started[r].load(Relaxed));
            if started > 0 {
                depth += &format!(" d{} {done}/{started}", k + 1);
            }
        }
        let rule = match &self.rule {
            Some(r) => format!("; rule {}: {} of {} replies are exceptions", r.spec, self.rule_exceptions.load(Relaxed), self.rule_nodes.load(Relaxed)),
            None => String::new(),
        };
        format!(
            "breaker nodes {}, certified {}, cache hits {}, failed or pending leaves {}; Maker moves done/started:{depth}{rule}",
            self.breaker_nodes.load(Relaxed),
            self.certified.load(Relaxed),
            self.cache_hits.load(Relaxed),
            self.leaves_failed.load(Relaxed),
        )
    }
}
