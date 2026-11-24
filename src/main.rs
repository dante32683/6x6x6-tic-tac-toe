//! 6x6x6 tic-tac-toe, Maker-Breaker version: search for a Breaker strategy
//! (opening replies, then a block-and-pair certificate). A full Breaker win
//! would prove the ordinary game is a draw.
//!
//! Usage:
//!   cube6 playout <rounds> <games> <seed>   greedy Breaker vs heuristic Maker
//!   cube6 prove <rounds> <width> [classes]  opening search from the empty board (classes: e.g. "0,3")
//!   cube6 check <file>                      certify each `FAIL maker=.. breaker=..` line
//!   cube6 import <certs.json>...            append harvested leaf certificates to CACHE
//!   cube6 merge-cache <out> <cache>...      join caches (from SPLIT machines) into a new file
//!   cube6 rules <proof>...                  how often R replies follow the RULE specs (`;`-separated; docs/rule.md)
//!   cube6 replay <proof>                    play the RULE as Breaker's own strategy and check the proof covers it
//!   cube6 extend <rounds> <failures>        prove the rule's own reply at each replay failure; records go to CACHE
//!
//! `prove` prints a progress line every PROGRESS seconds (default 300) and
//! reads PROOF, CACHE, COLLECT, HARD, and FRONTIER (search.rs; workflow in
//! docs/search.md).

mod bits;
mod check;
mod data;
mod fasthash;
mod qos;
mod repair;
mod replay;
mod rule;
mod search;
mod subgame;

use bits::Cells;
use std::io::Write;
use std::time::Instant;

/// Tiny deterministic RNG (xorshift) so playouts are reproducible.
struct Rng(u64);
impl Rng {
    fn next(&mut self) -> u64 {
        self.0 ^= self.0 << 13;
        self.0 ^= self.0 >> 7;
        self.0 ^= self.0 << 17;
        self.0
    }
    fn unit(&mut self) -> f64 {
        (self.next() >> 11) as f64 / (1u64 << 53) as f64
    }
}

fn main() {
    qos::use_all_cores();
    let args: Vec<String> = std::env::args().collect();
    let data = data::Data::load(bits::DATA_FILE);
    let n = bits::SIDE;
    println!("{n}x{n}x{n} board, {}: {} blocks, {} templates (with symmetric images)", bits::DATA_FILE, data.blocks.len(), data.templates.len());
    // a malformed argument is an error, never a silent default
    let arg = |i: usize, def: u64| match args.get(i) {
        None => def,
        Some(s) => s.parse().unwrap_or_else(|_| usage_exit(&format!("not a number: {s}"))),
    };
    let rounds = |i: usize, def: u64| match arg(i, def) {
        r @ 1..=64 => r as u8,
        r => usage_exit(&format!("rounds must be 1..=64, got {r}")),
    };
    // exit status: 0 proven (or other mode done), 1 not proven, 2 bad input or I/O failure
    let code = match args.get(1).map(|s| s.as_str()) {
        Some("playout") => {
            playout(&data, rounds(2, 4), arg(3, 100), arg(4, 1));
            0
        }
        Some("prove") => match arg(3, 4) {
            0 => usage_exit("width must be at least 1"),
            w => prove(&data, rounds(2, 3), w as usize, args.get(4).map(|s| s.as_str())),
        },
        Some("check") => match args.get(2) {
            Some(p) => {
                check_file(&data, p);
                0
            }
            None => usage_exit("check needs a file"),
        },
        Some("import") if args.len() > 2 => import(&data, &args[2..]),
        Some("merge-cache") if args.len() > 3 => merge_cache(&args[2], &args[3..]),
        Some("rules") if args.len() > 2 => rules_report(&data, &args[2..]),
        Some("extend") if args.len() == 4 => extend(&data, rounds(2, 4), &args[3]),
        Some("replay") if args.len() == 3 => {
            let spec = std::env::var("RULE").unwrap_or_else(|_| "default".into());
            let r = rule::Rule::parse(&spec).unwrap_or_else(|e| usage_exit(&e));
            let frame = std::env::var("FRAME").unwrap_or_else(|_| "search".into());
            let frame = replay::Frame::parse(&frame).unwrap_or_else(|| usage_exit("FRAME is fixed, search, geometric, or full"));
            replay::run(&data, &r, &args[2], frame)
        }
        _ => usage_exit("unknown mode"),
    };
    std::process::exit(code);
}

fn usage_exit(msg: &str) -> ! {
    eprintln!("{msg}\nusage: cube6 playout <rounds> <games> <seed> | prove <rounds> <width> [classes] | check <file> | import <certs.json>... | merge-cache <out> <cache>... | rules <proof>... | replay <proof> | extend <rounds> <failures>");
    std::process::exit(2);
}

