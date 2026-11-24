# Patterns in the proof: measurements

The numbers behind `docs/strategy.md`, measured on the first proof's three
per-orbit files (`class0.txt`, `class2w.txt`, and `class4-full.txt`;
`docs/checking.md`). The scripts below write their outputs (JSON, plus the
pickled layouts) to `<out>`.

    python gen/mine.py <out> c0=class0.txt c2=class2w.txt c4=class4-full.txt   # leaves.json, layouts.pkl
    python gen/mine_replies.py <out> c0=... c2=... c4=...                     # replies.json
    python gen/mine_families.py <out> data6.json                              # families.json (needs layouts.pkl)

`gen/cube6.py` builds the lines and the full 1,152-element group G the way
the verifier does; "up to symmetry" below always means up to G. Layers
("core" = coordinates in {2,3}, "mid" = {1,4}, "corner" = {0,5}) are in
each file's own orientation, since G itself can swap the layers. That
orientation is geometric where the search keyed positions by the 48 cube
symmetries: class 0, class 2, and the first part of the class 4 search.
The rest of the class 4 search and the rule search keyed them by all of G,
so layer counts there describe the stored frame, which may differ from the
geometric one by a map that swaps mid and core.

## Size

| | class 0 | class 2 | class 4 | all |
| --- | --- | --- | --- | --- |
| R records (replies) | 907 | 2,579 | 4,584 | 8,070 |
| leaves (L records) | 173,526 | 493,713 | 900,806 | 1,568,045 |
| leaves at depth 3 / 4 | 8,447 / 165,079 | 18,939 / 474,774 | 22,167 / 878,639 | 3.2% / 96.8% |
| blocks per leaf (mean) | 10.62 | 10.49 | 10.31 | 10.40 |
| pairs per leaf (mean, range) | 39.8 (25-68) | 40.7 (23-68) | 41.5 (23-64) | 41.1 (23-68) |
| unused empty cells per leaf | 10.1 | 9.8 | 9.7 | 9.8 |
| distinct blocks | 40 | 49 | 51 | 54 |
| distinct layouts | 2,101 | 3,658 | 4,585 | 5,999 |
| layouts for 90 / 99 / 100% of leaves | 272 / 1,068 / 2,101 | 337 / 1,429 / 3,658 | 435 / 1,705 / 4,585 | 434 / 1,807 / 5,999 |
| top layout's share | 4.7% | 5.7% | 6.0% | 5.7% |

A "layout" is a leaf's set of blocks (pairs ignored), counted up to G.
Reducing under G instead of the 48 geometric maps merges nothing in class 0
(2,101 either way).

## Breaker's replies (`replies.json`)

Share of replies by depth (Maker marks on the board), all orbits together:

| | depth 1 (R) | depth 2 (R) | depth 3 (R) | depth 3 (L) | depth 4 (L) |
| --- | --- | --- | --- | --- | --- |
| replies | 3 | 299 | 7,768 | 49,553 | 1,518,492 |
| on a space diagonal | 100% | 100% | 100% | 100% | 98.8% |
| on a diagonal without a Breaker mark | 100% | 100% | 97.2% | 98.4% | 79.2% |
| on a diagonal without a Maker mark | 67% | 95.3% | 96.2% | 95.8% | 90.9% |
| core / mid / corner | 100 / 0 / 0 | 0 / 99.0 / 1.0 | 65.9 / 20.1 / 14.1 | 98.0 / 1.9 / 0.1 | 54.6 / 23.2 / 21.0 |

- The first reply is cell 129 = (3,3,3) in all three orbits (first moves
  cells 0, 2, and 8). In class 0 it is on Maker's own diagonal.
- The per-orbit rows agree within a few points (`replies.json`, per label).
- Breaker's final marks at a leaf, up to G: 201 distinct sets; 3 cover 50%
  of leaves, 9 cover 90%, 25 cover 99%. They kill 19 to 27 lines: 24 to
  27 in 96.8% of leaves, 20 in 3.1%.

Rules tested and rejected (`rule A`, `B`, and `C` in `gen/mine_replies.py`;
greedy scores and feature orders in `gen/mine_reply_rules.py`):

- "Any empty cell on an untouched diagonal, on the depth's usual layer,
  avoiding Maker's diagonals" contains the reply 94% of the time at depth 2
  and 61% at depth 3, but the set is a single orbit of the position's
  stabilizer (so the rule picks the reply up to symmetry) in only 1.3% and
  0% of positions.
- Greedy scores over empty cells (live lines through the cell holding a Maker
  mark; the Erdos-Selfridge potential with weight 2 or 3 per Maker mark)
  pick the reply 11 to 31% of the time at depth 2 and 6 to 20% at depth 3,
  and almost never uniquely. "Most live lines through the cell" holds for
  every depth-2 reply only because all untouched diagonal cells tie at 7;
  at depth 3 it holds for 19%.
- The best lexicographic order of up to three such features (layer, the
  scores above, Chebyshev distance to Maker, Maker marks on the diagonal,
  lines shared with Breaker's marks) predicts 20% at depth 2 and 14% at
  depth 3.

## Leaf certificates (`leaves.json`)

- Lines per leaf: 25.8 dead (through a Breaker mark), 82.6 claimed by
  blocks (70.1 axis, 12.4 plane-diagonal, 0.0 space-diagonal), 41.1 by
  pairs (28.2 axis, 12.6 plane-diagonal, 0.26 space-diagonal).
- Cells per leaf: 117 in blocks, 82 in pairs, 9.8 unused, 8 marks.
- Maker marks inside blocks: none in 47% of leaves, one in 38%, two in
  13%, three or more in 2%. Breaker's leaf reply lies inside the
  certificate in 5.5% of leaves.
- Block shapes (distinct coordinate values per axis), share of 16.3 million
  block uses: 1x3x4 71%, 1x3x3 27%, 1x4x4 1.7%, 1x3x5 0.2%, 1x4x6 0.06%,
  and 5,696 non-planar uses (3x3x3 and larger).
- Planes, by block uses: 55% in a face plane (a coordinate fixed at 0 or
  5), 30% one plane in (1 or 4), 14% in a middle plane (2 or 3).

## Blocks and templates (`families.json`)

- 54 distinct blocks. The two most used (a 3x4 slab claiming 9 lines and a
  3x4 claiming 8, drawn in `strategy.md`) claim 51% of all block-claimed
  lines; 9 blocks claim 90% and 15 claim 99%. The top one is used 3.0 times
  per leaf.
- Nearest template: for each layout, the view (48 geometric images of each
  of the 1,393 templates in `data6.json`) sharing the most blocks. 76.0% of
  leaves use a template exactly, 23.6% a template minus blocks (22.7% minus
  one, 1.0% minus two), and 0.4% add blocks to their nearest template. No
  leaf block is outside the library.
- Leaves by nearest template: 1,027 templates in use; 27 cover 50% of
  leaves, 161 cover 90%, 423 cover 99%. The top template covers 8.0%.

## Across orbits

- 40 of the 54 blocks appear in all three orbits; the rest are in class 2
  or class 4 only.
- 1,602 layouts appear in all three orbits. Leaves whose layout also occurs
  in another orbit: class 0 99.8%, class 2 99.4%, class 4 94.9%.
