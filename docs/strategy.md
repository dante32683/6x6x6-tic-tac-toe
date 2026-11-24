# Breaker's winning strategy on 6x6x6, in plain terms

This page describes the strategy of the first proof (`full-6x6x6.txt`) as
compactly as the data allows. The numbers are measured on its three
per-orbit files; `docs/patterns.md` gives the measurements and the scripts
that produce them.

## The board

Cells are `(x, y, z)` with each coordinate in 0..5 (cell id
`36x + 6y + z`). The 148 winning lines are 108 axis lines (rows), 36 face
diagonals (the two diagonals of each of the 18 axis planes), and 4 space
diagonals. A space-diagonal cell lies on 7 lines; every other cell on 3 or
4. Each space diagonal has three layers, named by the coordinate values its
cells use:

    x=0      x=1      x=2      x=3      x=4      x=5
    o....o   ......   ......   ......   ......   o....o     o  corner {0,5}
    ......   .m..m.   ......   ......   .m..m.   ......     m  mid    {1,4}
    ......   ......   ..cc..   ..cc..   ......   ......     c  core   {2,3}
    ......   ......   ..cc..   ..cc..   ......   ......
    ......   .m..m.   ......   ......   .m..m.   ......
    o....o   ......   ......   ......   ......   o....o

Diagrams show the six x-layers side by side, rows y = 0..5 top to bottom,
columns z = 0..5 left to right.

The lines have 1,152 symmetries: the 48 rotations and reflections of the
cube combined with 24 relabelings of the coordinate values, the same on
all three axes, that keep lines as lines (they permute the value pairs
{0,5}, {1,4}, {2,3} and may swap inside a pair). Under them every first move is one of three kinds: a
diagonal cell, a cell on 4 lines, or a cell on 3 lines. The proof has one
file per kind. The relabelings can swap layers, so "core" and "mid" below
refer to the orientation the proof is written in.

## The strategy in one paragraph

Breaker spends his first moves killing the lines that no cheap gadget can
handle: he puts one mark on each of the four space diagonals, starting in
the core. Each such mark kills 7 lines, so after his fourth reply about 26
of the 148 lines are dead. The remaining game then splits into about 51
independent pieces: about 10 small planar slabs (blocks) in which Breaker
wins a local sub-game, and about 41 pairs, two empty cells of one line,
where Breaker answers each Maker move with the other cell. Breaker plays
each piece separately; since the pieces share no cells, every live line is
blocked by the piece that owns it. In 97% of the proof's leaves this split
comes after four replies, in the other 3% after three.

## The opening: four marks on four diagonals

These are rules the data supports; the percentage is the share of the
proof's replies that follow each one.

1. **First reply: a core cell.** Against every first move the proof plays
   (3,3,3) (3 of 3 orbits). Against a corner, that is the far core cell on
   Maker's own diagonal.
2. **Second reply: a mid cell of a fresh diagonal.** Always on a diagonal
   with no Breaker mark (299 of 299 positions), on the mid layer in 99%,
   and on a diagonal Maker hasn't touched in 95%.
3. **Third reply: a fresh diagonal again**, in 97% of the 7,768 positions:
   core 66%, mid 20%, corner 14%.
4. **Fourth reply, then the split.** 99% of these replies are still on a
   space diagonal, and 79% complete the set of one mark per diagonal.

From the second reply on, Breaker avoids diagonals that Maker has marked
(91 to 96% at each depth). What the rules don't fix is *which* cell of the
allowed set: in nearly every position several choices remain that are not
symmetric to each other, and no simple local rule picks the proof's choice
(threat counts, the Erdos-Selfridge potential, distances, and their
combinations predict at most 31% of second replies and 20% of third
replies; `docs/patterns.md`). The search picked the reply after which a
known block layout fits best, so the real rule is "the reply that leaves a
position one of the layouts below can finish". `docs/rule.md` gives a rule
that a second proof follows exactly. At a leaf, Breaker's four marks form
one of 201 patterns up to symmetry, and 9 patterns cover 90% of leaves.

## The finish: blocks and pairs

**Why blocks are needed.** A pair covers one line with two cells. After
four rounds there are about 122 live lines and 208 empty cells, so pairing
alone would need 244 cells. Blocks cover lines more cheaply: a typical
leaf has blocks claiming about 82 lines with 117 cells (1.4 cells per
line) and pairs for the other 41 lines with 82 cells, leaving about 10
cells unused.

