# verify_py: independent proof checker

`check_cube6.py` checks a proof file in the format of `docs/proof-format.md`
(Breaker wins 6x6x6 Maker-Breaker). It was written from that document alone,
without reading `src/`, `verify/`, `gen/`, or any other file in the repo, so a
bug would have to appear in two separately written programs to slip through.
It builds the 148 lines, the symmetry group, and the block-game minimax
itself and trusts nothing in the proof file beyond its records.

Python 3 with numpy only.

## Usage

    python check_cube6.py proof.txt [more.txt ...]   # whole game: PROOF OK
    python check_cube6.py proof.txt --root CELL      # first move CELL only: ROOT ORBIT OK (not a proof)
    python check_cube6.py --selftest                 # hand-built cases that must fail, and one that must pass
    python test_mutations.py                         # 20 real leaves (leaves20.txt) pass; 140 corruptions fail

On failure it prints `FAIL: <reason>` with the record (`file:line`), the
position (`M`, `B`), Maker's move, and Breaker's reply, and exits 1. Every
run ends with the counts: records read, Maker nodes checked, leaves checked,
distinct block games solved, seconds, and peak RSS (Linux).

How it works: one streaming pass indexes every record by the canonical form
of its position under G (the least 2-bit-per-cell packing over all 1,152
maps, vectorized in numpy) and keeps only its file offset and the map. The
tree walk canonicalizes each child position the same way, re-reads the
record, derives the map `s` from record to position, and re-checks that
`s(M') = M + m` and `s(B') = B` before using it. Maker nodes and matched
positions are memoized by canonical form; block games by their abstract game
(below).

## Judgment calls about the spec

Where the spec was ambiguous, the stricter reading was taken.

1. **Group.** Built exactly as described: 6 * 8 * 720 candidates, kept when
   all 148 lines map to lines. 2,304 candidate tuples pass, using exactly the
   48 value permutations that commute with `c -> 5 - c`; they give 1,152
   distinct maps (reflecting all three axes equals composing `t` with
   `c -> 5 - c`), so duplicates are dropped before the assert. Asserted: 1,152
   maps, identity present, closed under composition (all 1,152^2 products).
2. **Duplicate records.** When several records have the same position up to
   G, the first in file order is used and the rest are ignored (counted in
   the output). If that first record is bad the check fails, even if a later
   duplicate would have passed. With `--all-records` (for
   the rule-following proof, whose strategy needs several records for some
   positions) every record of a reached position is walked, as `verify/`
   does.
3. **Unreached records.** Every record's kind, field count, `M`, `B`, and
   `r` are parsed and validated at load (ids 0..215 without leading zeros,
   strictly increasing sets, `|M| = |B| + 1`, `M` and `B` disjoint, `r` empty).
   A malformed record anywhere fails the file. Certificates are parsed and
   checked only for leaves the tree reaches.
4. **File syntax.** Blank lines are rejected. A trailing `\r` is stripped.
   `M` and a block's cell set must be non-empty (`-` is allowed for `B`, and
   for the whole `blocks` or `pairs` field).
5. **Claimed-line list.** The spec doesn't give the separator between a
   block's claimed lines; the files use `,` (`3/4,9/10,...`), so that is the
   only one accepted, and a block must claim at least one line. `a/b` may come
   in either order but `a != b`. A repeated claim is harmless and accepted.
6. **Block size.** The spec's "blocks have at most 16 cells" is enforced: a
   larger block fails.
7. **Pairs.** A pair's two cells must be distinct, empty, outside every other
   gadget, and on one line. That line need not be live.
8. **Extra leaf check.** The leaf position (after Breaker's reply) is also
   checked for a whole Maker line. The spec's coverage and block checks
   already imply this; it is a cheap second guard.
9. **Occupied reply.** A record whose `r` lies in its own `M` or `B` is
   rejected at load; after mapping, `r` is checked again against the actual
   position.
10. **Block games.** Plain minimax over the block's empty cells, Maker to
    move, testing for a completed Maker edge at every node on both turns
    first. Three exact shortcuts keep it fast: Maker completes an edge with
    one cell left at once; Breaker facing one such threat must block it, and
    facing two loses; an edge containing another edge is dropped (owning it
    means owning the smaller one, and a Breaker mark in the smaller one is in
    it too). Results are memoized on the abstract game: the number of empty
    cells and each edge's empty part, with cells numbered in id order. The
    outcome depends only on that, so the key is exact, and it shares results
    between blocks of different shape or orientation when their games match.
11. **Canonical form.** Any canonical form under G serves the spec's
    indexing; this one is the lexicographically least packed board, not the
    spec's example of sorted `(s(M), s(B))`.
12. **Several files.** More than one proof file may be given; their records
    are merged into one index (first file wins on duplicates).
13. **`--root CELL`.** Only Maker's first move at CELL is checked at the
    root; every node below it checks all empty cells as usual. The root node
    itself is not counted among Maker nodes.

## Spec gaps it found

The gaps this checker ran into (the claimed-line separator, duplicate
records, duplicate group maps, whether a pair's line must be live, and
whether a block may claim no lines) are now stated in
`docs/proof-format.md`. Results and where the checked proofs live:
`docs/checking.md`.