/// One leaf layout from gen/harvest.py's `.certs.json`: the `FAIL` line it
/// solves (with `reply=`) and the library blocks CP-SAT chose.
#[derive(serde::Deserialize)]
struct HarvestedLeaf {
    fail: String,
    blocks: Vec<usize>,
}

/// Checks each harvested leaf layout and appends the ones that hold to
/// CACHE as leaf records, so the next pass finds those leaves proven even
/// when the merged template misses the search's shortlist.
/// Joins cache files into a new one: each input's torn last line is dropped
/// and every record checked (`search::scan_cache`), with one board line.
/// Byte or line concatenation can glue a torn record onto the next line or
/// keep it as a shorter, wrong record, so SPLIT caches are joined with this.
fn merge_cache(out: &str, inputs: &[String]) -> i32 {
    if std::path::Path::new(out).exists() {
        usage_exit(&format!("{out} exists; merge-cache writes a new file"));
    }
    let tmp = format!("{out}.partial");
    let write = || -> std::io::Result<usize> {
        let mut f = std::io::BufWriter::new(std::fs::File::create(&tmp)?);
        writeln!(f, "{}", search::board_line())?;
        let mut n = 0;
        for p in inputs {
            let text = std::fs::read_to_string(p)?;
            let mut err = Ok(());
            let scan = search::scan_cache(p, &text, |_, _, line| {
                if err.is_ok() {
                    err = writeln!(f, "{line}");
                    n += 1;
                }
            });
            err?;
            println!("{p}: {} records, {} bytes of a torn last line dropped", scan.records, scan.torn);
        }
        f.into_inner().map_err(|e| e.into_error())?.sync_all()?;
        std::fs::rename(&tmp, out)?;
        Ok(n)
    };
    match write() {
        Ok(n) => {
            println!("wrote {n} records to {out}");
            0
        }
        Err(e) => {
            eprintln!("merge-cache: {e}");
            2
        }
    }
}

fn import(data: &data::Data, files: &[String]) -> i32 {
    if std::env::var("CACHE").is_err() {
        usage_exit("import needs CACHE=<path> to append the records to");
    }
    let s = search::Search::from_env(data, 1);
    let (mut ok, mut bad, mut no_reply) = (0, 0, 0);
    for f in files {
        let text = std::fs::read_to_string(f).unwrap_or_else(|e| usage_exit(&format!("reading {f}: {e}")));
        let leaves: Vec<HarvestedLeaf> = serde_json::from_str(&text).unwrap_or_else(|e| usage_exit(&format!("{f}: {e}")));
        for l in leaves {
            let Some((m, b, reply)) = search::parse_fail_line(&l.fail) else { usage_exit(&format!("{f}: bad FAIL line: {}", l.fail)) };
            let Some(r) = reply else {
                no_reply += 1;
                continue;
            };
            let before = b.minus(&Cells::EMPTY.with(r));
            if s.import_leaf(&m, &before, r, &l.blocks) {
                ok += 1;
            } else {
                bad += 1;
            }
        }
    }
    println!("imported {ok} leaf certificates; {bad} layouts did not check; {no_reply} lines without reply= skipped");
    0
}

