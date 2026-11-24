//! Re-check and analysis of the 7x7x7 Maker-Breaker proof in Cain, Raymond,
//! and Kallersjo, "Cubic tic-tac-toe: A matching-based approach"
//! (arXiv:2509.21494, v1). Their code (tic-tac-toe-code.tar.gz) covers only
//! the center opening; the off-center case follows the paper's section 4.3.
//!
//! Modes:
//!   seven center            section 4.2: all 22,163,142 positions after 4 rounds
//!   seven offcenter         section 4.3: all 12,824,370 positions after 3 rounds
//!   seven gap               openings the section 4.3 symmetry step misses, and a fix
//!   seven sample <n> <seed> exact pairing surplus on random positions of both cases
//!   seven anymove <n> <seed> every third and fourth Breaker move the paper's text allows
//!   seven cover <file>      check a static cover of the whole board (blocks and pairs, no opening)
//!
//! Run with `cargo run --release -- <mode>`; `THREADS` sets the worker count.

mod board;
mod cover;
mod pairing;

use board::*;
use pairing::Matcher;
use std::sync::atomic::{AtomicUsize, Ordering};
use std::sync::Mutex;

fn p(abc: usize) -> usize {
    paper_cell(abc)
}

/// Statistics gathered over a family of positions.
#[derive(Default, Clone)]
struct Stats {
    positions: u64,
    failures: u64,
    invalid: u64,
    failure_examples: Vec<String>,
    survivor_counts: std::collections::BTreeMap<usize, u64>,
    /// Positions with a nonempty tight set (one more Maker mark there would break every pairing).
    tight: u64,
    tight_size: std::collections::BTreeMap<usize, u64>,
    /// How often each board line is in the tight set.
    tight_line: Vec<u64>,
    /// Free cells on no surviving line, per position.
    idle_cells: std::collections::BTreeMap<usize, u64>,
}

impl Stats {
    fn merge(&mut self, o: &Stats) {
        self.positions += o.positions;
        self.failures += o.failures;
        self.invalid += o.invalid;
        for e in &o.failure_examples {
            if self.failure_examples.len() < 20 {
                self.failure_examples.push(e.clone());
            }
        }
        for (k, v) in &o.survivor_counts {
            *self.survivor_counts.entry(*k).or_default() += v;
        }
        self.tight += o.tight;
        for (k, v) in &o.tight_size {
            *self.tight_size.entry(*k).or_default() += v;
        }
        if self.tight_line.is_empty() {
            self.tight_line = vec![0; LINE_COUNT];
        }
        for (i, v) in o.tight_line.iter().enumerate() {
            self.tight_line[i] += v;
        }
        for (k, v) in &o.idle_cells {
            *self.idle_cells.entry(*k).or_default() += v;
        }
    }

    fn record(&mut self, board: &Board, m: &mut Matcher, maker: &[usize], breaker: &[usize]) {
        if self.tight_line.is_empty() {
            self.tight_line = vec![0; LINE_COUNT];
        }
        self.positions += 1;
        m.load(board, maker, breaker);
        *self.survivor_counts.entry(m.survivors.len()).or_default() += 1;
        let missing = m.solve();
        if missing > 0 {
            self.failures += 1;
            if self.failure_examples.len() < 20 {
                self.failure_examples.push(format!(
                    "maker {:?} breaker {:?}: {} slots unmatched",
                    maker.iter().map(|&c| paper_name(c)).collect::<Vec<_>>(),
                    breaker.iter().map(|&c| paper_name(c)).collect::<Vec<_>>(),
                    missing
                ));
            }
            return;
        }
        if !m.validate(board, maker, breaker) {
            self.invalid += 1;
            return;
        }
        let tight = m.tight_lines(board);
        if !tight.is_empty() {
            self.tight += 1;
            for &l in &tight {
                self.tight_line[l] += 1;
            }
        }
        *self.tight_size.entry(tight.len()).or_default() += 1;
        let mut on_line = [false; CELLS];
        for f in &m.free {
            for &c in f {
                on_line[c] = true;
            }
        }
        let occupied: Vec<usize> = maker.iter().chain(breaker).copied().collect();
        let idle = (0..CELLS).filter(|&c| !on_line[c] && !occupied.contains(&c)).count();
        *self.idle_cells.entry(idle).or_default() += 1;
    }

