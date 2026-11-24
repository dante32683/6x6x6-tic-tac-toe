# Figures

`python gen/figures.py` (from the repository root) draws every figure in the
paper as `<name>.svg` and a 200 dpi `<name>.png` in this folder. Each figure
function asserts the numbers the paper quotes about it (24/144/48 cells by
line count, 9 and 8 claimed lines, 11 blocks and 41 pairs at the leaf, the
summed squared distances), so a change to the data fails the script rather
than leaving a figure that disagrees with the text.

Board figures draw the cube as six slices in two rows of three (x = 0 to 2
on top, 3 to 5 below), with y down the rows and z across. They are about
6.2 in wide, the paper's text width, so their 8 pt labels print at 8 pt.

| File | Paper | Shows |
| --- | --- | --- |
| `board-six-layers` | Figure 1 | one axis line, one plane diagonal, and one space diagonal |
| `three-kinds-of-cell` | Figure 2 | cells by the number of lines through them; the space-diagonal cells lettered by layer |
| `pairing-5x5` | Figure 3 | the Golomb-Hales pairing for five in a row on 5x5 (Golomb and Hales 2002, Figure 2) |
| `slab-placements` | Figure 4 | the two most common placements of the 3x4 block |
| `relabeling-layers` | Figure 5 | the value relabeling 1<->2, 3<->4 on two lines, before and after (slices x = 0 to 5, two per row) |
| `line-of-play` | Figure 6 | the line of play through `class0.txt`, each mark numbered by round |
| `leaf-certificate` | Figure 7 | the certificate at that leaf: blocks, pairs, unused cells, and marks |
| `reply-rule-second` | Figure 8 | the second-reply example: candidate mid cells and their summed squared distances |

`line-of-play` and `leaf-certificate` draw the real L record at line 4 of
`class0.txt` (copied into `gen/figures.py` as `LEAF_RECORD`), so the pairs
shown are the proof's own.

In the pairing figure the column letters `f` to `j` are not in column order;
the figure follows Golomb and Hales, and the script asserts that each letter's two
cells lie on one row, column, or diagonal.