/// For each proof file and each rule in RULE (`;`-separated specs, rule.rs),
/// how many R replies per depth the rule reproduces up to the position's
/// symmetry ("agree"), how many tie with the rule's choice on every feature
/// but sit in another orbit ("tied"), and how many top sets are one orbit
/// ("decided": the id tiebreak never matters there). Reads R records only.
/// With EXCEPTIONS=<path>, writes the first rule's disagreeing R records there.
fn rules_report(data: &data::Data, files: &[String]) -> i32 {
    use std::io::BufRead;
    let specs = std::env::var("RULE").unwrap_or_else(|_| "default".into());
    let rules: Vec<rule::Rule> = specs.split(';').map(|s| rule::Rule::parse(s).unwrap_or_else(|e| usage_exit(&e))).collect();
    let mut exc = std::env::var("EXCEPTIONS").ok().map(|p| std::io::BufWriter::new(std::fs::File::create(&p).unwrap_or_else(|e| usage_exit(&format!("{p}: {e}")))));
    for f in files {
        let file = std::fs::File::open(f).unwrap_or_else(|e| usage_exit(&format!("{f}: {e}")));
        let mut recs = Vec::new();
        for line in std::io::BufReader::new(file).lines() {
            let line = line.unwrap_or_else(|e| usage_exit(&format!("{f}: {e}")));
            if !line.starts_with("R |") {
                continue;
            }
            let p: Vec<&str> = line.split(" | ").collect();
            let cells = |s: &str| if s == "-" { Cells::EMPTY } else { s.split(',').fold(Cells::EMPTY, |a, t| a.with(t.parse().unwrap())) };
            recs.push((cells(p[1]), cells(p[2]), p[3].parse::<usize>().unwrap(), line.clone()));
        }
        for (ri, r) in rules.iter().enumerate() {
            // depth -> (n, agree, tied, decided)
            let mut t = std::collections::BTreeMap::<u32, [u64; 4]>::new();
            for (m, b, reply, line) in &recs {
                let e = t.entry(m.count()).or_default();
                e[0] += 1;
                let top = r.top(data, m, b);
                let key = |c: usize| data.canonical(m, &b.with(c));
                let want = key(*reply);
                let agree = key(top[0]) == want;
                e[1] += agree as u64;
                e[2] += (!agree && top.iter().any(|&c| key(c) == want)) as u64;
                e[3] += top.iter().all(|&c| key(c) == key(top[0])) as u64;
                if !agree && ri == 0 {
                    if let Some(w) = exc.as_mut() {
                        writeln!(w, "{line} | rule {}", top[0]).unwrap();
                    }
                }
            }
            for (depth, [n, a, tied, dec]) in t {
                let pc = |x: u64| 100.0 * x as f64 / n as f64;
                println!("{f} | {} | depth {depth} | {n} replies | agree {a} ({:.1}%) | tied {tied} ({:.1}%) | decided {dec} ({:.1}%)", r.spec, pc(a), pc(tied), pc(dec));
            }
        }
    }
    0
}

/// For each `FAIL` line of a replay (src/replay.rs), proves the rule's own
/// reply there: every Maker move after it must be answered within the
/// rounds left (`rounds` is the proof's total, so a reply at Maker depth k
/// leaves rounds - k). Proven replies get an R record in CACHE, next to the
/// leaf records the search writes (SEED reuses an existing proof's leaves),
/// so CACHE appended to the proof makes the replay pass at those positions.
fn extend(data: &data::Data, rounds: u8, failures: &str) -> i32 {
    use rayon::prelude::*;
    use std::io::BufRead;
    let s = search::Search::from_env(data, 1);
    let cells = |t: &str| if t == "-" { Cells::EMPTY } else { t.split(',').fold(Cells::EMPTY, |a, c| a.with(c.parse().unwrap())) };
    let file = std::fs::File::open(failures).unwrap_or_else(|e| usage_exit(&format!("{failures}: {e}")));
    let todo: Vec<(Cells, Cells, usize)> = std::io::BufReader::new(file)
        .lines()
        .map(|l| l.unwrap_or_else(|e| usage_exit(&format!("{failures}: {e}"))))
        .filter(|l| l.starts_with("FAIL |"))
        .map(|l| {
            let p: Vec<&str> = l.split(" | ").collect();
            let reply = p[3].strip_prefix("rule ").and_then(|r| r.parse().ok()).unwrap_or_else(|| usage_exit(&format!("bad line: {l}")));
            (cells(p[1]), cells(p[2]), reply)
        })
        .collect();
    let t0 = Instant::now();
    let done = std::sync::atomic::AtomicUsize::new(0);
    let outcomes: Vec<search::Outcome> = todo
        .par_iter()
        .map(|(m, b, x)| {
            let left = rounds.saturating_sub(m.count() as u8);
            let o = if left == 0 { search::Outcome::Failed } else { s.maker_node(m, &b.with(*x), left) };
            if o == search::Outcome::Proven {
                s.record(m, b, *x, None);
            } else {
                let fmt = |c: &Cells| c.iter().map(|i| i.to_string()).collect::<Vec<_>>().join(",");
                println!("NOT PROVEN | {} | {} | rule {x}", fmt(m), fmt(b));
            }
            let n = done.fetch_add(1, std::sync::atomic::Ordering::Relaxed) + 1;
            if n % 25 == 0 {
                eprintln!("{n}/{} ({:.0} s)", todo.len(), t0.elapsed().as_secs_f64());
            }
            o
        })
        .collect();
    let proven = outcomes.iter().filter(|&&o| o == search::Outcome::Proven).count();
    println!("extend: {proven} of {} rule replies proven ({:.0} s)", todo.len(), t0.elapsed().as_secs_f64());
    (proven < todo.len()) as i32
}

