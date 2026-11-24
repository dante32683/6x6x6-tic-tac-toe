# How small can the leaf catalogue be?

The first proof's leaves use 5,999 distinct block layouts up to G
(`docs/patterns.md`), but that counts what the search happened to pick per
leaf. This page measures how few layouts certify every leaf the proof tree
reaches, and describes `mincat-6x6x6.txt`, a proof that uses only those.

## Result

- **Catalogue: 520 layouts** (of the 5,999 the search used) certify all
  1,338,185 leaves that `verify/` reaches. 179 were chosen by set cover; the
  other 341 are leaves' own layouts kept as a fallback for 685 leaves (0.05%)
  that none of the chosen layouts fitted. The most used layout alone
  certifies 50% of leaves; 5 cover 90%, 27 cover 99%, 111 cover 99.9%
  (the search's own choice needed 434 for 90%). 230 layouts serve one leaf.
- **Lower bound: 25.** CP-SAT finds the exact minimum cover (OPTIMAL, 25)
  of 140 hard leaves (leaves the first catalogues missed), with fit sets
  over all 5,999 layouts. Any catalogue drawn from those layouts that
  certifies every reached leaf needs at least 25 entries. This is a bound
  for this definition of a fit (blocks and claims fixed, pairs rematched)
  and this pool; layouts outside it are not covered by the bound.
- So the true minimum is between 25 and 520. The gap is mostly the long
  tail: random samples need 11 layouts (300 leaves, top-400 pool, optimal),
  but each successive sample of the leaves the catalogue still misses needs
  more (28 of 200, 45 of 150, 80 of 300, optimal on each sample), and the
  last 685 leaves were not scouted at all.
- **Proof:** `mincat-6x6x6.txt` keeps the 8,070 R records unchanged and
  has 1,338,185 L records. All three checkers print `PROOF OK` on it (file,
  hash, and results: `docs/checking.md`). `gen/mincat_selfcheck.py` also
  ran `verify_py/`'s certificate check on every 10th to 25th new record as
  it was written (70,727 records, all OK).

## What "fits" means

A catalogue entry is a layout's blocks, each with the lines it claims. The
claim set of a cell set is the block library's (`data6.json`); it never
varies across the proof's records. Pairs are not part of an entry: for each
leaf they are recomputed by matching. Layout `k` fits leaf (M, B) (Maker to
move) when, for some g in G, with the leaf mapped into the layout's frame:

1. every live line is claimed by a block or gets a pair: two empty cells of
   the line outside every block, all pairs disjoint (bipartite matching, two
   cells per line, `gen/mincat_fit.py: match_pairs`);
2. each block is a Breaker win, Maker to move, on its live claimed lines
   restricted to the block, with Maker's cells in it already taken (exact,
   `gen/mbfast.py`; a block that wins from empty with every claim live is
   only re-solved when Maker has a cell in it).

That is exactly what `docs/proof-format.md` asks of a certificate, so a fit
gives a valid L record. Claimed lines that are dead are written anyway, as
the search does.

## Method

- **Reached leaves** (`gen/mincat_reach.py`): index every record by the
  canonical form of its position (first record in file order wins, as
  `verify_py` does) and walk the tree from the empty board, every empty
  cell for Maker. 1,466,708 distinct positions among 1,576,115 records;
  7,073 Maker nodes; 1,338,185 reached leaves. A position can have several
  records, and `verify/` checks every one, so the walk follows the reply of
  every R record of a position. Following only the first record (what
  `verify_py` does) reaches 1,051,860 leaves, the count `verify_py`
  reports; a proof built from those alone fails `verify/` with "no
  record". The other 229,860 L records are duplicates of an earlier
  record's position or never reached, and are left out.
- **Fitting** (`gen/mincat_fit.py`): two necessary conditions prune the 1,152
  maps cheaply (an unclaimed live line can hold at most 4 block or Maker
  cells, and the pairs need two free cells per unclaimed live line), then
  the exact check runs. For the full pass (`gen/mincat_rewrite.py fit`),
  the views that fit with no Maker cell at all are computed once per
  Breaker set up to G (201 such sets) and reused by every leaf with that
  Breaker set; Maker's cells only add constraints.
- **Fit sets on samples** (`gen/mincat_scout.py`): for a sample of leaves,
  every layout of a pool (the most used N, or all 5,999) that fits each
  leaf in some orientation.
- **Set cover** (`gen/mincat_cover.py`): greedy for the catalogue, CP-SAT for
  the exact minimum of the sample. Any catalogue that certifies every
  reached leaf also covers the sample, so the sample's optimum, computed
  with fit sets over all 5,999 layouts, is a lower bound for the whole
  proof.
- **Rounds**: fit every reached leaf with a small catalogue (greedy on a
  random sample), then scout a sample of the leaves it missed, add the
  greedy cover of that sample, and refit only the misses; repeat. Leaves
  still missed at the end keep their original record (`mincat_rewrite.py
  own`), which adds their own layouts to the catalogue. Rounds run: 13
  layouts (96.1% of the first 1,051,860 leaves), then 32, 51, and 83 more
  on each round's misses, then all 179 again with the fixed prefilter
  (below); the 286,325 leaves found by the all-records walk went through
  the same four catalogues.
- **Prefilter.** An earlier prefilter counted a Maker cell inside a block
  twice on an unpaired line and so rejected some real fits. The bound above
  uses only fit sets from the fixed prefilter; the proof never depended on
  the prefilter, since every record passed the exact check.
- **Proof** (`gen/mincat_rewrite.py join`): the format header, every R
  record unchanged, each reached leaf's new L record in place of its old one,
  and no other L records.

## Reproduce

    python gen/mincat_reach.py reach-all.npz class0.txt class2w.txt class4-full.txt
    python gen/mincat_scout.py reach-all.npz layouts.pkl data6.json scout1.json 300 400 1
    python gen/mincat_cover.py cat1.json scout1.json
    python gen/mincat_rewrite.py fit reach-all.npz layouts.pkl data6.json cat1.json round1
    # misses: cat round1/miss-*.txt into an .npy, scout a sample of them, cover, refit:
    python gen/mincat_rewrite.py fit reach-all.npz layouts.pkl data6.json cat2.json round2 miss1.npy
    python gen/mincat_rewrite.py own reach-all.npz layouts.pkl missN.npy own
    python gen/mincat_rewrite.py join reach-all.npz proof.txt round1 round2 ... own
    python gen/mincat_selfcheck.py verify_py/check_cube6.py round1/fit-*.tsv --every 25

`layouts.pkl` is `gen/mine.py`'s output (`docs/patterns.md`).