    fn report(&self, title: &str, board: &Board) {
        println!("== {title}");
        println!("positions        {}", self.positions);
        println!("no pairing       {}", self.failures);
        println!("invalid pairing  {}", self.invalid);
        for e in &self.failure_examples {
            println!("  FAIL {e}");
        }
        println!("survivor counts  {:?}", self.survivor_counts);
        println!("idle free cells  {:?}", self.idle_cells);
        println!(
            "tight positions  {} ({:.3}%)",
            self.tight,
            100.0 * self.tight as f64 / self.positions.max(1) as f64
        );
        println!("tight-set sizes  {:?}", self.tight_size);
        if self.tight > 0 {
            let mut by_kind = [0u64; 3];
            for (i, &v) in self.tight_line.iter().enumerate() {
                by_kind[board.kind[i] as usize] += v;
            }
            println!("tight lines by kind (axis, face diagonal, space diagonal): {:?}", by_kind);
            let mut top: Vec<(u64, usize)> = self.tight_line.iter().enumerate().map(|(i, &v)| (v, i)).collect();
            top.sort_unstable_by(|a, b| b.cmp(a));
            for &(v, i) in top.iter().take(12) {
                if v == 0 {
                    break;
                }
                let cells: Vec<usize> = board.lines[i].iter().map(|&c| paper_name(c)).collect();
                println!("  {:>9} {:?} {:?}", v, board.kind[i], cells);
            }
        }
    }
}

fn threads() -> usize {
    std::env::var("THREADS")
        .ok()
        .and_then(|s| s.parse().ok())
        .unwrap_or_else(|| std::thread::available_parallelism().map(|n| n.get()).unwrap_or(4))
}

/// Run `job(index, stats, matcher)` for every index in 0..count on all threads.
fn parallel<F>(count: usize, job: F) -> Stats
where
    F: Fn(usize, &mut Stats, &mut Matcher) + Sync,
{
    let next = AtomicUsize::new(0);
    let total = Mutex::new(Stats::default());
    std::thread::scope(|s| {
        for _ in 0..threads() {
            s.spawn(|| {
                let mut st = Stats::default();
                let mut m = Matcher::new();
                loop {
                    let i = next.fetch_add(1, Ordering::Relaxed);
                    if i >= count {
                        break;
                    }
                    job(i, &mut st, &mut m);
                }
                total.lock().unwrap().merge(&st);
            });
        }
    });
    total.into_inner().unwrap()
}

// ---------------------------------------------------------------------------
// Section 4.2: Maker opens at the center (code: starting-moves.C, driver.C).

/// Maker's second moves in the paper's frame: (a, b, c) with a <= b, not 444 or 555.
fn center_second_moves() -> Vec<usize> {
    let mut v = Vec::new();
    for a in 1..=7 {
        for b in a..=7 {
            for c in 1..=7 {
                let m2 = p(100 * a + 10 * b + c);
                if m2 != p(444) && m2 != p(555) {
                    v.push(m2);
                }
            }
        }
    }
    v
}

/// Breaker's third move (starting-moves.C): 117, else 771; 177 if Maker holds both.
fn center_b3(m2: usize, m3: usize) -> usize {
    let held = |c: usize| m2 == c || m3 == c;
    if held(p(117)) && held(p(771)) {
        p(177)
    } else if !held(p(117)) {
        p(117)
    } else {
        p(771)
    }
}

/// Breaker's fourth move: the first free of 177, 711, 622, 266 (superdiagonal C);
/// in the rare case (b3 = 177), 226 or else 662 on superdiagonal D.
fn center_b4(b3: usize, m: [usize; 3]) -> usize {
    let held = |c: usize| m.contains(&c);
    if b3 == p(177) {
        return if held(p(226)) { p(662) } else { p(226) };
    }
    for c in [177, 711, 622, 266] {
        if !held(p(c)) {
            return p(c);
        }
    }
    unreachable!("Maker holds only three of the four candidates")
}

