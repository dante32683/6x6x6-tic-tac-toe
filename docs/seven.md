# 7x7x7: a static strategy and a re-check

Cain, Raymond, and Källersjö, "Cubic tic-tac-toe: A matching-based
approach" (arXiv:2509.21494, v1, 2025) prove that Breaker wins 7x7x7
Maker-Breaker, so ordinary 7x7x7 is a draw. This page gives a much shorter
proof of the same theorem by the block method of this repository, an
independent re-check of their proof (including one missed case in section
4.3, which their own moves close), and what the 7x7x7 and 6x6x6 proofs
share.

## Their proof

There is no proof file. The proof is a fixed Breaker opening plus a claim
that a pairing exists at the end of it, checked by C++ code that
regenerates every case (`tic-tac-toe-code.tar.gz`, linked on p. 15; it
covers only the center opening, and the authors offer the rest on request).
The code logs matching sizes, not the matchings.

- **Maker opens at the center** (section 4.2). Breaker plays 555, then 626,
  then a corner of superdiagonal C or D (117, else 771; 177 if Maker holds
  both), then the first free cell of 177, 711, 622, 266 on the other one
  (226 or 662 in the rare case). Paper cells are digits 1 to 7, so 444 is
  the center. One rotation about the main diagonal puts Maker's second move
  in the frame x <= y, which keeps 626 free. After four rounds 166 lines
  survive on 335 free cells, and every one of the 194 x 339 x 337 =
  22,163,142 positions is claimed to have a pairing (332 cells).
- **Maker opens elsewhere** (section 4.3). Breaker takes the center, then
  555, then 626 (or 717 if Maker took 626). A symmetry is said to put
  Maker's first two moves in the half cube x <= 4. After three rounds 168
  lines survive on 337 free cells (one spare), and 195 x 194 x 339 =
  12,824,370 positions are claimed to have pairings.

Breaker's opening ignores Maker except when Maker takes one of the planned
cells. No four cells off the center kill more than the 27 lines this
opening kills (a brute force over the 24 degree-7 cells; other cells lie
on at most 5 lines).

## Our re-check (`seven/`)

`seven/` is a small Rust crate, separate from `cube6`, that rebuilds the
board and both openings from the paper (center case: also from
`starting-moves.C`) and tests every position for a pairing by augmenting
paths. Each pairing it finds is checked from scratch (two distinct free
cells of each surviving line, no cell used twice, every line dead or
paired), so a success doesn't rest on the matching code. It also asserts
the paper's symmetry step for the center case and finds each position's
tight set: the lines whose free cells exactly equal their paired cells,
where one more Maker mark would leave no pairing.

    cd seven && cargo build --release && cargo test --release
    target/release/seven center | offcenter | gap | sample <n> <seed>

| | center (4.2) | off-center (4.3) |
| --- | --- | --- |
| positions | 22,163,142 | 12,824,370 |
| with a pairing, validated | all | all |
| surviving lines, free cells | 166, 335 | 168, 337 |
| positions with a tight set | 0 | 0 |
| time, 8 threads | 449 s | 220 s |

Both of the paper's counts and both "every case has a pairing" claims
reproduce exactly. No position is even tight: one extra Maker mark
anywhere would still leave a pairing. In the off-center case that is all
the room there is, since 337 free cells against 336 needed leave one spare.

The exact surplus says how many extra Maker marks, placed anywhere, a
position's pairing survives (`seven sample 20000 7`, 20,000 random
positions of each case):

| surplus | center | off-center |
| --- | --- | --- |
| 1 | 0 | 20,000 (all) |
| 2 | 138 (0.7%) | |
| 3 | 19,862 (99.3%) | |

