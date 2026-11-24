# Task: write an independent proof checker

I have a computer-generated proof that Breaker wins 6x6x6 Maker-Breaker
tic-tac-toe. It is a large text file in the format specified below. A
checker for it already exists, written by a different AI. I want a second,
fully independent one from you, so that a bug would have to appear in two
separately written programs to go unnoticed.

Work only from the specification below. Do not assume anything about the
other checker. If the spec is ambiguous or seems wrong anywhere, say so
explicitly before writing code, and state the interpretation you chose.

## What to deliver

1. One Python 3 file, `check_cube6.py` (standard library plus numpy only).
   Usage:
   - `python check_cube6.py proof.txt` checks the whole game from the empty
     board and prints `PROOF OK` or the first failure with its position.
   - `python check_cube6.py proof.txt --root CELL` checks only the subtree
     after Maker's first move at CELL and every first move in the same orbit
     under the symmetry group, and prints `ROOT ORBIT OK` (this is not a full
     proof). My files: one holds the orbit of cell 0, another the orbit of
     cell 2, a third will hold the orbit of cell 8. Concatenated they should
     give `PROOF OK`.
   - Print counts at the end: records read, Maker nodes checked, leaf
     certificates checked, distinct block games solved, seconds taken.
2. Build everything yourself: the 148 lines, the symmetry group (assert it
   has 1,152 elements and is closed under composition), and the block-game
   solver. Never trust data in the proof file beyond the records themselves.
3. Performance: the files are large (up to 700 MB, about 500,000 leaf
   records), so stream the file once, store records compactly, and memoize.
   Canonicalizing a position under 1,152 maps is the hot spot; vectorize it
   with numpy. Memoize block games by their shape up to translation and
   symmetry, plus marks. It should finish in under an hour and under 8 GB of
   RAM on a normal desktop.
4. A short self-test (`python check_cube6.py --selftest`) with tiny
   hand-built cases that must fail: a reply on an occupied cell, overlapping
   gadgets, a pair whose cells are not on one line, a live line left
   uncovered, a block that is actually a Maker win, a Maker move with no
   matching record.
5. A list of every place you made a judgment call about the spec.

Be strict: when in doubt, fail the proof rather than accept it.

## The specification (verbatim)

The spec mentions the generating program's own tools (`cube6`, `verify`,
`data6.json`); ignore those, they are context only.

# Proof file format (6x6x6 Maker-Breaker, Breaker wins)

`cube6 prove ... ` with `PROOF=<path>` writes a proof file. `verify/` is an
independent checker for it: it shares no code with the search and must not
read `data6.json`. This file is the whole contract between them.

## The game

- Cells: the 216 cells of a 6x6x6 cube, id = `x*36 + y*6 + z`, with
  `x, y, z` in `0..6`.
- Lines: every set of 6 cells `p, p+d, ..., p+5d` inside the cube, for a
  direction `d` in `{-1,0,1}^3 \ {0}`. There are 148 lines.
- Maker moves first and wins by owning all 6 cells of a line. Breaker wins by
  owning at least one cell of every line. Each turn the player to move takes
  one empty cell.
- Symmetries: the group `G` of 1,152 automorphisms of the line hypergraph used
  here. Each is `(x,y,z) -> (t(x_p), t(y_p), t(z_p))` followed by reflecting
  any subset of coordinates (`c -> 5 - c`), where `p` permutes the three
  coordinates and `t` is one permutation of `{0..5}` applied to every
  coordinate, chosen from the 48 that commute with `c -> 5 - c` (they permute
  the pairs `{0,5}, {1,4}, {2,3}` and may swap inside each pair). With `t` the
  identity these are the 48 geometric cube symmetries; the other value
  permutations are not geometric but still map every line to a line.
  This is the full automorphism group of the line hypergraph: Dvořák and
  Valla (Discrete Mathematics, 2021) show it has order
  `2^(d-1+k) d! k!` with `k = floor(n/2)`, which is 1,152 for n = 6, d = 3.
  Patashnik's 1980 Qubic proof used the same kind of map (192 for 4x4x4).
- The verifier builds `G` itself: for each of the 6 * 8 * 720 candidate maps it
  keeps the ones that send all 148 lines to lines, and it asserts the result
  has 1,152 elements and is closed under composition. It never takes the
  group from the proof file or from the search.
- Orbits of first moves under `G`: the 216 cells fall into three orbits, the
  24 cells of the four space diagonals (7 lines each), the 144 cells on 4
  lines, and the 48 cells on 3 lines. So the root needs one Maker first
  move per orbit, and the verifier's check of every empty cell (below) covers
  the rest through `G`. The search's ten geometric first-move classes 0..9
  (representatives cells 0, 1, 2, 7, 8, 14, 43, 44, 50, 86) fall into the
  orbits {0, 6, 9}, {1, 2, 3, 5, 7, 8}, and {4}.