**The workhorse block** is a 3-by-4 slab in one plane: 12 cells, three
columns of one coordinate by four of the other. It claims every line of its
plane that crosses it in at least 2 cells. Two placements do half of all
the block work:

    slab claiming 9 lines        slab claiming 8 lines
    (plane x=0; rows y, cols z)
    . . . . . .                  # # # # . .
    . # # # . .                  # # # # . .
    . # # # . .                  # # # # . .
    . # # # . .                  . . . . . .
    . # # # . .                  . . . . . .
    . . . . . .                  . . . . . .
    4 rows + 3 columns           3 rows + 4 columns
    + both plane diagonals       + one plane diagonal

Breaker, moving second, can hit every claimed line inside the slab. This is
a real sub-game (6 Breaker cells against 9 lines, not a pairing), solved
exhaustively by the verifier. Together these two blocks claim 51% of all
block-claimed lines; with the 3x3 slab (claiming its 3 rows and 3 columns)
and a few more placements, 9 blocks claim 90%. The proof uses 54 distinct
blocks in all; 98% of block uses are 3x4 or 3x3 slabs, and only 0.03% are
not flat.

**Where the slabs go.** 55% sit in the cube's six faces, 30% one plane
in, and 14% in the two middle planes. They cover axis lines and face
diagonals, never space diagonals; those are dead from the opening or, in
about one leaf in four, held by a pair.

**Maker's marks.** Maker has 4 marks at a leaf. Pairs must be empty, so
Maker's marks sit in unused cells or inside blocks: 53% of leaves have at
least one Maker mark inside a block, and the block still wins with it.

## Leaf layouts: a catalogue, not a formula

A leaf's *layout* is its set of blocks; the pairs then follow by matching
each remaining line to two free cells of its own. The most common layout,
used in 5.7% of all leaves (and in each orbit):

    x=0      x=1      x=2      x=3      x=4      x=5
    ...DDD   ..AAA.   ..AAA.   ..AAA.   ..AAA.   ......
    ...DDD   .IIIF.   CIIIFB   CIIIFB   CIII.B   ..HHH.
    ...DDD   ....F.   C...FB   C...FB   CJJJJB   ..HHH.
    ...DDD   ....F.   CGGGFB   C...FB   CJJJJB   ..HHH.
    ......   ....F.   CGGGFB   C...FB   CJJJJB   ..HHH.
    ......   ......   .GGG..   ...EEE   ...EEE   ...EEE

Ten slabs (eight 3x4, two 3x3), each in one plane: D, H, A, C, B, and E in
face planes, the rest one plane in or in the middle. A slab drawn across
several layers is vertical: A, for example, is the 4-by-3 slab in the plane
y=0.

How far the layouts compress:

- **Layouts.** 5,999 distinct layouts up to symmetry; 55 cover half the
  leaves, 434 cover 90%, 1,807 cover 99%, and the last 1% needs the other
  4,192 (1,751 are used once).
- **Families.** Nearly every layout is one of the search's starting
  templates, as is or with blocks removed: 76% of leaves use a template
  exactly, 23.6% drop one or two of its blocks (the lines those blocks
  held go to pairs), and 0.4% add a block. Grouped by template, 27 families
  cover half the leaves, 161 cover 90%, 423 cover 99%, and 1,027 cover
  all.
- **Across first moves.** The three orbits use the same pieces: 40 of the
  54 blocks and 1,602 layouts occur in all three, and 95 to 99.8% of each
  orbit's leaves use a layout that also occurs in another orbit.

## What does not compress, and why

- **The exact reply.** The opening rules leave several non-equivalent
  cells, and the proof's choice depends on which layout fits afterwards,
  not on any local feature tested. Some of the other choices may also win;
  the proof records only one per position.
- **The layout tail.** No layout fits most positions (the top one fits
  5.7%), because a layout must leave Maker's four marks in unused cells or
  in blocks that survive them, and Maker's marks go anywhere. The 5,999
  are what the search happened to use, not a minimum: 520 layouts certify
  every leaf the checkers reach, and at least 25 are needed
  (`docs/leaf-catalogue.md`).
- **The pairs.** They are a matching computed per position and have no
  structure worth listing.

## Where the full strategy lives

The proof files list every reply (R records, 8,070) and every leaf
certificate (L records, 1,568,045); `docs/proof-format.md` defines them and
shows why disjoint gadgets compose. The rules on this page summarize the
checked files and are not part of the proof.