Three is the most the center case can have (335 free cells, 332 needed),
and one the most the off-center case can have. So Hall's condition binds
only for the whole board: no region of the cube is ever the bottleneck,
just the total cell count. That is why a fixed opening, blind to Maker's
moves, is enough there. On 6x6x6 after four rounds the count fails for the
board as a whole (121 lines need 242 cells, 208 are free), so no pairing
exists anywhere close, and gadgets denser than pairs have to make up the
difference.

The paper's text is looser than its code about Breaker's third and fourth
moves ("such a corner cell lying on one of these two superdiagonals", then
"any unoccupied cell along whichever superdiagonal ... they have not yet
occupied"); the code fixes one choice. On 100,000 random center openings,
every choice the text allows still leaves a pairing (`seven anymove 100000
3`: 2,360,389 positions, none without). That is a sample, not a proof of
the looser reading.

## A gap in section 4.3, and how it closes

Section 4.3 says: "Rotating the cube if necessary, there is no loss of
generality in assuming that Maker's first and second moves are in the 'half
cube' for which the first coordinate is at most 4." That needs one symmetry
that puts both moves in the half, and none exists when the two moves lie
on opposite sides of the center in every coordinate (centered coordinates
of opposite sign in all three). Example: Maker 111, Breaker 444, Maker
555. Every symmetry maps 111 and 555 to opposite corners of a cube around
the center, so one of them always has first coordinate at least 5, and
Breaker's prescribed second move, 555, is Maker's in this very example.

`seven gap` counts these openings: 5,832 ordered pairs of Maker moves
(216 x 27), 165 classes up to the 48 symmetries. The enumeration of
195 x 194 never reaches them, so their 339 third moves each were never
checked. The theorem still holds, with the paper's own moves: choose any
orientation that puts Maker's first move in the half cube and his second
move off 555, 626, and 717. Then 555 is free for Breaker's second move,
626 or 717 stays free for his third, and every one of these orientations
(3,780 over the 165 classes, 1,281,420 positions) has a pairing after every
third Maker move. A search for a different second move also closes every
class (it settles on a corner of the main diagonal, 111 or 117).

So the fix is a sentence in the paper's Step 1 ("if no symmetry puts both
moves in the half cube, use one that puts the first there and keeps the
second off 555, 626, and 717") plus these checks.

## A static Breaker strategy for 7x7x7 (`seven/cover7.txt`)

The block method (`docs/proof-format.md`; `gen/gen.py`) proves the same
theorem with no opening and no casework. `seven/cover7.txt` lists 18
disjoint blocks and 81 pairs that between them claim all 193 lines on the
empty board, with 0 free marks:

| blocks | cells | claimed lines (edges), in the grid's own rows and columns |
| --- | --- | --- |
| 10 | 3x3 grid | 3 rows, 3 columns |
| 3 | 3x3 grid | 3 rows, 1 column, 1 diagonal |
| 4 | 3x4 grid | 4 rows of 3, 3 columns of 4, 1 diagonal |
| 1 | 3x4 grid | 4 rows of 3, 3 columns of 4, both diagonals |

An edge is a line's cells inside the block. A grid's two directions are
any two line directions, so some grids are slanted or lie in diagonal
slices. The blocks use 177 cells and
claim 112 distinct lines (116 edges, since a few lines have an edge in two
blocks); the pairs use 162 cells and claim the other 81; 4 cells are left
over. Breaker's strategy is to answer every Maker move inside the
gadget it lands in: with the block's local strategy, or with the other cell
of the pair. A move on a spare cell or in a finished gadget gets any reply,
and an extra Breaker mark never hurts him. Each block is a win for Breaker
moving second (he hits every edge), so every line gets a Breaker mark and
Maker never completes one. This is the standard composition argument for
disjoint gadgets, with pairs as the two-cell case.

`seven cover` checks the file without `gen.py` or `mb.py`: blocks and
pairs disjoint, each edge's cells inside its block and on one line, each
pair on one line, every line claimed, and every block solved by its own
exhaustive search (`cover.rs`, memoized minimax over the block's cells).
The test `cover7_is_a_breaker_win` runs it in 0.03 s.
A second checker, `seven/check_cover7.py`, was written in Python from the
specification alone, without reading `seven/src/`, `gen/`, or `src/`; run
`python seven/check_cover7.py seven/cover7.txt` (its mutation tests: `python seven/test_check_cover7.py`).

    python gen/gen.py 1 120 7                   # in an empty folder; writes data7.json
    python gen/cover_export.py data7.json 0 cover7.txt
    seven/target/release/seven cover cover7.txt  # COVER OK

The search isn't deterministic, but the stored file is the certificate.
Layouts like it are common: a longer run found three more with 0 free
marks (23, 20, and 19 blocks). On the empty 6x6x6 board blocks need 3 free
marks, which is why the 6x6x6 proof searches an opening.
Pairs alone can't cover 7x7x7 (193 lines need 386 cells; there are 343),
which is why their proof plays an opening first. A literature search found no
earlier static 7x7x7 strategy; the closest method is Uiterwijk's set
matching (arXiv:1703.10678), shown on planar boards.

## What 7x7x7 shares with 6x6x6

**The opening.** Both proofs start by putting one Breaker mark on each of
the four space diagonals, starting next to the center and moving out:

| | 7x7x7 (center opening) | 6x6x6 (our rule proof, `docs/rule.md`) |
| --- | --- | --- |
| first reply | 555, next to the center | (3,3,3), a core cell |
| second | 626, two steps out, a fresh diagonal | a mid cell of a fresh diagonal |
| third | a corner of a fresh diagonal | a fresh diagonal, core first, then mid, then corner |
| fourth | the last diagonal | the last diagonal (79% of replies) |
| depends on Maker? | only when Maker took the planned cell | yes: avoid Maker's diagonals, then farthest from Maker |

The space-diagonal cells are the only cells on 7 lines (on both boards,
apart from 7x7x7's center), so both openings take the cheapest kills
first. In both, four marks kill 27 lines at best.

**The finish.** Both end in a static certificate at every leaf: a set of
disjoint gadgets, each defended on its own. On 7x7x7 the gadgets are all
pairs; on 6x6x6 about 10 blocks carry 82 of the roughly 122 live lines and
pairs take the other 41 (`docs/patterns.md`). Our pairs are found by the
same matching problem as theirs. 7x7x7 is the special case where the
block layout is empty.

**Why 6x6x6 needs blocks.** Density, live lines per free cell, after
Breaker's k marks kill as many lines as possible and Maker's k marks take
k more cells (`gen/kill_bound.py`, an exact branch and bound, checked
against brute force for small k; each run takes seconds):

| board | k = 3 | k = 4 | k = 5 | k = 6 |
| --- | --- | --- | --- | --- |
| 7x7x7, Maker at the center | 172/337 = 0.510 | 166/335 = 0.496 | | |
| 7x7x7, Breaker at the center (the paper's moves, not proven best) | 168/337 = 0.499 | | | |
| 6x6x6 | 127/210 = 0.605 | 121/208 = 0.582 | 115/206 = 0.558 | 109/204 = 0.534 |
| 5x5x5, Maker at the center | 89/119 = 0.748 | 83/117 = 0.709 | 78/115 = 0.678 | 73/113 = 0.646 |
| 5x5x5, Breaker at the center | 84/119 = 0.706 | 78/117 = 0.667 | 72/115 = 0.626 | 68/113 = 0.602 |

A pairing needs at most 1/2. 7x7x7 is under it after four rounds (0.496)
and only just; 6x6x6 sits at 0.582 to 0.587 after four, which blocks at up
to 3/4 cover. Pairs alone would need at least 8 rounds on 6x6x6, where
the count first allows them (100 lines on 200 cells), and at least 12 on
5x5x5 with Maker at the center (48 lines on 101 cells). 5x5x5 has a
center on 13 lines and 0.87 lines per cell on the empty board.