/// Maker plays toward squares on many open lines (with noise); Breaker plays
/// the greedy best-slack reply each round and needs a certificate after `rounds`.
fn playout(data: &data::Data, rounds: u8, games: u64, seed: u64) {
    let s = search::Search::new(data, 1);
    let mut rng = Rng(seed.wrapping_mul(0x9E3779B97F4A7C15) | 1);
    let t0 = Instant::now();
    let mut wins = 0;
    for _ in 0..games {
        let (mut m, mut b) = (Cells::EMPTY, Cells::EMPTY);
        let mut ok = false;
        for r in 0..rounds {
            let empty = Cells::all().minus(&m).minus(&b);
            let pick = empty
                .iter()
                .map(|c| {
                    let open = data.cell_lines[c].iter().filter(|&&li| !data.line_mask[li].meets(&b)).count();
                    (open as f64 + 3.0 * rng.unit(), c)
                })
                .max_by(|x, y| x.0.partial_cmp(&y.0).unwrap())
                .unwrap()
                .1;
            m.insert(pick);
            // greedy Breaker: width 1, only this round left -> picks best reply and checks it
            if s.breaker_node(&m, &b, 1) == search::Outcome::Proven {
                ok = true;
                break;
            }
            if r + 1 == rounds {
                break;
            }
            // not certified yet: play the best-slack reply and continue
            match best_reply(data, &m, &b) {
                Some(c) => b.insert(c),
                None => break, // Maker has already won
            }
        }
        if ok {
            wins += 1;
        } else if std::env::var("DUMP").is_ok() {
            // failed position after the last round, Breaker's final reply
            // included; a position Maker has already won has nothing to certify
            if let Some(c) = best_reply(data, &m, &b) {
                let fb = b.with(c);
                let fmt = |s: &Cells| s.iter().map(|c| c.to_string()).collect::<Vec<_>>().join(",");
                println!("FAIL maker={} breaker={}", fmt(&m), fmt(&fb));
            }
        }
    }
    println!("rounds {rounds}: certified {wins}/{games} ({:.1}s)", t0.elapsed().as_secs_f64());
}

/// Certify Maker-to-move positions dumped by `playout` (DUMP set).
fn check_file(data: &data::Data, path: &str) {
    let (mut n, mut ok) = (0, 0);
    for line in std::fs::read_to_string(path).unwrap().lines() {
        if !line.starts_with("FAIL") {
            continue;
        }
        let Some((m, b, _)) = search::parse_fail_line(line) else { usage_exit(&format!("{path}: bad FAIL line: {line}")) };
        let mut vs = check::views(data, &m, &b);
        // SHORTLIST=n keeps only the n best-slack views, as the search does
        if let Some(n) = std::env::var("SHORTLIST").ok().and_then(|s| s.parse::<usize>().ok()) {
            let live = data.live_lines(&b);
            vs.sort_by_cached_key(|v| std::cmp::Reverse(check::slack(v, &live, &b)));
            vs.truncate(n);
        }
        if std::env::var("STATS").is_ok() {
            let (mut touched, mut held) = (0, 0);
            for t in &data.templates {
                for &bi in t {
                    if data.blocks[bi].cells.meets(&m) {
                        touched += 1;
                        held += check::block_holds(data, bi, &m, &b) as u32;
                    }
                }
            }
            let live = data.live_lines(&b);
            let best = vs.iter().map(|v| check::slack(v, &live, &b)).max().unwrap();
            println!("touched {touched} held {held} best slack {best}");
        }
        n += 1;
        if check::certify(data, &vs, &[], &m, &b, true).is_some() {
            ok += 1;
        } else if std::env::var("DUMP").is_ok() {
            println!("{line}");
        }
    }
    println!("certified {ok}/{n}");
}

/// Breaker's playout reply: a forced block when Maker threatens a line,
/// otherwise the reply leaving the best template slack. None when Maker has
/// already won (a finished line or two threats).
fn best_reply(data: &data::Data, m: &Cells, b: &Cells) -> Option<usize> {
    let live = data.live_lines(b);
    let empty = Cells::all().minus(m).minus(b);
    let forced = search::forced_replies(data, m, &empty, &live)?;
    if let Some(&c) = forced.first() {
        return Some(c);
    }
    let mut h = check::HoldsAt::new(data, m, b);
    let vs = check::views_at(&mut h);
    let (dead, reach) = check::dead_blocks(&mut h);
    empty
        .iter()
        .max_by_key(|&c| {
            let bb = b.with(c);
            let mut lv = live;
            for &li in &data.cell_lines[c] {
                lv.0[li / 64] &= !(1 << (li % 64));
            }
            let extra = if reach.has(c) { check::reply_views(&mut h, c, &dead) } else { Vec::new() };
            vs.iter().chain(&extra).map(|v| check::slack(v, &lv, &bb)).max().unwrap()
        })
}

