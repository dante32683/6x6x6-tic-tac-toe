# Breaker's replies as a rule

The first proof stores 8,070 reply records (R records,
`docs/proof-format.md`). This page states a five-question rule that picks
every one of Breaker's replies before his last, the second proof, which a
search built by following the rule, and the checks that Breaker wins by
playing the rule himself.

## The rule

At a position that is not a leaf (Breaker can't finish with a certificate
yet), Breaker replies:

1. **First reply:** the core cell farthest from Maker's mark. For each of
   the proof's three first moves (cells 0, 2, and 8) that is (3,3,3).
2. **Later replies:** an empty cell of a space diagonal that has no Breaker
   mark yet; among those, one whose diagonal has no Maker mark if there is
   one; then the depth's usual layer (second reply: mid, then corner, then
   core; third reply: core, then mid, then corner); then the cell farthest
   from Maker's marks (the largest sum of squared distances to them); the
   lowest cell id breaks any tie left.

Leaf replies (L records) stay free: the reply that comes with the
certificate. In code the rule is `RULE=default`, short for
`diag,fresh,clean,layer,dist2` (`src/rule.rs` lists every feature). The id
tiebreak rarely matters: after the features, the cells still tied form one
orbit of the position's symmetry group in 90 to 92% of R positions.

## The first proof does not follow it

`cube6 rules <proof>...` counts the R records whose reply equals the rule's
up to the position's symmetry. On the first proof:

| Orbit (file) | depth 1 | depth 2 | depth 3 |
| --- | --- | --- | --- |
| class 0 | 1 of 1 | 21 of 54 (38.9%) | 278 of 852 (32.6%) |
| class 2 | 1 of 1 | 35 of 124 (28.2%) | 655 of 2,454 (26.7%) |
| class 4 | 1 of 1 | 25 of 121 (20.7%) | 1,255 of 4,462 (28.1%) |

Depth is the number of Maker marks on the board. No variant did better:
Erdős-Selfridge potential or live lines through Maker's marks in place of
distance (14 to 18% at depth 3), nearest instead of farthest (5 to 9%),
or extra keys after distance (within a point). The search ranked replies by
how well its templates fit, and several replies win.

## The rule proof

`RULE=<spec>` makes `cube6 prove` try the rule's reply first at every
non-leaf Breaker node and fall back to the other replies only if it fails;
the progress line counts these fallbacks as exceptions. `SEED=<proof
files>` lets it reuse the first proof's leaf certificates. The search ran
in ten shares (`SPLIT=k/10`, `docs/search.md`), then once unsplit from
their merged caches:

    RULE=default COLLECT=1 SPLIT=k/10 SEED=class0.txt,class2w.txt,class4-full.txt \
      CACHE=cache.txt FRONTIER=frontier.txt cube6 prove 4 4 0,2,4

No share needed an exception, and the existing templates certified every
leaf. The result, `rule-6x6x6.txt`, has 1,738,490 records (8,512 R,
1,729,978 L). All three checkers print `PROOF OK` on it, and `cube6 rules`
finds every R reply equal to the rule's, read in the orientation the
record is written in:

| Depth | R records | Agree with the rule | Decided before the cell-id tiebreak |
| --- | --- | --- | --- |
| first reply | 3 | 3 (100%) | 3 (100%) |
| second reply | 232 | 232 (100%) | 182 (78.4%) |
| third reply | 8,277 | 8,277 (100%) | 7,391 (89.3%) |

## Strict replay: the rule as Breaker's own strategy

`cube6 rules` reads each record in the orientation the search wrote it in,
which is wherever the search first met that position. A Breaker who plays
the rule has no record to look at, so "Breaker wins by following the rule"
needs a labelling of the board he can work out himself. `cube6 replay
<proof>` (`src/replay.rs`) tests this: from the empty board it tries every
Maker move, answers each with the rule read in a stated frame (`FRAME`),
and counts a reply as covered when the position after it is, under the
full group, the position after some R record's own reply. A position with
no R record is a leaf.

Every rule feature is geometric, so only the cell-id tiebreak and the
non-geometric relabelings (which also turn corner cells into mid or core
cells) can change the rule's choice. Results on `rule-6x6x6.txt`:

