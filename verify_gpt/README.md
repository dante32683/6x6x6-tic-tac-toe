# Python checker by ChatGPT

`check_cube6.py` was written by ChatGPT in a blank web session from the
prompt in `prompt.md`, which holds only the task and the `docs/proof-format.md`
of that day. It saw no code from this repo.
Python 3.10+ and numpy:

    python check_cube6.py --selftest
    python check_cube6.py proof.txt [--root CELL] [--all-records]

It checks every leaf certificate in the file, reached or not. The walk
follows the first record of each position in file order; `--all-records`
(added by Claude, not part of ChatGPT's original program) walks every
record of a reached position, as `verify/` does. Its results are in
`docs/checking.md`.

`test_mutations.py` (added by Claude, not part of ChatGPT's program) samples
real leaf records, checks that they pass, and checks that corrupted copies
(a reply on a marked cell, overlapping or misplaced pairs and blocks, a claim
witness outside its block) fail:

    python test_mutations.py [proof] [records=40] [seed=1]

The reached-leaf counts match `verify_py/` exactly. Where the proofs live
and their SHA-256s: `docs/checking.md`.
