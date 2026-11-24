# Proof file format (6x6x6 Maker-Breaker, Breaker wins)

`cube6 prove` with `PROOF=<path>` writes a proof file, and the checkers
(`verify/`, `verify_py/`, `verify_gpt/`) read it. This document is the whole
contract between them: the checkers share no code with the search and do not
read `data6.json`.

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
  keeps the ones that send all 148 lines to lines and drops duplicate maps
  (2,304 candidates pass, since reflecting all three axes equals composing
  `t` with `c -> 5 - c`), and it asserts the result
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
    comma-separated list of at least one claimed line, each written as `a/b`:
    two distinct cells of that line that both lie in the block (two cells
    determine at most one line).
  - `pairs`: pair entries separated by ` ; ` (or `-`). A pair entry is `a/b`,
    two empty cells; the pair covers the unique line through `a` and `b`,
    which need not be live.

A writer should give one record per position up to G when the strategy
allows it. When a file has several, `verify/` requires every one to
check, and `verify_py/` and `verify_gpt/` use the first in file order
unless run with `--all-records`, which walks every one. A strategy whose
reply depends on the order of Maker's moves needs several records for
some positions: the rule-following proof `rule-6x6x6-ext.txt` does
(docs/rule.md, Strict replay), so it is checked with `verify/` or with
`--all-records`.

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
forced to lose, since an extra mark of his own never hurts him. The checkers
check only the first half.

`verify full` (options `--root <cell>` and `--emit-used <file>`, the latter
under "Pruned proofs" below) prints the number of records, `check_maker` nodes, leaves, and
distinct block games, and ends with `PROOF OK` (whole game, every first move),
`ROOT ORBIT OK` (with `--root`: one first-move orbit only, not a proof), or the
first failure with its position. `verify certs` ends with `CERTS OK`, which
covers the leaf certificates alone and says nothing about the tree above them.

## Pruned proofs

A search writes every record it met, including duplicates of one position
and records from earlier passes that the final strategy never reaches.
`verify full <proof> --emit-used <lines.txt>` checks exactly as without the
flag and, once the walk passes, walks again following only the first record
(in file order) of each reached position, and writes the 1-based file line
numbers of the records it meets. `gen/compact_prune.py <proof> <lines.txt>
<pruned.txt>` copies the comment lines and those records byte for byte. The
result is an ordinary proof in this format with one record per position up
to G, and it is what the catalogue format below encodes.

## Catalogue format (v2)

A binary encoding of a pruned proof. The pruned 6x6x6 proof (1.49 GB as v1)
is 7.8 MB as v2 and 1.9 MB after `zstd -19`, against 107 MB for the full v1 file
under zstd. It is a transport format: `verify_py/` and `verify_gpt/` read v1 only, and
a v2 file is trusted once `gen/compact_v2.py decode` turns it back into v1
and that file passes all three checkers. `verify/` also reads v2 directly
(`verify full proof.v2`): its `v2.rs` decodes the file by the rules below
and checks the records like any v1 records, so a wrong decoder can only
make a check fail. Encoder and reference decoder:
`gen/compact_v2.py`.

The idea: leaves repeat a few thousand certificate layouts, each in many
orientations and positions. v2 stores each layout once, and per leaf only
which layout, which map of G puts it in place, and the two moves that lead
there; the pairs are recomputed.

### Conventions

- `G` is the 1,152 maps of the line hypergraph (above), each written as its
  image tuple `(g(0), ..., g(215))`, sorted in increasing lexicographic
  order; a *symmetry index* is a position in that list. `verify_py/`,
  `verify_gpt/`, and `gen/cube6.py` build G in this order.
- The *line order* lists the 148 lines by their sorted cell tuples, in
  increasing lexicographic order.
- Integers are little-endian. A *set* is a `u8` count followed by that many
  `u8` cell ids, increasing.

### Layout

| Part | Contents |
| --- | --- |
| magic | the 8 ASCII bytes `C6PROOF2` |
| sizes | `u32 T` (header bytes), `u32 K` (layouts), `u32 NR` (R records), `u32 NL` (leaves), `u8 W` (layout id width, 2 or 4) |
| header | `T` bytes of ASCII: the v1 file's comment lines, joined by `\n` |
| catalogue | `K` layouts; each is `u8` block count, then per block: its cell set, a `u8` claim count, and per claim two `u8` cells `a, b` (two cells of the claimed line inside the block) |
| R records | `NR` records in v1 file order; each is the set `M`, the set `B`, and `u8 r` |
| leaf counts | `NR` bytes: the number of leaves under each R record |
| leaf columns | `NL` bytes `m` (Maker's move), then `NL` bytes `r` (Breaker's reply), then `NL` layout ids (`u16` if `W = 2`, else `u32`), then `NL` symmetry indices (`u16`) |

The file ends right after the last column.

### Decoding to v1

Write the header, then each R record as `R | M | B | r`. Then, for each R
record in order with position `(M, B + r)` (Maker to move), take its next
`count` leaves in column order. Leaf `(m, r', k, g)` becomes

    L | M + m | B + r | r' | blocks | pairs

- `blocks`: layout `k` with every cell sent through map `g` of G; each
  block's cells sorted, each claim written `min/max`, blocks sorted by their
  cell lists.
- `pairs`: on the position `(M + m, B + r + r')`, the lines that have no
  Breaker mark and are claimed by no block each get two cells that are empty
  and outside every block, no cell used twice. The reference decoder finds
  them with Kuhn's augmenting-path matching: two slots per line, lines in the
  line order, each line's cells tried in increasing order. A pairing exists
  for every leaf the encoder wrote, since the source record's own pairs are
  one. Pairs are written `min/max`, sorted.

Every leaf is in the orientation of the R record above it, which the v1
rules allow, so the decoded file differs byte-wise from the pruned file but
checks the same way. The decoder needs G and the lines, but no canonical
forms and no tree walk.

### Encoding

`gen/compact_v2.py encode <pruned.txt> <out.v2>` reads a pruned proof twice.
The first pass indexes every position by its canonical form. A walk then
gives each leaf to the first `(R record, Maker move m)` in R record order,
`m` increasing, whose child position is that leaf up to G (R records whose
Maker position repeats an earlier one are skipped), and finds the map `s`
from the leaf record to that child. The second pass maps each certificate's
blocks by `s` and reduces them under G: the least block partition (each cell
labelled by its block's least cell, as in `gen/cube6.py`), ties broken by
the least sorted claimed-line lists, each claim stored as the two least
cells of its line in the block. Layout ids number layouts by the number of
leaves using them, most used first, ties by their sorted block lists; when
several maps send a layout to a leaf's blocks (the layout has symmetries),
the leaf gets the least symmetry index. Ids therefore do not depend on the
order of the L records, and encoding a decoded file gives back the same
bytes. The encoder stops with an error on a second record for one position,
an unreached leaf, a position with no record, or more than 255 leaves under
one R record.