fn run_center(board: &Board) {
    let seconds = center_second_moves();
    assert_eq!(seconds.len(), 194);
    // The symmetry step: some rotation about superdiagonal A (cyclic shift of
    // coordinates, which fixes 444 and 555) maps every second move into the frame.
    let in_frame = |c: usize| {
        let [x, y, _] = coords(c);
        x <= y
    };
    for c in 0..CELLS {
        if c == p(444) || c == p(555) {
            continue;
        }
        let [x, y, z] = coords(c);
        assert!(
            [cell(x, y, z), cell(y, z, x), cell(z, x, y)].iter().any(|&r| in_frame(r)),
            "second move {} has no rotation into the frame",
            paper_name(c)
        );
    }
    let stats = parallel(seconds.len(), |i, st, m| {
        let m2 = seconds[i];
        let (m1, b1, b2) = (p(444), p(555), p(626));
        for m3 in 0..CELLS {
            if [m1, b1, m2, b2].contains(&m3) {
                continue;
            }
            let b3 = center_b3(m2, m3);
            for m4 in 0..CELLS {
                if [m1, b1, m2, b2, m3, b3].contains(&m4) {
                    continue;
                }
                let b4 = center_b4(b3, [m2, m3, m4]);
                st.record(board, m, &[m1, m2, m3, m4], &[b1, b2, b3, b4]);
            }
        }
    });
    stats.report("center opening (section 4.2), after 4 rounds", board);
}

// ---------------------------------------------------------------------------
// Section 4.3: Maker opens elsewhere; Breaker takes the center.

/// Cells with first coordinate at most 4 (paper notation), the "half cube".
fn in_half(c: usize) -> bool {
    coords(c)[0] <= 3
}

/// Breaker's third move in section 4.3: 626, or 717 if Maker holds 626.
fn offcenter_b3(maker: &[usize]) -> Option<usize> {
    [p(626), p(717)].into_iter().find(|c| !maker.contains(c))
}

fn run_offcenter(board: &Board) {
    let firsts: Vec<usize> = (0..CELLS).filter(|&c| in_half(c) && c != CENTER).collect();
    assert_eq!(firsts.len(), 195);
    let stats = parallel(firsts.len(), |i, st, m| {
        let m1 = firsts[i];
        let (b1, b2) = (p(444), p(555));
        for m2 in 0..CELLS {
            if !in_half(m2) || m2 == b1 || m2 == m1 {
                continue;
            }
            for m3 in 0..CELLS {
                if [m1, b1, m2, b2].contains(&m3) {
                    continue;
                }
                let b3 = offcenter_b3(&[m1, m2, m3]).expect("626 and 717 cannot both be Maker's here");
                st.record(board, m, &[m1, m2, m3], &[b1, b2, b3]);
            }
        }
    });
    stats.report("off-center opening (section 4.3), after 3 rounds", board);
}

// ---------------------------------------------------------------------------
// The section 4.3 symmetry step ("rotating the cube if necessary, ... Maker's
// first and second moves are in the half cube") needs one symmetry putting
// both moves in the half. Find the openings where none exists.

fn pairing_exists(board: &Board, m: &mut Matcher, maker: &[usize], breaker: &[usize]) -> bool {
    m.load(board, maker, breaker);
    m.solve() == 0 && m.validate(board, maker, breaker)
}