| `FRAME` | Breaker reads the board in | 1st reply | 2nd reply | 3rd reply |
| --- | --- | --- | --- | --- |
| `geometric` | its least orientation under the 48 cube maps | 5 of 10 | 202 of 554 | 6,337 of 7,192 |
| `full` | its least orientation under all 1,152 maps | 3 of 3 | 59 of 221 | 391 of 1,984 |
| `fixed` | Maker's first move relabeled to cell 0, 2, or 8, then every later move as played | 3 of 3 | 406 of 639 | 10,432 of 11,301 |
| `search` | as `fixed`, but after each Maker move the board is relabeled so the move is the lowest-id cell giving an equivalent position | 3 of 3 | 229 of 229 | 7,545 of 7,945 |

So the rule holds only in the search's own frame, and even there 400 third
replies fall outside the proof: positions the search first met by another
move order, wrote in that orientation, and later served from its cache.

`cube6 extend 4 failures-search.txt` proved the rule's own reply at all
400, adding 400 R records and 83,164 leaf records. Put first in a copy of
the proof they make `rule-6x6x6-ext.txt`: 1,822,054 records (8,912 R,
1,813,142 L). On it the replay passes in the search frame: 3 of 3, 229 of
229, and 7,945 of 7,945, each the record's own cell. A second program,
`replay_py/replay_rule.py`, written from the rule's description without the
Rust code, reports the same counts.

**The strategy needs several records per position.** In the search frame
the labelling depends on the order of Maker's moves, so the rule can reply
differently to two move orders that reach the same position. For example
`R | 0,50,54 | 129,154 | 93` and `R | 0,9,80 | 129,169 | 93` are the same
position up to G, with replies that are not equivalent; 547 classes of
`rule-6x6x6-ext.txt` are like this. So no file with one record per
position can hold the rule strategy, and a check of it must walk every
record:

- `verify full` checks every record of each position it reaches, so its
  `PROOF OK` covers the rule strategy.
- `verify_py/` and `verify_gpt/` follow the first record per position by
  default, which checks a different strategy (it differs from the rule's
  at 552 replies). With `--all-records` they walk every record, as
  `verify/` does. All three print `PROOF OK` (counts in
  `docs/checking.md`).
- Negative test: the line `R | 0 | - | 1`, a wrong second record for the
  position after Maker's first move, appended to the file. The first-record
  walk never reads it; with `--root 0 --all-records` both Python checkers
  reject the file.

**Leaf layouts.** `gen/mine.py` over every L record of
`rule-6x6x6-ext.txt`: 5,188 distinct layouts up to G (a layout is a leaf's
set of blocks, pairs ignored; `docs/patterns.md`) from 53 distinct blocks;
69, 484, and 1,777 layouts cover 50, 90, and 99% of the leaves; the most
used layout covers 2.2%, and 1,030 are used once. Leaves average 10.35
blocks and 41.7 pairs. The first proof has 5,999 layouts.

**Where the rule stops.** The rule picks replies at positions whose class
has an R record; at a class with only L records Breaker plays a leaf
record's reply and certificate. Which classes are leaves is part of the
proof, not of the rule: at depth 3 the replay meets 42,005 positions, and
7,945 of them have R records. At least 442 classes have both kinds.
`cube6 replay` plays the rule there; stopping at the leaf is also covered,
because every checker walks every record of each class it reaches.
`REPLAY OK` reads only R records, so the claim needs `PROOF OK` on the same
file as well.

## Breaker's strategy in full

1. Relabel the cube so Maker's first move is cell 0, 2, or 8.
2. After each later Maker move c, with the board labelled as (M, B) before
   it, find the lowest-id empty cell c' such that (M + c', B) is equivalent
   to (M + c, B) under the full group, and relabel the whole board by a map
   that carries (M + c, B) onto (M + c', B). The map may move Maker's
   earlier marks as well (from M = {8}, B = {129}, Maker's 103 becomes 53
   only by a map that also sends 103 to 8 and 8 to 53); when several maps
   qualify they all give the same labelled board, the same reply, and the
   same board next turn.
3. If the position's class has an R record, play the rule's reply x in
   this labelling, which is cell g^-1(x) on the real board for the
   relabeling g in use; otherwise play the class's leaf record.

With `rule-6x6x6-ext.txt` this strategy has no exceptions, so the R records
can be regenerated from the rule plus the list of positions where it stops,
and only the leaves need storing. The relabeling uses the full group's
canonical form, so a person playing the rule needs a program (or the class
table) for it.
