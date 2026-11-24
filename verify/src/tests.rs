//! Unit tests: group structure, block games, certificate mutations, and a
//! small end-to-end proof.

use crate::block::Solver;
use crate::cert::{check_cert, Block, Cert, CertStats};
use crate::geometry::{Geometry, Set, CELLS, GROUP_SIZE, LINES};
use crate::parse;
use crate::verify::{build_index, used_records, Verifier};

#[test]
fn line_count_and_group() {
    let geo = Geometry::new(); // asserts |G| = 1152 and closure
    assert_eq!(geo.lines.len(), LINES);
    assert_eq!(geo.group.len(), GROUP_SIZE);
    assert!(geo.lines.iter().all(|l| l.len() == 6));
}

#[test]
fn first_move_orbits() {
    let geo = Geometry::new();
    let orbits = geo.orbits();
    let sizes: Vec<usize> = orbits.iter().map(Vec::len).collect();
    assert_eq!(sizes, vec![24, 144, 48]);
    let reps = [0usize, 1, 2, 7, 8, 14, 43, 44, 50, 86];
    let mut by_orbit: Vec<Vec<usize>> = vec![vec![]; orbits.len()];
    for (i, r) in reps.iter().enumerate() {
        by_orbit[orbits.iter().position(|o| o.contains(r)).unwrap()].push(i);
    }
    assert_eq!(by_orbit, vec![vec![0, 6, 9], vec![1, 2, 3, 5, 7, 8], vec![4]]);
}

#[test]
fn canonical_form_is_orientation_independent() {
    let geo = Geometry::new();
    let (m, b) = (Set::from_cells(&[0, 40, 100]), Set::from_cells(&[7, 90]));
    let (cm, cb, _) = geo.canonical(m, b);
    for g in geo.group.iter().step_by(37) {
        let (m2, b2) = (crate::geometry::apply_map(g, m), crate::geometry::apply_map(g, b));
        assert_eq!(geo.canonical(m2, b2).0, cm);
        assert_eq!(geo.canonical(m2, b2).1, cb);
    }
}

/// A position where few lines are live: Breaker marks from a greedy hitting
/// set, stopped early. Returns (B, the live lines).
fn nearly_hit(geo: &Geometry) -> (Set, Vec<usize>) {
    let mut b = Set::default();
    loop {
        let live: Vec<usize> = (0..geo.lines.len()).filter(|&i| geo.lines[i].inter(b).is_empty()).collect();
        if live.len() <= 6 {
            return (b, live);
        }
        let best = (0..CELLS).max_by_key(|&c| live.iter().filter(|&&i| geo.lines[i].has(c)).count()).unwrap();
        b = b.with(best);
    }
}

/// Valid certificate for `nearly_hit`: one pair of free cells per live line.
fn pair_cert(geo: &Geometry, b: Set, live: &[usize]) -> Cert {
    let mut used = b;
    let mut pairs = vec![];
    for &li in live {
        let free: Vec<usize> = geo.lines[li].to_vec().into_iter().filter(|&c| !used.has(c)).collect();
        pairs.push((free[0], free[1]));
        used = used.with(free[0]).with(free[1]);
    }
    Cert { blocks: vec![], pairs }
}

fn check(geo: &Geometry, b: Set, cert: &Cert) -> Result<(), String> {
    check_cert(geo, &mut Solver::default(), &mut CertStats::default(), Set::default(), b, cert)
}

#[test]
fn valid_certificate_is_accepted() {
    let geo = Geometry::new();
    let (b, live) = nearly_hit(&geo);
    assert!(!live.is_empty());
    check(&geo, b, &pair_cert(&geo, b, &live)).unwrap();
}

#[test]
fn corrupted_certificates_are_rejected() {
    let geo = Geometry::new();
    let (b, live) = nearly_hit(&geo);
    let good = pair_cert(&geo, b, &live);
    assert!(live.len() >= 2);

    // overlapping pair: the second pair reuses a cell of the first
    let mut c = good.clone();
    c.pairs[1].0 = c.pairs[0].0;
    assert!(check(&geo, b, &c).unwrap_err().contains("overlaps"));

    // uncovered live line
    let mut c = good.clone();
    c.pairs.pop();
    assert!(check(&geo, b, &c).unwrap_err().contains("not covered"));

    // fake line: two cells that share no line
    let mut c = good.clone();
    let (a, d) = (0..CELLS)
        .flat_map(|a| (0..CELLS).map(move |d| (a, d)))
        .find(|&(a, d)| a != d && !b.has(a) && !b.has(d) && geo.line_through(a, d).is_none() && !good.pairs.iter().any(|&(p, q)| [p, q].contains(&a) || [p, q].contains(&d)))
        .unwrap();
    c.pairs[0] = (a, d);
    assert!(check(&geo, b, &c).unwrap_err().contains("not on a line"));

    // pair on a marked cell
    let mut c = good.clone();
    c.pairs[0].0 = b.to_vec()[0];
    assert!(check(&geo, b, &c).is_err());
}