fn run_gap(board: &Board) {
    let syms = symmetries();
    let mut missed = Vec::new();
    let mut ordered = 0usize;
    for m1 in 0..CELLS {
        for m2 in 0..CELLS {
            if m1 == CENTER || m2 == CENTER || m1 == m2 {
                continue;
            }
            ordered += 1;
            if !syms.iter().any(|g| in_half(g[m1]) && in_half(g[m2])) {
                missed.push((m1, m2));
            }
        }
    }
    println!("== section 4.3 symmetry step");
    println!("ordered openings (Maker's first two moves, Breaker at the center): {ordered}");
    println!("openings no symmetry puts in the half cube: {}", missed.len());
    // Characterize: centered coordinates u, v with u_i * v_i < 0 for every i.
    let centered = |c: usize| coords(c).map(|t| t as i32 - 3);
    let all_opposite = missed.iter().all(|&(a, b)| {
        let (u, v) = (centered(a), centered(b));
        (0..3).all(|i| u[i] * v[i] < 0)
    });
    let count_opposite = (0..CELLS)
        .flat_map(|a| (0..CELLS).map(move |b| (a, b)))
        .filter(|&(a, b)| {
            let (u, v) = (centered(a), centered(b));
            (0..3).all(|i| u[i] * v[i] < 0)
        })
        .count();
    println!("all of them have opposite signs in every centered coordinate: {all_opposite} ({count_opposite} such ordered pairs)");

    // Classes up to the 48 symmetries.
    let mut classes: Vec<(usize, usize)> = Vec::new();
    let mut seen = std::collections::HashSet::new();
    for &(a, b) in &missed {
        let key = syms.iter().map(|g| (g[a], g[b])).min().unwrap();
        if seen.insert(key) {
            classes.push(key);
        }
    }
    println!("classes up to symmetry: {}", classes.len());

    // (1) The paper's own moves, read as kindly as possible: try every frame
    // that puts Maker's first move in the half, Breaker plays 555 and then
    // 626 or 717, and see whether some frame works for every third move.
    let mut m = Matcher::new();
    let (mut kind_ok, mut kind_bad) = (0, 0);
    let mut bad_examples = Vec::new();
    for &(a, b) in &classes {
        let mut some_frame = false;
        for g in &syms {
            let (m1, m2) = (g[a], g[b]);
            if !in_half(m1) || m2 == p(555) {
                continue;
            }
            let mut all = true;
            for m3 in 0..CELLS {
                if [m1, m2, CENTER, p(555)].contains(&m3) {
                    continue;
                }
                let maker = [m1, m2, m3];
                let Some(b3) = offcenter_b3(&maker) else { all = false; break };
                if !pairing_exists(board, &mut m, &maker, &[CENTER, p(555), b3]) {
                    all = false;
                    break;
                }
            }
            if all {
                some_frame = true;
                break;
            }
        }
        if some_frame {
            kind_ok += 1;
        } else {
            kind_bad += 1;
            if bad_examples.len() < 10 {
                bad_examples.push((paper_name(a), paper_name(b)));
            }
        }
    }
    println!("paper's moves (555, then 626 or 717) work in some frame: {kind_ok} classes; in no frame: {kind_bad}");
    for (a, b) in &bad_examples {
        println!("  no frame works: Maker {a} then {b}");
    }

    // (1b) A simple wording of the fix: any orientation that puts Maker's
    // first move in the half cube and his second move off 555, 626, and 717.
    // Then 555 is free, 626 or 717 stays free for Breaker's third move, and
    // the paper's moves are defined. Check every such orientation.
    let reserved = [p(555), p(626), p(717)];
    let (mut frames, mut frames_ok, mut classes_with_frame, mut positions) = (0, 0, 0, 0u64);
    let mut frame_failures = Vec::new();
    for &(a, b) in &classes {
        let mut any = false;
        for g in &syms {
            let (m1, m2) = (g[a], g[b]);
            if !in_half(m1) || reserved.contains(&m2) {
                continue;
            }
            any = true;
            frames += 1;
            let mut all = true;
            for m3 in 0..CELLS {
                if [m1, m2, CENTER, p(555)].contains(&m3) {
                    continue;
                }
                let maker = [m1, m2, m3];
                let b3 = offcenter_b3(&maker).expect("m2 avoids 626 and 717");
                positions += 1;
                if !pairing_exists(board, &mut m, &maker, &[CENTER, p(555), b3]) {
                    all = false;
                    if frame_failures.len() < 10 {
                        frame_failures.push((paper_name(m1), paper_name(m2), paper_name(m3)));
                    }
                }
            }
            if all {
                frames_ok += 1;
            }
        }
        if any {
            classes_with_frame += 1;
        }
    }
    println!(
        "orientations with Maker's first move in the half and his second off 555, 626, 717: \
         {classes_with_frame} of {} classes have one; {frames_ok} of {frames} such orientations pass \
         ({positions} positions checked)",
        classes.len()
    );
    for (a, b, c) in &frame_failures {
        println!("  no pairing: Maker {a}, {b}, {c}");
    }

    // (2) A fix found by search: a second Breaker move that works for every
    // third Maker move with some third Breaker move. Space-diagonal cells first.
    let diag: Vec<usize> = (0..CELLS)
        .filter(|&c| {
            let u = centered(c);
            c != CENTER && u[0].abs() == u[1].abs() && u[1].abs() == u[2].abs()
        })
        .collect();
    let mut order: Vec<usize> = diag.clone();
    order.extend((0..CELLS).filter(|c| !diag.contains(c)));
    let mut fixed = 0;
    let mut unfixed = Vec::new();
    for &(a, b) in &classes {
        let mut found = None;
        for &b2 in &order {
            if [a, b, CENTER].contains(&b2) {
                continue;
            }
            let ok = (0..CELLS).all(|m3| {
                if [a, b, CENTER, b2].contains(&m3) {
                    return true;
                }
                order.iter().any(|&b3| {
                    ![a, b, m3, CENTER, b2].contains(&b3)
                        && pairing_exists(board, &mut m, &[a, b, m3], &[CENTER, b2, b3])
                })
            });
            if ok {
                found = Some(b2);
                break;
            }
        }
        match found {
            Some(b2) => {
                fixed += 1;
                println!("  Maker {} then {}: Breaker {} works", paper_name(a), paper_name(b), paper_name(b2));
            }
            None => unfixed.push((paper_name(a), paper_name(b))),
        }
    }
    println!("classes fixed by a second Breaker move found by search: {fixed}; not fixed: {}", unfixed.len());
    for (a, b) in &unfixed {
        println!("  NOT FIXED: Maker {a} then {b}");
    }
}