/// `only`: comma-separated positions in the first-move class list (e.g. "0"), or all.
/// Returns the exit status: 0 all run classes hold, 1 not proven, 2 bad input or write failure.
/// Seconds between progress lines in `prove` (env PROGRESS overrides; 0 turns them off).
const PROGRESS_SECS: u64 = 300;

fn prove(data: &data::Data, rounds: u8, width: usize, only: Option<&str>) -> i32 {
    let mut s = search::Search::from_env(data, width);
    s.split_rounds = rounds - 1;
    let every = match std::env::var("PROGRESS") {
        Ok(v) => v.parse().unwrap_or_else(|_| usage_exit(&format!("PROGRESS is not a number: {v}"))),
        Err(_) => PROGRESS_SECS,
    };
    let finished = std::sync::atomic::AtomicBool::new(false);
    std::thread::scope(|scope| {
        let reporter = (every > 0).then(|| {
            scope.spawn(|| {
                let t0 = Instant::now();
                loop {
                    std::thread::park_timeout(std::time::Duration::from_secs(every));
                    if finished.load(std::sync::atomic::Ordering::Relaxed) {
                        break;
                    }
                    println!("progress {:.2} h: {}", t0.elapsed().as_secs_f64() / 3600.0, s.progress_line(rounds));
                }
            })
        });
        // stops the reporter when prove_classes returns or panics, so the
        // scope's join never waits out a park
        struct Stop<'a>(&'a std::sync::atomic::AtomicBool, Option<std::thread::Thread>);
        impl Drop for Stop<'_> {
            fn drop(&mut self) {
                self.0.store(true, std::sync::atomic::Ordering::Relaxed);
                if let Some(t) = &self.1 {
                    t.unpark();
                }
            }
        }
        let _stop = Stop(&finished, reporter.as_ref().map(|h| h.thread().clone()));
        prove_classes(&s, data, rounds, only)
    })
}

fn prove_classes(s: &search::Search, data: &data::Data, rounds: u8, only: Option<&str>) -> i32 {
    let collect = std::env::var("COLLECT").is_ok();
    let t0 = Instant::now();
    let empty = Cells::EMPTY;
    let mut seen = std::collections::HashSet::new();
    // geometric classes keep the established numbering (class 4 is cell 8);
    // the full group would merge them into the three orbits
    let firsts: Vec<usize> = (0..bits::CELLS).filter(|&m| seen.insert(data.canonical_geometric(&empty.with(m), &empty))).collect();
    println!("{} first-move classes; rounds {rounds}, width {}{}", firsts.len(), s.width, if collect { ", collect mode" } else { "" });
    let mut worst = search::Outcome::Proven;
    let pick: Option<Vec<usize>> = only.map(|s| {
        s.split(',')
            .map(|t| match t.parse() {
                Ok(i) if i < firsts.len() => i,
                _ => usage_exit(&format!("class {t} is not one of 0..{}", firsts.len())),
            })
            .collect()
    });
    for (i, m) in firsts.into_iter().enumerate() {
        if pick.as_ref().is_some_and(|p| !p.contains(&i)) {
            continue;
        }
        let t = Instant::now();
        let o = s.breaker_node(&empty.with(m), &empty, rounds);
        worst = worst.max(o);
        let word = match o {
            search::Outcome::Proven => "HOLDS",
            search::Outcome::Pending => "PENDING (holds once the pending leaves are certified)",
            search::Outcome::Failed => "not proven",
        };
        println!("first move {m:3}: {word}  ({:.1}s, {})", t.elapsed().as_secs_f64(), s.progress_line(rounds));
    }
    let all = worst == search::Outcome::Proven;
    let mut code = if all { 0 } else { 1 };
    if let Ok(path) = std::env::var("PROOF") {
        match s.write_proof(&path) {
            Ok(n) => println!("wrote {n} proof records to {path}"),
            Err(e) => {
                eprintln!("writing {path}: {e}");
                code = 2;
            }
        }
    }
    // "not proven" means this bounded search found no strategy, not that Maker wins
    let verdict = match worst {
        search::Outcome::Proven => "",
        search::Outcome::Pending => "pending",
        search::Outcome::Failed => "not proven",
    };
    println!("{} in {:.1}s", if !all { verdict } else if pick.is_some() { "all selected classes HOLD (not every class was run)" } else { "BREAKER WINS (all first moves)" }, t0.elapsed().as_secs_f64());
    code
}
