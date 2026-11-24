# replay_py: independent replay of Breaker's rule

`replay_rule.py` is a second program, written without reading `src/`,
`verify/`, `verify_py/`, `verify_gpt/`, or `gen/`, that replays Breaker's
five-question rule (docs/rule.md, "The rule") on a rule proof file. It
uses only Python 3 and numpy.

## What it checks

1. It builds the 1,152-map group G from docs/proof-format.md and asserts each
   map is a bijection that sends lines to lines, and that there are exactly
   1,152. It also asserts the 148 lines and that the four space diagonals are lines.
2. It reads only the `R` records (stream; `L` lines are skipped unparsed) and
   indexes them by the canonical form of (M, B) under G, keeping the canonical
   forms of every (M, B + r) reached.
3. From the labelled empty board it explores every labelled history in which
   Breaker follows the rule. At each labelled position with Maker to move it
   takes the lowest-id cell of each class of Maker moves (class of (M + c, B)
   under G), and for each result P:
   - P's class has an R record: Breaker plays the rule's reply x; covered if
     (M + c, B + x) is equivalent under G to (M_r, B_r + r) for some R record
     of that class, else a failure (printed). Covered positions continue.
   - no R record: a leaf stop.
   Identical labelled positions are merged; counts without merging are in brackets.

`REPLAY OK` is printed only with zero failures.

## What it does not check

It never reads the `L` records, so it relies on the certificate checkers
(`verify/`, `verify_py/ --all-records`) to walk every record: that every
leaf stop has a valid certificate, and that every R successor has a record.
Leaf stops here are classes with no R record; it does not confirm an L record
exists for them. It checks the rule's replies only at positions that have R
records, and the rule is defined only for the first three replies.

One reading of the brief: Maker's first move is fixed to cells 0, 2, 8, as the
brief says. Cells 1 and 2 are one class under G, so "lowest id" alone would
give 1 (with the reply 129 failing); the script asserts that 0, 2, 8 are one
per class and uses them. Below the root it uses the lowest id of each class.

## Run

    python replay_py/replay_rule.py <proof.txt>

One process, about 5 minutes and a few hundred MB per file.

## Results

`rule-6x6x6-ext.txt` (8,912 R records, 7,349 position classes):

    depth 1: labelled positions explored 1, histories 1
    depth 2: labelled positions explored 3, histories 3
    depth 3: labelled positions explored 229, histories 232
    depth 4: labelled positions explored 7945, histories 8783
      reply 1: rule positions met 3 [3], covered 3 [3], failures 0 [0], leaf stops 0 [0]
      reply 2: rule positions met 229 [232], covered 229 [232], failures 0 [0], leaf stops 0 [0]
      reply 3: rule positions met 7945 [8783], covered 7945 [8783], failures 0 [0], leaf stops 34060 [36934]
      reply 4: rule positions met 0 [0], covered 0 [0], failures 0 [0], leaf stops 1513708 [1839842]
    total failures 0; 285s
    REPLAY OK

`rule-6x6x6.txt` (8,512 R records, 7,349 position classes): 400 failures, all
third replies (434 without merging), no `REPLAY OK`; 296s.

      reply 1: rule positions met 3 [3], covered 3 [3], failures 0 [0], leaf stops 0 [0]
      reply 2: rule positions met 229 [232], covered 229 [232], failures 0 [0], leaf stops 0 [0]
      reply 3: rule positions met 7945 [8783], covered 7545 [8349], failures 400 [434], leaf stops 34060 [36934]