// ---------------------------------------------------------------------------

struct Rng(u64);
impl Rng {
    fn next(&mut self) -> u64 {
        self.0 ^= self.0 << 13;
        self.0 ^= self.0 >> 7;
        self.0 ^= self.0 << 17;
        self.0
    }
    fn below(&mut self, n: usize) -> usize {
        (self.next() % n as u64) as usize
    }
}

fn run_sample(board: &Board, n: usize, seed: u64) {
    let mut rng = Rng(seed.max(1));
    let mut m = Matcher::new();
    let seconds = center_second_moves();
    let mut hist_center = std::collections::BTreeMap::new();
    let mut hist_off = std::collections::BTreeMap::new();
    let cap = 6;
    for _ in 0..n {
        // Center case.
        let (m1, b1, b2) = (p(444), p(555), p(626));
        let m2 = seconds[rng.below(seconds.len())];
        let m3 = loop {
            let c = rng.below(CELLS);
            if ![m1, b1, m2, b2].contains(&c) {
                break c;
            }
        };
        let b3 = center_b3(m2, m3);
        let m4 = loop {
            let c = rng.below(CELLS);
            if ![m1, b1, m2, b2, m3, b3].contains(&c) {
                break c;
            }
        };
        let b4 = center_b4(b3, [m2, m3, m4]);
        let (maker, breaker) = ([m1, m2, m3, m4], [b1, b2, b3, b4]);
        assert!(pairing_exists(board, &mut m, &maker, &breaker));
        *hist_center.entry(m.surplus(cap)).or_insert(0u64) += 1;

        // Off-center case.
        let half: Vec<usize> = (0..CELLS).filter(|&c| in_half(c) && c != CENTER).collect();
        let m1 = half[rng.below(half.len())];
        let m2 = loop {
            let c = half[rng.below(half.len())];
            if c != m1 {
                break c;
            }
        };
        let m3 = loop {
            let c = rng.below(CELLS);
            if ![m1, m2, CENTER, p(555)].contains(&c) {
                break c;
            }
        };
        let maker = [m1, m2, m3];
        let breaker = [CENTER, p(555), offcenter_b3(&maker).unwrap()];
        assert!(pairing_exists(board, &mut m, &maker, &breaker));
        *hist_off.entry(m.surplus(cap)).or_insert(0u64) += 1;
    }
    println!("== exact surplus (extra Maker marks a pairing survives), {n} random positions each");
    println!("center opening, after 4 rounds:      {:?}", hist_center);
    println!("off-center opening, after 3 rounds:  {:?}", hist_off);
}