#[test]
fn block_certificates() {
    let geo = Geometry::new();
    let (b, live) = nearly_hit(&geo);
    // Turn the first pair into a two-cell block claiming the same line.
    let mut cert = pair_cert(&geo, b, &live);
    let (x, y) = cert.pairs.remove(0);
    cert.blocks.push(Block { cells: Set::from_cells(&[x, y]), lines: vec![(x, y)] });
    check(&geo, b, &cert).unwrap();

    // A claimed line with a cell outside the block is rejected.
    let mut bad = cert.clone();
    bad.blocks[0].cells = Set::from_cells(&[x]);
    assert!(check(&geo, b, &bad).unwrap_err().contains("outside the block"));

    // A block over a whole line leaves the other live lines uncovered.
    let l = geo.lines[live[0]].to_vec();
    let mut bad = cert.clone();
    bad.blocks[0] = Block { cells: Set::from_cells(&l), lines: vec![(l[0], l[1])] };
    bad.pairs.clear();
    assert!(check(&geo, b, &bad).unwrap_err().contains("not covered"));
}

#[test]
fn maker_owned_edge_in_block_is_rejected() {
    let geo = Geometry::new();
    let (b, live) = nearly_hit(&geo);
    let l = geo.lines[live[0]];
    let mut cert = pair_cert(&geo, b, &live);
    cert.pairs.remove(0);
    cert.blocks.push(Block { cells: l, lines: vec![(l.to_vec()[0], l.to_vec()[1])] });
    // With Maker owning the whole line, the block game is lost at the root.
    let err = check_cert(&geo, &mut Solver::default(), &mut CertStats::default(), l, b, &cert);
    assert!(err.unwrap_err().contains("not a Breaker win"));
}

/// An end-to-end run on a toy "proof": the verifier must reject a file that
/// lacks the records for some first move.
#[test]
fn full_check_rejects_missing_records() {
    let geo = Geometry::new();
    let records = parse::file("R | 0 | - | 1\n").unwrap();
    let index = build_index(&geo, &records);
    let mut v = Verifier::new(&geo, &records, &index);
    let err = v.check_root(&[0]).unwrap_err();
    assert!(err.contains("no record"), "{err}");
    let mut v = Verifier::new(&geo, &records, &index);
    assert!(v.check_root(&[5]).is_err());
}

/// `--emit-used` keeps the first record of each reached position and drops
/// duplicates and records the walk never reaches. Certificates are empty
/// here: `used_records` follows the tree and checks nothing.
#[test]
fn used_records_keep_one_record_per_reached_position() {
    let geo = Geometry::new();
    let mut text = String::from("R | 0 | - | 129\nR | 0 | - | 129\n");
    let mut seen = std::collections::HashSet::new();
    let mut leaves = 0;
    for c in (1..CELLS).filter(|&c| c != 129) {
        let (m, b) = (Set::from_cells(&[0, c]), Set::from_cells(&[129]));
        let (cm, cb, _) = geo.canonical(m, b);
        if seen.insert((cm, cb)) {
            let r = (1..CELLS).find(|&x| x != c && x != 129).unwrap();
            text += &format!("L | {} | 129 | {r} | - | -\n", m.show());
            leaves += 1;
        }
    }
    let last = text.lines().last().unwrap().to_string();
    text += &format!("{last}\nL | 1,2 | 3 | 4 | - | -\n"); // a duplicate leaf, then one never reached
    let records = parse::file(&text).unwrap();
    let index = build_index(&geo, &records);
    let used = used_records(&geo, &records, &index, &geo.orbit(0).to_vec()).unwrap();
    let want: Vec<usize> = std::iter::once(0).chain(2..2 + leaves).collect();
    assert_eq!(used, want);
}

/// A hand-built v2 file: one R record and one leaf whose layout has no
/// blocks, so the decoder must rebuild a pairing for every live line.
#[test]
fn v2_leaf_decodes_to_a_valid_certificate() {
    let geo = Geometry::new();
    let (b, live) = nearly_hit(&geo);
    let bc = b.to_vec();
    let n = bc.len();
    let on_live = |c: usize| live.iter().any(|&l| geo.lines[l].has(c));
    let off: Vec<usize> = (0..CELLS).filter(|&c| !b.has(c) && !on_live(c)).take(n).collect();
    let (m_r, mv) = (&off[..n - 1], off[n - 1]);
    let mut data = crate::v2::MAGIC.to_vec();
    for v in [0u32, 1, 1, 1] {
        data.extend(v.to_le_bytes()); // header bytes, layouts, R records, leaves
    }
    data.push(2); // layout id width
    data.push(0); // layout 0: no blocks
    data.push(m_r.len() as u8);
    data.extend(m_r.iter().map(|&c| c as u8));
    data.push((n - 2) as u8);
    data.extend(bc[..n - 2].iter().map(|&c| c as u8));
    data.extend([bc[n - 2] as u8, 1, mv as u8, bc[n - 1] as u8, 0, 0, 0, 0]);
    let records = crate::v2::records(&data, &geo).unwrap();
    assert_eq!(records.len(), 2);
    let leaf = &records[1];
    assert_eq!((leaf.m, leaf.reply), (Set::from_cells(m_r).with(mv), bc[n - 1]));
    let cert = leaf.cert.as_ref().unwrap();
    assert_eq!(cert.pairs.len(), live.len());
    check_cert(&geo, &mut Solver::default(), &mut CertStats::default(), leaf.m, leaf.b.with(leaf.reply), cert).unwrap();

    // a truncated file and a bad symmetry index are errors, not panics
    assert!(crate::v2::records(&data[..data.len() - 1], &geo).is_err());
    let mut bad = data.clone();
    let at = bad.len() - 1;
    bad[at] = 0xff;
    assert!(crate::v2::records(&bad, &geo).unwrap_err().contains("symmetry index"));
}