- Why this is sound: a map in `G` is a bijection on cells that maps lines to
  lines, so it maps a block's edges (`line ∩ block`) to the mapped block's
  edges, live lines to live lines, and Maker and Breaker sets to sets of the
  same size. A valid certificate or Breaker reply therefore stays valid after
  mapping, and every check below is unchanged by it.

## What the file claims

Breaker has a strategy that never lets Maker complete a line. The file gives
Breaker's reply in a set of positions, and at the end of each line of play a
*certificate* that Breaker can hold the rest of the game.

## Records

Plain text, one record per line, fields separated by ` | `. Cell sets are
comma-separated cell ids in increasing order (empty set: `-`). Lines starting
with `#` are comments.

Every record describes a position with **Breaker to move**: Maker set `M`,
Breaker set `B`, `|M| = |B| + 1`. Two kinds:

    R | M | B | r
    L | M | B | r | blocks | pairs

- `R` (reply): in position (M, B) Breaker plays cell `r`. Play continues from
  (M, B + r) with Maker to move.
- `L` (leaf): Breaker plays `r`, and the position (M, B + r), Maker to move,
  has the certificate given by `blocks` and `pairs`:
  - `blocks`: block entries separated by ` ; ` (or `-` for none). A block entry
    is `cells : lines`, where `cells` is the block's cell set and `lines` is a
    list of claimed lines, each written as `a/b`: two distinct cells of that
    line that both lie in the block (two cells determine at most one line).
  - `pairs`: pair entries separated by ` ; ` (or `-`). A pair entry is `a/b`,
    two empty cells; the pair covers the unique line through `a` and `b`.

A position may be given in any orientation: the record for (M, B) also serves
every position `(s(M), s(B))` for each `s` in `G`, with reply `s(r)` and the
certificate mapped by `s`. The search writes each record in the orientation
it met the position, and keys positions by their canonical form under `G`
too; the verifier indexes records by their canonical form under `G`
(for example the least sorted `(s(M), s(B))` over `G`).

## What the verifier checks

Starting from the empty board with Maker to move, `check_maker(M, B)`:

1. No line is all Maker (`M` contains no full line). Otherwise: fail.
2. For **every** empty cell `m` (not just symmetry classes), the position
   (M + m, B), Breaker to move, must match a record under some symmetry `s`:
   a record (M', B') with `s(M') = M + m` and `s(B') = B`. None: fail.
3. With `r = s(r')`, `r` must be empty in (M + m, B). Then:
   - `R` record: `check_maker(M + m, B + r)`.
   - `L` record: check the certificate on (M + m, B + r), mapped by `s`.

Memoize `check_maker` on positions (any orientation) so shared subtrees are
checked once. The recursion ends because every step adds marks.

A certificate on position (M, B) with Maker to move is valid when:

1. Each block's cells, and each pair's two cells, are pairwise disjoint across
   all blocks and pairs. Pair cells are empty. Block cells may hold marks.
2. Each claimed line `a/b` of a block is a real line through `a` and `b`, and
   both lie in the block. Each pair `a/b` lies on a real line.
3. Every *live* line (no cell in `B`) is a claimed line of some block, or the
   line of some pair.
4. Each block is a Breaker win: the game on the block's cells where the
   "edges" are the claimed lines that are still live, each restricted to the
   block (`line ∩ block`), with the marks already in the block, **Maker to
   move**, Breaker winning if every such edge ends with a Breaker mark and
   Maker winning if he owns a whole edge. Check it with plain minimax over the
   block's empty cells (blocks have at most 16 cells), testing for a completed
   Maker edge at every node on both turns before anything else.

Why this proves the game: inside a certificate Breaker answers each Maker move
in the gadget Maker played in (the other cell of a pair, the block's winning
reply in a block; any empty cell if the gadget is spent or Maker played
outside every gadget). Gadgets are disjoint, so their strategies never
interfere, and each live line gets a Breaker mark from its gadget.

The step "any empty cell" rests on one lemma: an extra Breaker mark never
hurts. If Breaker wins a block from (M, B) with Maker to move, he also wins it
from (M, B ∪ X) for any X disjoint from M: he plays the original strategy, and
whenever it names a cell he already owns he takes any other empty cell. A
Breaker mark only removes edges and empty cells, so every position he reaches
is the original one with extra Breaker marks. The same lemma lets the
verifier accept a block whose certificate was found before Breaker's latest
reply landed elsewhere.

A Breaker win in Maker-Breaker means the second player can always stop the
first from completing a line. For the ordinary game (both players can win)
this gives a draw together with strategy stealing: the first player cannot be
forced to lose, since an extra mark of his own never hurts him. A paper must
state both halves; the verifier checks only the first.

`verify full` prints the number of records, `check_maker` nodes, leaves, and
distinct block games, and ends with `PROOF OK` (whole game, every first move),
`ROOT ORBIT OK` (with `--root`: one first-move orbit only, not a proof), or the
first failure with its position. `verify certs` ends with `CERTS OK`, which
covers the leaf certificates alone and says nothing about the tree above them.