/// The paper's text (section 4.2, Step 1) is looser than its code: Breaker's
/// third move is "such a corner cell lying on one of these two
/// superdiagonals" and the fourth "any unoccupied cell along whichever
/// superdiagonal ... they have not yet occupied". The code fixes one choice.
/// On random positions, try every choice the text allows.
fn run_anymove(board: &Board, n: usize, seed: u64) {
    let mut rng = Rng(seed.max(1));
    let mut m = Matcher::new();
    let seconds = center_second_moves();
    let diag_c = [177, 266, 355, 533, 622, 711].map(p); // superdiagonal C, center left out
    let diag_d = [117, 226, 335, 553, 662, 771].map(p); // superdiagonal D
    let corners = [p(711), p(177), p(771), p(117)];
    let (mut tried, mut failed) = (0u64, 0u64);
    let mut examples = Vec::new();
    for _ in 0..n {
        let (m1, b1, b2) = (p(444), p(555), p(626));
        let m2 = seconds[rng.below(seconds.len())];
        let m3 = loop {
            let c = rng.below(CELLS);
            if ![m1, b1, m2, b2].contains(&c) {
                break c;
            }
        };
        for &b3 in &corners {
            if [m2, m3].contains(&b3) {
                continue;
            }
            let other: &[usize] = if diag_c.contains(&b3) { &diag_d } else { &diag_c };
            let m4 = loop {
                let c = rng.below(CELLS);
                if ![m1, b1, m2, b2, m3, b3].contains(&c) {
                    break c;
                }
            };
            for &b4 in other {
                if [m2, m3, m4].contains(&b4) {
                    continue;
                }
                tried += 1;
                let (maker, breaker) = ([m1, m2, m3, m4], [b1, b2, b3, b4]);
                if !pairing_exists(board, &mut m, &maker, &breaker) {
                    failed += 1;
                    if examples.len() < 10 {
                        examples.push(format!(
                            "maker {:?} breaker {:?}",
                            maker.map(paper_name),
                            breaker.map(paper_name)
                        ));
                    }
                }
            }
        }
    }
    println!("== every third and fourth move the paper's text allows (center opening), {n} random openings");
    println!("positions tried {tried}, without a pairing {failed}");
    for e in &examples {
        println!("  FAIL {e}");
    }
}

fn main() {
    let board = Board::new();
    let args: Vec<String> = std::env::args().collect();
    let t = std::time::Instant::now();
    match args.get(1).map(|s| s.as_str()) {
        Some("center") => run_center(&board),
        Some("offcenter") => run_offcenter(&board),
        Some("gap") => run_gap(&board),
        Some("cover") => {
            let path = args.get(2).expect("usage: seven cover <cover.txt>");
            if let Err(e) = cover::run(&board, path) {
                println!("COVER FAILED: {e}");
                std::process::exit(1);
            }
        }
        Some("anymove") => {
            let n = args.get(2).and_then(|s| s.parse().ok()).unwrap_or(10_000);
            let seed = args.get(3).and_then(|s| s.parse().ok()).unwrap_or(1);
            run_anymove(&board, n, seed)
        }
        Some("sample") => {
            let n = args.get(2).and_then(|s| s.parse().ok()).unwrap_or(10_000);
            let seed = args.get(3).and_then(|s| s.parse().ok()).unwrap_or(1);
            run_sample(&board, n, seed)
        }
        _ => {
            eprintln!("usage: seven center | offcenter | gap | sample <n> <seed> | anymove <n> <seed> | cover <file>");
            std::process::exit(2);
        }
    }
    eprintln!("time {:.1} s", t.elapsed().as_secs_f64());
}
